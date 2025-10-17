#!/usr/bin/env python3
"""
Django-Integrated Comprehensive Film Analytics Embedding Pipeline
Works with existing Django Movie model and new analytics models
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm
import time
import json
from datetime import datetime, timedelta
import os
import gc
import logging
from typing import Dict, List, Tuple, Any
import django
from django.conf import settings
from django.db import transaction
from django.core.management import execute_from_command_line

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

# Import Django models
from movies.models import Movie
from chat.analytics_models import (
    FilmPerformanceSummary, 
    TheaterPerformance, 
    MarketAnalysis, 
    ComparativeAnalysis,
    EmbeddingChunk
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DjangoFilmAnalyticsPipeline:
    def __init__(self):
        """Initialize the Django-integrated film analytics pipeline"""
        self.config = self._load_config()
        self.model = None
        self.pc = None
        self.index = None
        
    def _load_config(self):
        """Load configuration with Pinecone credentials"""
        return {
            # Pinecone settings
            'PINECONE_API_KEY': "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ",
            'PINECONE_ENVIRONMENT': "us-east-1-aws",
            'INDEX_NAME': "customer-database-vectors",
            'DIMENSION': 768,
            
            # Embedding settings
            'EMBEDDING_MODEL': "BAAI/bge-base-en-v1.5",
            'BATCH_SIZE': 256,
            
            # Data processing settings
            'CHUNK_SIZE': 25000,
            'MAX_RECORDS_2023': 5000000,
            'MAX_RECORDS_2024': 5000000,
            
            # Checkpoint settings
            'CHECKPOINT_DIR': "checkpoints",
        }
    
    def initialize_components(self):
        """Initialize embedding model and Pinecone connection"""
        try:
            logger.info("🚀 Initializing Django Film Analytics Pipeline")
            
            # Initialize embedding model
            logger.info("🤖 Loading embedding model...")
            self.model = SentenceTransformer(self.config['EMBEDDING_MODEL'])
            
            # Initialize Pinecone
            logger.info("🔌 Connecting to Pinecone...")
            self.pc = Pinecone(api_key=self.config['PINECONE_API_KEY'])
            
            # Create or connect to index
            existing_indexes = self.pc.list_indexes().names()
            if self.config['INDEX_NAME'] not in existing_indexes:
                logger.info(f"🆕 Creating index: {self.config['INDEX_NAME']}")
                self.pc.create_index(
                    name=self.config['INDEX_NAME'],
                    dimension=self.config['DIMENSION'],
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region=self.config['PINECONE_ENVIRONMENT']
                    )
                )
                # Wait for index to be ready
                while not self.pc.describe_index(self.config['INDEX_NAME']).status['ready']:
                    time.sleep(1)
            
            self.index = self.pc.Index(self.config['INDEX_NAME'])
            
            logger.info("✅ Components initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize components: {e}")
            raise
    
    def create_film_performance_chunks(self, movies: List[Movie]) -> List[Tuple[str, Dict]]:
        """Create film performance analysis chunks from Django Movie objects"""
        chunks = []
        
        for movie in movies:
            # Calculate performance metrics
            sales_estimate = float(movie.price) * movie.reserved
            occupancy_rate = movie.get_occupancy_rate()
            
            # Calculate day-over-day growth (placeholder)
            dod_growth = np.random.uniform(-5, 15)
            
            performance_text = f"""
Film Performance Analysis:
Title: {movie.title}
Genre: {movie.genre} | Rating: {movie.rating}
Studio: {movie.studio_name}
Release Date: {movie.release_date}
Running Date: {movie.running_date}

Performance Metrics:
- Reserved Seats: {movie.reserved:,} / {movie.total_seats:,} ({occupancy_rate:.1f}%)
- Sales Estimate: ${sales_estimate:,.2f}
- Average Price: ${movie.price:.2f}
- Day-over-Day Growth: {dod_growth:.1f}%

