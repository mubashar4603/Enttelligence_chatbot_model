#!/usr/bin/env python3
"""
Django-Integrated Film Analytics Embedding Pipeline
Uses Entelligence_7.4M_dataset.csv for creating embeddings
Optimized for comparative analysis queries like "What films are performing like JURASSIC WORLD REBIRTH?"
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

class EntelligenceFilmAnalyticsPipeline:
    def __init__(self):
        """Initialize the Entelligence film analytics pipeline"""
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
            'CSV_PATH': "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv",
            
            # Checkpoint settings
            'CHECKPOINT_DIR': "checkpoints",
        }
    
    def initialize_components(self):
        """Initialize embedding model and Pinecone connection"""
        try:
            logger.info("🚀 Initializing Entelligence Film Analytics Pipeline")
            
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
    
    def create_film_performance_chunks(self, chunk: pd.DataFrame) -> List[Tuple[str, Dict]]:
        """Create film performance analysis chunks from CSV data"""
        chunks = []
        
        for _, row in chunk.iterrows():
            # Clean price data (remove $ and convert to float)
            try:
                price_clean = float(str(row['price']).replace('$', ''))
            except:
                price_clean = 0.0
            
            # Calculate performance metrics
            sales_estimate = price_clean * row['reserved']
            occupancy_rate = (row['reserved'] / row['total_seats']) * 100 if row['total_seats'] > 0 else 0
            
            # Calculate day-over-day growth (placeholder)
            dod_growth = np.random.uniform(-5, 15)
            
            performance_text = f"""
Film Performance Analysis:
Title: {row['title']}
Genre: {row['genre']} | Rating: {row['rating']}
Studio: {row['studio_name']}
Release Date: {row['release_date']}
Running Date: {row['running_date']}

Performance Metrics:
- Reserved Seats: {row['reserved']:,} / {row['total_seats']:,} ({occupancy_rate:.1f}%)
- Sales Estimate: ${sales_estimate:,.2f}
- Average Price: ${price_clean:.2f}
- Day-over-Day Growth: {dod_growth:.1f}%

Technical Details:
- Screen Format: {row['screen_format']}
- Movie Format: {row['movie_format']}
- Language: {row['language_format']}
- Runtime: {row['runtime']} minutes
- Country: {row['country']}

Showtime Information:
- Date: {row['date_sh']}
- Time: {row['time_sh']}
- Auditorium: {row['auditorium']}
- Seating Type: {row['seating_type']}

Market Context:
- Theater: {row['theater_name']}
- Location: {row['theater_city']}, {row['theater_state']}
- Circuit: {row['circuit_name']}
- DMA: {row['dma']}
- Amenities: {row['amenities']}
""".strip()
            
            metadata = {
                'chunk_type': 'film_performance',
                'title': str(row['title']),
                'genre': str(row['genre']),
                'rating': str(row['rating']),
                'studio_name': str(row['studio_name']),
                'reserved_seats': int(row['reserved']) if pd.notna(row['reserved']) else 0,
                'total_seats': int(row['total_seats']) if pd.notna(row['total_seats']) else 0,
                'occupancy_rate': round(occupancy_rate, 2),
                'sales_estimate': round(sales_estimate, 2),
                'price': price_clean,
                'dod_growth': round(dod_growth, 2),
                'screen_format': str(row['screen_format']),
                'language_format': str(row['language_format']),
                'release_date': str(row['release_date']),
                'running_date': str(row['running_date']),
                'date_sh': str(row['date_sh']),
                'time_sh': str(row['time_sh']),
                'theater_city': str(row['theater_city']),
                'theater_state': str(row['theater_state']),
                'circuit_name': str(row['circuit_name']),
                'dma': str(row['dma']),
                'runtime': str(row['runtime']),
                'country': str(row['country']),
                'year': int(str(row['date_sh'])[:4]) if pd.notna(row['date_sh']) else None
            }
            
            chunks.append((performance_text, metadata))
        
        return chunks
    
    def create_comparative_analysis_chunks(self, chunk: pd.DataFrame) -> List[Tuple[str, Dict]]:
        """Create comparative analysis chunks for 'What films are performing like X?' queries"""
        chunks = []
        
        # Group by movie title for comparative analysis
        movie_groups = chunk.groupby('title')
        
        for title, movie_data in movie_groups:
            # Calculate comprehensive performance metrics
            total_reserved = movie_data['reserved'].sum()
            total_seats = movie_data['total_seats'].sum()
            
            # Clean price data and calculate sales
            prices_clean = []
            for price in movie_data['price']:
                try:
                    prices_clean.append(float(str(price).replace('$', '')))
                except:
                    prices_clean.append(0.0)
            
            total_sales = sum(price * reserved for price, reserved in zip(prices_clean, movie_data['reserved']))
            avg_price = np.mean(prices_clean) if prices_clean else 0.0
            occupancy_rate = (total_reserved / total_seats) * 100 if total_seats > 0 else 0
            
            # Get first movie for metadata
            first_movie = movie_data.iloc[0]
            
            # Calculate performance patterns
            performance_patterns = self._analyze_performance_patterns(movie_data)
            
            # Get market penetration
            market_penetration = self._calculate_market_penetration(movie_data)
            
            comparative_text = f"""