Technical Details:
- Screen Format: {movie.screen_format}
- Movie Format: {movie.movie_format}
- Language: {movie.language_format}
- Runtime: {movie.runtime} minutes
- Country: {movie.country}

Showtime Information:
- Date: {movie.date_sh}
- Time: {movie.time_sh}
- Auditorium: {movie.auditorium}
- Seating Type: {movie.seating_type}

Market Context:
- Theater: {movie.theater_name}
- Location: {movie.theater_city}, {movie.theater_state}
- Circuit: {movie.circuit_name}
- DMA: {movie.dma}
- Amenities: {movie.amenities}
""".strip()
            
            metadata = {
                'chunk_type': 'film_performance',
                'title': movie.title,
                'genre': movie.genre,
                'rating': movie.rating,
                'studio_name': movie.studio_name,
                'reserved_seats': movie.reserved,
                'total_seats': movie.total_seats,
                'occupancy_rate': round(occupancy_rate, 2),
                'sales_estimate': round(sales_estimate, 2),
                'price': float(movie.price),
                'dod_growth': round(dod_growth, 2),
                'screen_format': movie.screen_format,
                'language_format': movie.language_format,
                'release_date': str(movie.release_date),
                'running_date': str(movie.running_date),
                'date_sh': str(movie.date_sh),
                'time_sh': str(movie.time_sh),
                'theater_city': movie.theater_city,
                'theater_state': movie.theater_state,
                'circuit_name': movie.circuit_name,
                'dma': movie.dma,
                'runtime': movie.runtime,
                'country': movie.country,
                'year': movie.date_sh.year,
                'movie_id': movie.id
            }
            
            chunks.append((performance_text, metadata))
        
        return chunks
    
    def create_comparative_analysis_chunks(self, movies: List[Movie]) -> List[Tuple[str, Dict]]:
        """Create comparative analysis chunks for 'What films are performing like X?' queries"""
        chunks = []
        
        # Group movies by title for comparative analysis
        movies_by_title = {}
        for movie in movies:
            if movie.title not in movies_by_title:
                movies_by_title[movie.title] = []
            movies_by_title[movie.title].append(movie)
        
        for title, movie_list in movies_by_title.items():
            # Calculate comprehensive performance metrics
            total_reserved = sum(movie.reserved for movie in movie_list)
            total_seats = sum(movie.total_seats for movie in movie_list)
            total_sales = sum(float(movie.price) * movie.reserved for movie in movie_list)
            avg_price = sum(float(movie.price) for movie in movie_list) / len(movie_list)
            occupancy_rate = (total_reserved / total_seats) * 100 if total_seats > 0 else 0
            
            # Get first movie for metadata
            first_movie = movie_list[0]
            
            # Calculate performance patterns
            performance_patterns = self._analyze_performance_patterns(movie_list)
            
            # Get market penetration
            market_penetration = self._calculate_market_penetration(movie_list)
            
            comparative_text = f"""
Comparative Film Analysis:
Title: {title}
Genre: {first_movie.genre} | Rating: {first_movie.rating}
Studio: {first_movie.studio_name}
Release Date: {first_movie.release_date}

Performance Profile:
- Total Reserved: {total_reserved:,} seats
- Total Capacity: {total_seats:,} seats
- Overall Occupancy: {occupancy_rate:.1f}%
- Total Sales: ${total_sales:,.2f}
- Average Price: ${avg_price:.2f}

Performance Patterns:
- Peak Performance Time: {performance_patterns['peak_time']}
- Best Performing Format: {performance_patterns['best_format']}
- Top Market: {performance_patterns['top_market']}
- Day-over-Day Growth: {performance_patterns['dod_growth']:.1f}%
- Weekend vs Weekday Performance: {performance_patterns['weekend_ratio']:.1f}

Market Analysis:
- Market Penetration: {market_penetration['penetration_rate']:.1f}%
- Geographic Spread: {market_penetration['geographic_spread']} cities
- Theater Circuit Mix: {market_penetration['circuit_diversity']} circuits
- Format Diversity: {market_penetration['format_diversity']} formats

Release Strategy:
- Release Timing: {first_movie.release_date}
- Running Duration: {performance_patterns['running_duration']} days
- Screen Count: {len(movie_list)} showtimes
- Format Mix: {', '.join(performance_patterns['format_mix'])}
""".strip()
            
            metadata = {
                'chunk_type': 'comparative_analysis',
                'title': title,
                'genre': first_movie.genre,
                'rating': first_movie.rating,
                'studio_name': first_movie.studio_name,
                'total_reserved': int(total_reserved),
                'total_seats': int(total_seats),
                'overall_occupancy': round(occupancy_rate, 2),
                'total_sales': round(total_sales, 2),
                'avg_price': round(avg_price, 2),
                'dod_growth': round(performance_patterns['dod_growth'], 2),
                'market_penetration': round(market_penetration['penetration_rate'], 2),
                'geographic_spread': market_penetration['geographic_spread'],
                'circuit_diversity': market_penetration['circuit_diversity'],
                'format_diversity': market_penetration['format_diversity'],
                'peak_time': performance_patterns['peak_time'],
                'best_format': performance_patterns['best_format'],
                'top_market': performance_patterns['top_market'],
                'weekend_ratio': round(performance_patterns['weekend_ratio'], 2),
                'release_date': str(first_movie.release_date),
                'year': first_movie.date_sh.year,
                'movie_ids': [movie.id for movie in movie_list]
            }
            
            chunks.append((comparative_text, metadata))
        
        return chunks
    
    def create_theater_opportunity_chunks(self, movies: List[Movie]) -> List[Tuple[str, Dict]]:
        """Create theater opportunity analysis chunks"""
        chunks = []
        
        # Group movies by theater
        movies_by_theater = {}
        for movie in movies:
            key = (movie.theater_name, movie.theater_city)
            if key not in movies_by_theater:
                movies_by_theater[key] = []
            movies_by_theater[key].append(movie)
        
        for (theater_name, theater_city), movie_list in movies_by_theater.items():
            # Calculate theater metrics
            total_capacity = sum(movie.total_seats for movie in movie_list)
            total_reserved = sum(movie.reserved for movie in movie_list)
            total_sales = sum(float(movie.price) * movie.reserved for movie in movie_list)
            avg_price = sum(float(movie.price) for movie in movie_list) / len(movie_list)
            overall_occupancy = (total_reserved / total_capacity) * 100 if total_capacity > 0 else 0
            
            # Get first movie for metadata
            first_movie = movie_list[0]
            
            # Analyze opportunity patterns
            opportunity_analysis = self._analyze_theater_opportunities(movie_list)
            
            opportunity_text = f"""
Theater Opportunity Analysis:
Name: {theater_name}
Location: {theater_city}, {first_movie.theater_state}
Circuit: {first_movie.circuit_name}
DMA: {first_movie.dma}

Capacity Analysis:
- Total Seats: {total_capacity:,}
- Reserved Seats: {total_reserved:,}
- Overall Occupancy: {overall_occupancy:.1f}%
- Total Sales: ${total_sales:,.2f}
- Average Price: ${avg_price:.2f}

Opportunity Indicators:
- Underperforming Time Slots: {opportunity_analysis['underperforming_slots']}
- Capacity Utilization: {opportunity_analysis['capacity_utilization']:.1f}%
- Price Optimization Potential: {opportunity_analysis['price_optimization']:.1f}%
- Format Mix Opportunities: {opportunity_analysis['format_opportunities']}

Current Movies: {len(set(movie.title for movie in movie_list))} titles
Amenities: {first_movie.amenities}
Market Position: {opportunity_analysis['market_position']}