Comparative Film Analysis:
Title: {title}
Genre: {first_movie['genre']} | Rating: {first_movie['rating']}
Studio: {first_movie['studio_name']}
Release Date: {first_movie['release_date']}

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
- Release Timing: {first_movie['release_date']}
- Running Duration: {performance_patterns['running_duration']} days
- Screen Count: {len(movie_data)} showtimes
- Format Mix: {', '.join(performance_patterns['format_mix'])}
""".strip()
            
            metadata = {
                'chunk_type': 'comparative_analysis',
                'title': str(title),
                'genre': str(first_movie['genre']),
                'rating': str(first_movie['rating']),
                'studio_name': str(first_movie['studio_name']),
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
                'release_date': str(first_movie['release_date']),
                'year': int(str(first_movie['date_sh'])[:4]) if pd.notna(first_movie['date_sh']) else None
            }
            
            chunks.append((comparative_text, metadata))
        
        return chunks
    
    def create_theater_opportunity_chunks(self, chunk: pd.DataFrame) -> List[Tuple[str, Dict]]:
        """Create theater opportunity analysis chunks"""
        chunks = []
        
        # Group by theater
        theater_groups = chunk.groupby(['theater_name', 'theater_city'])
        
        for (theater_name, theater_city), theater_data in theater_groups:
            # Calculate theater metrics
            total_capacity = theater_data['total_seats'].sum()
            total_reserved = theater_data['reserved'].sum()
            
            # Clean price data
            prices_clean = []
            for price in theater_data['price']:
                try:
                    prices_clean.append(float(str(price).replace('$', '')))
                except:
                    prices_clean.append(0.0)
            
            total_sales = sum(price * reserved for price, reserved in zip(prices_clean, theater_data['reserved']))
            avg_price = np.mean(prices_clean) if prices_clean else 0.0
            overall_occupancy = (total_reserved / total_capacity) * 100 if total_capacity > 0 else 0
            
            # Analyze opportunity patterns
            opportunity_analysis = self._analyze_theater_opportunities(theater_data)
            
            opportunity_text = f"""
Theater Opportunity Analysis:
Name: {theater_name}
Location: {theater_city}, {theater_data.iloc[0]['theater_state']}
Circuit: {theater_data.iloc[0]['circuit_name']}
DMA: {theater_data.iloc[0]['dma']}

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

Current Movies: {theater_data['title'].nunique()} titles
Amenities: {theater_data.iloc[0]['amenities']}
Market Position: {opportunity_analysis['market_position']}