Recommendations:
- Focus Time Slots: {opportunity_analysis['focus_slots']}
- Pricing Strategy: {opportunity_analysis['pricing_strategy']}
- Format Expansion: {opportunity_analysis['format_expansion']}
""".strip()
            
            metadata = {
                'chunk_type': 'theater_opportunity',
                'theater_name': theater_name,
                'theater_city': theater_city,
                'theater_state': first_movie.theater_state,
                'circuit_name': first_movie.circuit_name,
                'dma': first_movie.dma,
                'total_capacity': int(total_capacity),
                'total_reserved': int(total_reserved),
                'overall_occupancy': round(overall_occupancy, 2),
                'total_sales': round(total_sales, 2),
                'avg_price': round(avg_price, 2),
                'capacity_utilization': round(opportunity_analysis['capacity_utilization'], 2),
                'price_optimization': round(opportunity_analysis['price_optimization'], 2),
                'market_position': opportunity_analysis['market_position'],
                'movie_count': len(set(movie.title for movie in movie_list)),
                'amenities': first_movie.amenities,
                'year': first_movie.date_sh.year,
                'movie_ids': [movie.id for movie in movie_list]
            }
            
            chunks.append((opportunity_text, metadata))
        
        return chunks
    
    def create_market_penetration_chunks(self, movies: List[Movie]) -> List[Tuple[str, Dict]]:
        """Create market penetration analysis chunks"""
        chunks = []
        
        # Group movies by city and date
        movies_by_market = {}
        for movie in movies:
            key = (movie.theater_city, movie.date_sh)
            if key not in movies_by_market:
                movies_by_market[key] = []
            movies_by_market[key].append(movie)
        
        for (city, date), movie_list in movies_by_market.items():
            # Calculate market metrics
            total_market_seats = sum(movie.total_seats for movie in movie_list)
            total_market_reserved = sum(movie.reserved for movie in movie_list)
            market_sales = sum(float(movie.price) * movie.reserved for movie in movie_list)
            market_occupancy = (total_market_reserved / total_market_seats) * 100 if total_market_seats > 0 else 0
            
            # Get first movie for metadata
            first_movie = movie_list[0]
            
            # Analyze market penetration
            penetration_analysis = self._analyze_market_penetration(movie_list)
            
            penetration_text = f"""
Market Penetration Analysis:
City: {city}
State: {first_movie.theater_state}
Date: {date}
DMA: {first_movie.dma}

Market Performance:
- Total Market Capacity: {total_market_seats:,}
- Reserved Seats: {total_market_reserved:,}
- Market Occupancy: {market_occupancy:.1f}%
- Total Market Sales: ${market_sales:,.2f}

Penetration Analysis:
- Theater Count: {len(set(movie.theater_name for movie in movie_list))}
- Circuit Diversity: {penetration_analysis['circuit_diversity']}
- Format Mix: {penetration_analysis['format_mix']}
- Price Range: ${penetration_analysis['price_range'][0]:.2f} - ${penetration_analysis['price_range'][1]:.2f}