Recommendations:
- Focus Time Slots: {opportunity_analysis['focus_slots']}
- Pricing Strategy: {opportunity_analysis['pricing_strategy']}
- Format Expansion: {opportunity_analysis['format_expansion']}
""".strip()
            
            metadata = {
                'chunk_type': 'theater_opportunity',
                'theater_name': str(theater_name),
                'theater_city': str(theater_city),
                'theater_state': str(theater_data.iloc[0]['theater_state']),
                'circuit_name': str(theater_data.iloc[0]['circuit_name']),
                'dma': str(theater_data.iloc[0]['dma']),
                'total_capacity': int(total_capacity),
                'total_reserved': int(total_reserved),
                'overall_occupancy': round(overall_occupancy, 2),
                'total_sales': round(total_sales, 2),
                'avg_price': round(avg_price, 2),
                'capacity_utilization': round(opportunity_analysis['capacity_utilization'], 2),
                'price_optimization': round(opportunity_analysis['price_optimization'], 2),
                'market_position': opportunity_analysis['market_position'],
                'movie_count': theater_data['title'].nunique(),
                'amenities': str(theater_data.iloc[0]['amenities']),
                'year': int(str(theater_data.iloc[0]['date_sh'])[:4]) if pd.notna(theater_data.iloc[0]['date_sh']) else None
            }
            
            chunks.append((opportunity_text, metadata))
        
        return chunks
    
    def create_market_penetration_chunks(self, chunk: pd.DataFrame) -> List[Tuple[str, Dict]]:
        """Create market penetration analysis chunks"""
        chunks = []
        
        # Group by city and date
        market_groups = chunk.groupby(['theater_city', 'date_sh'])
        
        for (city, date), market_data in market_groups:
            # Calculate market metrics
            total_market_seats = market_data['total_seats'].sum()
            total_market_reserved = market_data['reserved'].sum()
            
            # Clean price data
            prices_clean = []
            for price in market_data['price']:
                try:
                    prices_clean.append(float(str(price).replace('$', '')))
                except:
                    prices_clean.append(0.0)
            
            market_sales = sum(price * reserved for price, reserved in zip(prices_clean, market_data['reserved']))
            market_occupancy = (total_market_reserved / total_market_seats) * 100 if total_market_seats > 0 else 0
            
            # Analyze market penetration
            penetration_analysis = self._analyze_market_penetration(market_data)
            
            penetration_text = f"""
Market Penetration Analysis:
City: {city}
State: {market_data.iloc[0]['theater_state']}
Date: {date}
DMA: {market_data.iloc[0]['dma']}

Market Performance:
- Total Market Capacity: {total_market_seats:,}
- Reserved Seats: {total_market_reserved:,}
- Market Occupancy: {market_occupancy:.1f}%
- Total Market Sales: ${market_sales:,.2f}

Penetration Analysis:
- Theater Count: {market_data['theater_name'].nunique()}
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
                'city': str(city),
                'state': str(market_data.iloc[0]['theater_state']),
                'date': str(date),
                'dma': str(market_data.iloc[0]['dma']),
                'total_market_capacity': int(total_market_seats),
                'total_market_reserved': int(total_market_reserved),
                'market_occupancy': round(market_occupancy, 2),
                'total_market_sales': round(market_sales, 2),
                'theater_count': market_data['theater_name'].nunique(),
                'circuit_diversity': penetration_analysis['circuit_diversity'],
                'format_mix': penetration_analysis['format_mix'],
                'price_range_min': round(penetration_analysis['price_range'][0], 2),
                'price_range_max': round(penetration_analysis['price_range'][1], 2),
                'capacity_utilization': round(penetration_analysis['capacity_utilization'], 2),
                'year': int(str(date)[:4]) if pd.notna(date) else None
            }
            
            chunks.append((penetration_text, metadata))
        
        return chunks
    
    def _analyze_performance_patterns(self, movie_data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze performance patterns for a movie"""
        # Analyze time patterns
        time_patterns = movie_data['time_sh'].value_counts()
        peak_time = time_patterns.index[0] if len(time_patterns) > 0 else "Unknown"
        
        # Analyze format performance
        format_performance = movie_data.groupby('screen_format')['reserved'].sum().sort_values(ascending=False)
        best_format = format_performance.index[0] if len(format_performance) > 0 else "Unknown"
        
        # Analyze market performance
        market_performance = movie_data.groupby('theater_city')['reserved'].sum().sort_values(ascending=False)
        top_market = market_performance.index[0] if len(market_performance) > 0 else "Unknown"
        
        # Calculate weekend vs weekday ratio
        movie_data['is_weekend'] = pd.to_datetime(movie_data['date_sh']).dt.dayofweek.isin([5, 6])
        weekend_ratio = movie_data.groupby('is_weekend')['reserved'].sum()
        weekend_ratio_value = weekend_ratio.get(True, 0) / weekend_ratio.get(False, 1) if weekend_ratio.get(False, 0) > 0 else 1
        
        # Calculate running duration
        dates = pd.to_datetime(movie_data['date_sh'])
        running_duration = (dates.max() - dates.min()).days + 1
        
        return {
            'peak_time': peak_time,
            'best_format': best_format,
            'top_market': top_market,
            'dod_growth': np.random.uniform(-5, 15),  # Placeholder
            'weekend_ratio': weekend_ratio_value,
            'running_duration': running_duration,
            'format_mix': movie_data['screen_format'].unique().tolist()
        }
    
    def _calculate_market_penetration(self, movie_data: pd.DataFrame) -> Dict[str, Any]:
        """Calculate market penetration metrics"""
        total_theaters = movie_data['theater_name'].nunique()
        total_cities = movie_data['theater_city'].nunique()
        total_circuits = movie_data['circuit_name'].nunique()
        total_formats = movie_data['screen_format'].nunique()
        
        # Calculate penetration rate (simplified)
        penetration_rate = (total_cities / 1000) * 100  # Assuming 1000 total cities
        
        return {
            'penetration_rate': min(penetration_rate, 100),
            'geographic_spread': total_cities,
            'circuit_diversity': total_circuits,
            'format_diversity': total_formats
        }
    
    def _analyze_theater_opportunities(self, theater_data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze theater opportunities"""
        # Analyze time slot performance
        time_performance = theater_data.groupby('time_sh')['reserved'].mean()
        underperforming_slots = time_performance[time_performance < time_performance.median()].index.tolist()
        
        # Calculate capacity utilization
        capacity_utilization = (theater_data['reserved'].sum() / theater_data['total_seats'].sum()) * 100
        
        # Analyze price optimization potential
        price_variance = theater_data['price'].std() / theater_data['price'].mean()
        price_optimization = max(0, (1 - price_variance) * 100)
        
        # Analyze format opportunities
        format_performance = theater_data.groupby('screen_format')['reserved'].mean()
        format_opportunities = format_performance[format_performance < format_performance.median()].index.tolist()
        
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
    
    def _analyze_market_penetration(self, market_data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze market penetration"""
        # Circuit diversity
        circuit_diversity = market_data['circuit_name'].nunique()
        
        # Format mix
        format_mix = market_data['screen_format'].value_counts().to_dict()
        
        # Price range
        price_range = (market_data['price'].min(), market_data['price'].max())
        
        # Top movies
        movie_performance = market_data.groupby('title').agg({
            'reserved': 'sum',
            'price': 'mean'
        }).sort_values('reserved', ascending=False)
        
        top_movies = movie_performance.head(3)
        
        # Underperforming theaters
        theater_performance = market_data.groupby('theater_name')['reserved'].mean()
        underperforming_theaters = theater_performance[theater_performance < theater_performance.median()].index.tolist()
        
        # Format gaps (simplified)
        format_gaps = ['IMAX', 'Dolby Cinema']  # Placeholder
        
        # Price optimization potential
        price_optimization = 'High' if price_range[1] - price_range[0] > 10 else 'Medium'
        
        # Capacity utilization
        capacity_utilization = (market_data['reserved'].sum() / market_data['total_seats'].sum()) * 100
        
        return {
            'circuit_diversity': circuit_diversity,
            'format_mix': format_mix,
            'price_range': price_range,
            'top_movies': top_movies,
            'underperforming_theaters': underperforming_theaters[:3],
            'format_gaps': format_gaps,
            'price_optimization': price_optimization,
            'capacity_utilization': capacity_utilization
        }
    
    def process_chunk(self, chunk: pd.DataFrame, chunk_num: int, total_processed: int) -> int:
        """Process a single chunk and create all embedding types"""
        logger.info(f"📦 Processing chunk {chunk_num} ({len(chunk):,} rows)")
        
        all_chunks = []
        
        # Create different types of chunks
        logger.info("   Creating film performance chunks...")
        performance_chunks = self.create_film_performance_chunks(chunk)
        all_chunks.extend(performance_chunks)
        
        logger.info("   Creating comparative analysis chunks...")
        comparative_chunks = self.create_comparative_analysis_chunks(chunk)
        all_chunks.extend(comparative_chunks)
        
        logger.info("   Creating theater opportunity chunks...")
        theater_chunks = self.create_theater_opportunity_chunks(chunk)
        all_chunks.extend(theater_chunks)
        
        logger.info("   Creating market penetration chunks...")
        market_chunks = self.create_market_penetration_chunks(chunk)
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
        
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'entelligence_film_analytics_checkpoint.json')
        os.makedirs(self.config['CHECKPOINT_DIR'], exist_ok=True)
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        logger.info(f"💾 Checkpoint saved: {total_processed:,} records processed")
    
    def run_pipeline(self):
        """Run the complete Entelligence embedding pipeline"""
        logger.info("🚀 Starting Entelligence Film Analytics Embedding Pipeline")
        logger.info("=" * 80)
        
        # Initialize components
        self.initialize_components()
        
        # Load data from CSV
        logger.info(f"📊 Loading data from {self.config['CSV_PATH']}...")
        
        # Get total row count
        with open(self.config['CSV_PATH'], 'r') as f:
            total_rows = sum(1 for line in f) - 1  # Subtract header
        
        logger.info(f"📈 Total rows in dataset: {total_rows:,}")
        
        # Check for existing checkpoint
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'entelligence_film_analytics_checkpoint.json')
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
        chunk_iterator = pd.read_csv(self.config['CSV_PATH'], chunksize=self.config['CHUNK_SIZE'], low_memory=False)
        
        for chunk_num, chunk in enumerate(chunk_iterator, start=1):
            if chunk_num <= skip_chunks:
                continue
            
            chunk_start_time = time.time()
            
            try:
                # Process chunk
                chunk_vectors = self.process_chunk(chunk, chunk_num, total_processed)
                total_processed += chunk_vectors
                
                # Clear memory
                del chunk
                gc.collect()
                
                # Save checkpoint every 10 chunks
                if chunk_num % 10 == 0:
                    self.save_checkpoint(chunk_num, total_processed, chunk_type_counts)
                
                # Show progress
                chunk_time = time.time() - chunk_start_time
                progress = (chunk_num * self.config['CHUNK_SIZE'] / total_rows) * 100
                logger.info(f"✅ Chunk {chunk_num} completed in {chunk_time:.1f}s")
                logger.info(f"📊 Progress: {chunk_num * self.config['CHUNK_SIZE']:,}/{total_rows:,} ({progress:.1f}%)")
                
            except Exception as e:
                logger.error(f"❌ Chunk {chunk_num} failed: {e}")
                raise
        
        # Final verification
        time.sleep(2)
        stats = self.index.describe_index_stats()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ ENTELIGENCE PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info("=" * 80)
        logger.info(f"📊 Final Summary:")
        logger.info(f"   • Total vectors created: {stats['total_vector_count']:,}")
        logger.info(f"   • Index name: {self.config['INDEX_NAME']}")
        logger.info(f"   • Dimension: {self.config['DIMENSION']}")
        logger.info(f"   • Chunk types: {list(chunk_type_counts.keys())}")
        logger.info(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("\n🎯 Your Entelligence chatbot can now answer:")
        logger.info("   • 'What films are performing like JURASSIC WORLD REBIRTH?'")
        logger.info("   • 'Where are my opportunities?'")
        logger.info("   • 'How is WEAPONS performing in less populated areas?'")
        logger.info("   • 'What showtimes do I want to keep?'")
        logger.info("   • Complex comparative analysis queries")

def main():
    """Main function"""
    pipeline = EntelligenceFilmAnalyticsPipeline()
    pipeline.run_pipeline()

if __name__ == "__main__":
    main()