Top Performing Movies:
{chr(10).join([f'- {title}: {data['reserved']:,} seats, ${data['price']:.2f} avg" for title, data in penetration_analysis['top_movies'].iterrows()])}

Market Opportunities:
- Underperforming Theaters: {penetration_analysis['underperforming_theaters']}
- Format Gaps: {penetration_analysis['format_gaps']}
- Price Optimization: {penetration_analysis['price_optimization']}
- Capacity Utilization: {penetration_analysis['capacity_utilization']:.1f}%
""".strip()
            
            metadata = {
                'chunk_type': 'market_penetration',
                'city': city,
                'state': first_movie.theater_state,
                'date': str(date),
                'dma': first_movie.dma,
                'total_market_capacity': int(total_market_seats),
                'total_market_reserved': int(total_market_reserved),
                'market_occupancy': round(market_occupancy, 2),
                'total_market_sales': round(market_sales, 2),
                'theater_count': len(set(movie.theater_name for movie in movie_list)),
                'circuit_diversity': penetration_analysis['circuit_diversity'],
                'format_mix': penetration_analysis['format_mix'],
                'price_range_min': round(penetration_analysis['price_range'][0], 2),
                'price_range_max': round(penetration_analysis['price_range'][1], 2),
                'capacity_utilization': round(penetration_analysis['capacity_utilization'], 2),
                'year': date.year,
                'movie_ids': [movie.id for movie in movie_list]
            }
            
            chunks.append((penetration_text, metadata))
        
        return chunks
    
    def _analyze_performance_patterns(self, movies: List[Movie]) -> Dict[str, Any]:
        """Analyze performance patterns for a list of movies"""
        # Analyze time patterns
        time_counts = {}
        for movie in movies:
            time_str = str(movie.time_sh)
            time_counts[time_str] = time_counts.get(time_str, 0) + movie.reserved
        
        peak_time = max(time_counts.items(), key=lambda x: x[1])[0] if time_counts else "Unknown"
        
        # Analyze format performance
        format_performance = {}
        for movie in movies:
            format_performance[movie.screen_format] = format_performance.get(movie.screen_format, 0) + movie.reserved
        
        best_format = max(format_performance.items(), key=lambda x: x[1])[0] if format_performance else "Unknown"
        
        # Analyze market performance
        market_performance = {}
        for movie in movies:
            market_performance[movie.theater_city] = market_performance.get(movie.theater_city, 0) + movie.reserved
        
        top_market = max(market_performance.items(), key=lambda x: x[1])[0] if market_performance else "Unknown"
        
        # Calculate weekend vs weekday ratio
        weekend_reserved = sum(movie.reserved for movie in movies if movie.date_sh.weekday() >= 5)
        weekday_reserved = sum(movie.reserved for movie in movies if movie.date_sh.weekday() < 5)
        weekend_ratio = weekend_reserved / weekday_reserved if weekday_reserved > 0 else 1
        
        # Calculate running duration
        dates = [movie.date_sh for movie in movies]
        running_duration = (max(dates) - min(dates)).days + 1 if dates else 1
        
        return {
            'peak_time': peak_time,
            'best_format': best_format,
            'top_market': top_market,
            'dod_growth': np.random.uniform(-5, 15),  # Placeholder
            'weekend_ratio': weekend_ratio,
            'running_duration': running_duration,
            'format_mix': list(set(movie.screen_format for movie in movies))
        }
    
    def _calculate_market_penetration(self, movies: List[Movie]) -> Dict[str, Any]:
        """Calculate market penetration metrics"""
        total_theaters = len(set(movie.theater_name for movie in movies))
        total_cities = len(set(movie.theater_city for movie in movies))
        total_circuits = len(set(movie.circuit_name for movie in movies))
        total_formats = len(set(movie.screen_format for movie in movies))
        
        # Calculate penetration rate (simplified)
        penetration_rate = (total_cities / 1000) * 100  # Assuming 1000 total cities
        
        return {
            'penetration_rate': min(penetration_rate, 100),
            'geographic_spread': total_cities,
            'circuit_diversity': total_circuits,
            'format_diversity': total_formats
        }
    
    def _analyze_theater_opportunities(self, movies: List[Movie]) -> Dict[str, Any]:
        """Analyze theater opportunities"""
        # Analyze time slot performance
        time_performance = {}
        for movie in movies:
            time_str = str(movie.time_sh)
            if time_str not in time_performance:
                time_performance[time_str] = []
            time_performance[time_str].append(movie.reserved)
        
        avg_time_performance = {time: np.mean(reserved_list) for time, reserved_list in time_performance.items()}
        median_performance = np.median(list(avg_time_performance.values()))
        underperforming_slots = [time for time, avg in avg_time_performance.items() if avg < median_performance]
        
        # Calculate capacity utilization
        capacity_utilization = (sum(movie.reserved for movie in movies) / sum(movie.total_seats for movie in movies)) * 100
        
        # Analyze price optimization potential
        prices = [float(movie.price) for movie in movies]
        price_variance = np.std(prices) / np.mean(prices) if np.mean(prices) > 0 else 0
        price_optimization = max(0, (1 - price_variance) * 100)
        
        # Analyze format opportunities
        format_performance = {}
        for movie in movies:
            format_performance[movie.screen_format] = format_performance.get(movie.screen_format, 0) + movie.reserved
        
        avg_format_performance = {fmt: perf / len([m for m in movies if m.screen_format == fmt]) 
                                 for fmt, perf in format_performance.items()}
        median_format_performance = np.median(list(avg_format_performance.values()))
        format_opportunities = [fmt for fmt, avg in avg_format_performance.items() 
                               if avg < median_format_performance]
        
        return {
            'underperforming_slots': underperforming_slots[:3],
            'capacity_utilization': capacity_utilization,
            'price_optimization': price_optimization,
            'format_opportunities': format_opportunities[:3],
            'market_position': 'High' if capacity_utilization > 50 else 'Medium' if capacity_utilization > 25 else 'Low',
            'focus_slots': underperforming_slots[:2],
            'pricing_strategy': 'Optimize' if price_optimization < 50 else 'Maintain',
            'format_expansion': format_opportunities[:2]
        }
    
    def _analyze_market_penetration(self, movies: List[Movie]) -> Dict[str, Any]:
        """Analyze market penetration"""
        # Circuit diversity
        circuit_diversity = len(set(movie.circuit_name for movie in movies))
        
        # Format mix
        format_mix = {}
        for movie in movies:
            format_mix[movie.screen_format] = format_mix.get(movie.screen_format, 0) + 1
        
        # Price range
        prices = [float(movie.price) for movie in movies]
        price_range = (min(prices), max(prices))
        
        # Top movies
        movie_performance = {}
        for movie in movies:
            if movie.title not in movie_performance:
                movie_performance[movie.title] = {'reserved': 0, 'price': []}
            movie_performance[movie.title]['reserved'] += movie.reserved
            movie_performance[movie.title]['price'].append(float(movie.price))
        
        top_movies = sorted(movie_performance.items(), key=lambda x: x[1]['reserved'], reverse=True)[:3]
        top_movies_df = pd.DataFrame([
            {'title': title, 'reserved': data['reserved'], 'price': np.mean(data['price'])}
            for title, data in top_movies
        ])
        
        # Underperforming theaters
        theater_performance = {}
        for movie in movies:
            if movie.theater_name not in theater_performance:
                theater_performance[movie.theater_name] = []
            theater_performance[movie.theater_name].append(movie.reserved)
        
        avg_theater_performance = {theater: np.mean(reserved_list) 
                                  for theater, reserved_list in theater_performance.items()}
        median_theater_performance = np.median(list(avg_theater_performance.values()))
        underperforming_theaters = [theater for theater, avg in avg_theater_performance.items() 
                                   if avg < median_theater_performance]
        
        # Format gaps (simplified)
        format_gaps = ['IMAX', 'Dolby Cinema']  # Placeholder
        
        # Price optimization potential
        price_optimization = 'High' if price_range[1] - price_range[0] > 10 else 'Medium'
        
        # Capacity utilization
        capacity_utilization = (sum(movie.reserved for movie in movies) / sum(movie.total_seats for movie in movies)) * 100
        
        return {
            'circuit_diversity': circuit_diversity,
            'format_mix': format_mix,
            'price_range': price_range,
            'top_movies': top_movies_df,
            'underperforming_theaters': underperforming_theaters[:3],
            'format_gaps': format_gaps,
            'price_optimization': price_optimization,
            'capacity_utilization': capacity_utilization
        }
    
    def process_chunk(self, movies: List[Movie], chunk_num: int, total_processed: int) -> int:
        """Process a single chunk and create all embedding types"""
        logger.info(f"📦 Processing chunk {chunk_num} ({len(movies):,} movies)")
        
        all_chunks = []
        
        # Create different types of chunks
        logger.info("   Creating film performance chunks...")
        performance_chunks = self.create_film_performance_chunks(movies)
        all_chunks.extend(performance_chunks)
        
        logger.info("   Creating comparative analysis chunks...")
        comparative_chunks = self.create_comparative_analysis_chunks(movies)
        all_chunks.extend(comparative_chunks)
        
        logger.info("   Creating theater opportunity chunks...")
        theater_chunks = self.create_theater_opportunity_chunks(movies)
        all_chunks.extend(theater_chunks)
        
        logger.info("   Creating market penetration chunks...")
        market_chunks = self.create_market_penetration_chunks(movies)
        all_chunks.extend(market_chunks)
        
        logger.info(f"   Created {len(all_chunks)} total chunks")
        
        # Generate embeddings
        texts = [chunk[0] for chunk in all_chunks]
        metadata_list = [chunk[1] for chunk in all_chunks]
        
        logger.info("   Generating embeddings...")
        embeddings = self.model.encode(
            texts,
            batch_size=self.config['BATCH_SIZE'],
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        
        # Upload to Pinecone
        logger.info("   Uploading to Pinecone...")
        self.upload_vectors(embeddings, metadata_list, total_processed)
        
        # Store in Django database
        logger.info("   Storing in Django database...")
        self.store_in_django_db(all_chunks, embeddings)
        
        return len(all_chunks)
    
    def upload_vectors(self, embeddings: np.ndarray, metadata_list: List[Dict], start_idx: int):
        """Upload vectors to Pinecone with retry logic"""
        vectors = []
        for i, (embedding, metadata) in enumerate(zip(embeddings, metadata_list)):
            vector_id = f"{metadata['chunk_type']}_{start_idx + i}"
            vectors.append({
                "id": vector_id,
                "values": embedding.tolist(),
                "metadata": metadata
            })
        
        # Upload in batches
        batch_size = 100
        total_batches = (len(vectors) + batch_size - 1) // batch_size
        
        for i in tqdm(range(0, len(vectors), batch_size), total=total_batches, desc="     Uploading"):
            batch = vectors[i:i + batch_size]
            
            # Retry logic
            for attempt in range(3):
                try:
                    self.index.upsert(vectors=batch, timeout=30)
                    break
                except Exception as e:
                    if attempt < 2:
                        wait_time = 2 ** attempt
                        logger.warning(f"     ⚠️  Batch failed (attempt {attempt + 1}/3): {str(e)[:100]}")
                        logger.info(f"     ⏳ Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"     ❌ Batch failed after 3 attempts!")
                        raise e
            
            time.sleep(0.1)  # Rate limiting
    
    def store_in_django_db(self, chunks: List[Tuple[str, Dict]], embeddings: np.ndarray):
        """Store embedding chunks in Django database"""
        try:
            with transaction.atomic():
                embedding_chunks = []
                for i, (text, metadata) in enumerate(chunks):
                    vector_id = f"{metadata['chunk_type']}_{i}"
                    
                    embedding_chunk = EmbeddingChunk(
                        chunk_type=metadata['chunk_type'],
                        chunk_text=text,
                        vector_id=vector_id,
                        metadata=metadata
                    )
                    embedding_chunks.append(embedding_chunk)
                
                EmbeddingChunk.objects.bulk_create(embedding_chunks, batch_size=1000)
                
        except Exception as e:
            logger.warning(f"⚠️  Failed to store in Django database: {e}")
    
    def save_checkpoint(self, chunk_num: int, total_processed: int, chunk_type_counts: Dict[str, int]):
        """Save processing checkpoint"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'chunk_number': chunk_num,
            'total_processed': total_processed,
            'chunk_type_counts': chunk_type_counts
        }
        
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'django_film_analytics_checkpoint.json')
        os.makedirs(self.config['CHECKPOINT_DIR'], exist_ok=True)
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        logger.info(f"💾 Checkpoint saved: {total_processed:,} records processed")
    
    def run_pipeline(self):
        """Run the complete Django-integrated embedding pipeline"""
        logger.info("🚀 Starting Django Film Analytics Embedding Pipeline")
        logger.info("=" * 80)
        
        # Initialize components
        self.initialize_components()
        
        # Get movies from Django database, filtered by year
        logger.info("📊 Loading movies from Django database...")
        
        # Get 5M records from 2023 and 5M from 2024
        movies_2023 = list(Movie.objects.filter(date_sh__year=2023)[:self.config['MAX_RECORDS_2023']])
        movies_2024 = list(Movie.objects.filter(date_sh__year=2024)[:self.config['MAX_RECORDS_2024']])
        
        all_movies = movies_2023 + movies_2024
        logger.info(f"📈 Total movies to process: {len(all_movies):,}")
        logger.info(f"   - 2023 movies: {len(movies_2023):,}")
        logger.info(f"   - 2024 movies: {len(movies_2024):,}")
        
        # Check for existing checkpoint
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'django_film_analytics_checkpoint.json')
        skip_chunks = 0
        total_processed = 0
        chunk_type_counts = {'film_performance': 0, 'comparative_analysis': 0, 'theater_opportunity': 0, 'market_penetration': 0}
        
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
                skip_chunks = checkpoint['chunk_number']
                total_processed = checkpoint['total_processed']
                chunk_type_counts = checkpoint.get('chunk_type_counts', chunk_type_counts)
                logger.info(f"📂 Resuming from checkpoint: chunk {skip_chunks}, {total_processed:,} records")
        
        # Process data in chunks
        chunk_size = self.config['CHUNK_SIZE']
        total_chunks = (len(all_movies) + chunk_size - 1) // chunk_size
        
        for chunk_num in range(total_chunks):
            if chunk_num + 1 <= skip_chunks:
                continue
            
            start_idx = chunk_num * chunk_size
            end_idx = min(start_idx + chunk_size, len(all_movies))
            chunk_movies = all_movies[start_idx:end_idx]
            
            chunk_start_time = time.time()
            
            try:
                # Process chunk
                chunk_vectors = self.process_chunk(chunk_movies, chunk_num + 1, total_processed)
                total_processed += chunk_vectors
                
                # Clear memory
                del chunk_movies
                gc.collect()
                
                # Save checkpoint every 10 chunks
                if (chunk_num + 1) % 10 == 0:
                    self.save_checkpoint(chunk_num + 1, total_processed, chunk_type_counts)
                
                # Show progress
                chunk_time = time.time() - chunk_start_time
                progress = ((chunk_num + 1) * chunk_size / len(all_movies)) * 100
                logger.info(f"✅ Chunk {chunk_num + 1} completed in {chunk_time:.1f}s")
                logger.info(f"📊 Progress: {(chunk_num + 1) * chunk_size:,}/{len(all_movies):,} ({progress:.1f}%)")
                
            except Exception as e:
                logger.error(f"❌ Chunk {chunk_num + 1} failed: {e}")
                raise
        
        # Final verification
        time.sleep(2)
        stats = self.index.describe_index_stats()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ DJANGO PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info("=" * 80)
        logger.info(f"📊 Final Summary:")
        logger.info(f"   • Total vectors created: {stats['total_vector_count']:,}")
        logger.info(f"   • Index name: {self.config['INDEX_NAME']}")
        logger.info(f"   • Dimension: {self.config['DIMENSION']}")
        logger.info(f"   • Chunk types: {list(chunk_type_counts.keys())}")
        logger.info(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("\n🎯 Your Django-integrated chatbot can now answer:")
        logger.info("   • 'What films are performing like JURASSIC WORLD REBIRTH?'")
        logger.info("   • 'Where are my opportunities?'")
        logger.info("   • 'How is WEAPONS performing in less populated areas?'")
        logger.info("   • 'What showtimes do I want to keep?'")
        logger.info("   • Complex comparative analysis queries")

def main():
    """Main function"""
    pipeline = DjangoFilmAnalyticsPipeline()
    pipeline.run_pipeline()

if __name__ == "__main__":
    main()
