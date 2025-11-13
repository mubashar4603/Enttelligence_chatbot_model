#!/usr/bin/env python3
"""
Precision Entelligence System for processing Movie data and creating embeddings
"""

import numpy as np
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from django.conf import settings
from movies.models import Movie
from tqdm import tqdm
import logging
import time
import gc

logger = logging.getLogger(__name__)


class PrecisionEntelligenceSystem:
    """Precision pipeline for creating embeddings from Movie models"""
    
    def __init__(self, csv_path=None):
        """Initialize the precision pipeline
        
        Args:
            csv_path: Optional path to CSV file. If provided, only processes movies from this CSV.
        """
        self.config = {
            'CHUNK_SIZE': 50000,
            'BATCH_SIZE': 256,
            'INDEX_NAME': "customer-database-vectors",
            'DIMENSION': 768,
            'EMBEDDING_MODEL': "BAAI/bge-base-en-v1.5",
            'CHECKPOINT_INTERVAL': 2
        }
        
        self.csv_path = csv_path
        self.model = None
        self.index = None
        self.processed_count = 0
        self.csv_titles = None
        self.csv_date_range = None
        self.csv_unique_keys = None  # Store unique identifiers from CSV
        
    def initialize_components(self):
        """Initialize Pinecone and embedding model"""
        logger.info("🔌 Initializing components...")
        
        try:
            # Initialize Pinecone
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            self.index = pc.Index(self.config['INDEX_NAME'])
            logger.info(f"✅ Connected to Pinecone index: {self.config['INDEX_NAME']}")
            
            # Initialize embedding model
            self.model = SentenceTransformer(self.config['EMBEDDING_MODEL'])
            logger.info(f"✅ Loaded embedding model: {self.config['EMBEDDING_MODEL']}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize components: {e}")
            raise
    
    def create_movie_text(self, movie):
        """Create text representation of a movie record"""
        try:
            occupancy_rate = movie.get_occupancy_rate() if hasattr(movie, 'get_occupancy_rate') else 0
            sales_estimate = float(movie.price) * movie.reserved if movie.price and movie.reserved else 0
            
            text = f"""
Movie: {movie.title}
Genre: {movie.genre} | Rating: {movie.rating}
Studio: {movie.studio_name}
Release Date: {movie.release_date}
Runtime: {movie.runtime} minutes

Showtime Details:
Date: {movie.date_sh} | Time: {movie.time_sh}
Theater: {movie.theater_name}
Location: {movie.theater_city}, {movie.theater_state}
Circuit: {movie.circuit_name}
Auditorium: {movie.auditorium}
Format: {movie.screen_format} | {movie.movie_format} | {movie.language_format}

Performance Metrics:
Price: ${float(movie.price):.2f}
Reserved Seats: {movie.reserved:,}
Total Seats: {movie.total_seats:,}
Available Seats: {movie.available:,}
Occupancy Rate: {occupancy_rate:.2f}%
Sales Estimate: ${sales_estimate:,.2f}

Theater Details:
Address: {movie.theater_address}
Zip Code: {movie.theater_zip}
DMA: {movie.dma or 'N/A'}
Amenities: {movie.amenities or 'N/A'}
""".strip()
            
            return text
        except Exception as e:
            logger.warning(f"⚠️  Error creating text for movie {movie.id}: {e}")
            return None
    
    def create_metadata(self, movie):
        """Create metadata for a movie record"""
        try:
            occupancy_rate = movie.get_occupancy_rate() if hasattr(movie, 'get_occupancy_rate') else 0
            sales_estimate = float(movie.price) * movie.reserved if movie.price and movie.reserved else 0
            
            metadata = {
                'chunk_type': 'movie_showtime',
                'movie_id': int(movie.id),
                'title': str(movie.title),
                'genre': str(movie.genre),
                'rating': str(movie.rating),
                'studio_name': str(movie.studio_name),
                'release_date': str(movie.release_date),
                'runtime': int(movie.runtime) if movie.runtime else None,
                'theater_name': str(movie.theater_name),
                'theater_city': str(movie.theater_city),
                'theater_state': str(movie.theater_state),
                'circuit_name': str(movie.circuit_name),
                'date_sh': str(movie.date_sh),
                'time_sh': str(movie.time_sh),
                'price': float(movie.price) if movie.price else 0.0,
                'reserved': int(movie.reserved),
                'total_seats': int(movie.total_seats),
                'occupancy_rate': round(occupancy_rate, 2),
                'sales_estimate': round(sales_estimate, 2),
                'year': movie.date_sh.year if movie.date_sh else None
            }
            
            return metadata
        except Exception as e:
            logger.warning(f"⚠️  Error creating metadata for movie {movie.id}: {e}")
            return None
    
    def convert_numpy_types(self, obj):
        """Convert numpy types to Python native types for Pinecone compatibility"""
        if isinstance(obj, dict):
            return {key: self.convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_numpy_types(item) for item in obj]
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj
    
    def upload_vectors(self, embeddings, metadata_list, start_idx):
        """Upload vectors to Pinecone"""
        vectors = []
        for i, (embedding, metadata) in enumerate(zip(embeddings, metadata_list)):
            if metadata is None:
                continue
                
            vector_id = f"movie_{metadata.get('movie_id', start_idx + i)}_{start_idx + i}"
            clean_metadata = self.convert_numpy_types(metadata)
            
            vectors.append({
                "id": vector_id,
                "values": embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
                "metadata": clean_metadata
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
                        time.sleep(wait_time)
                    else:
                        logger.error(f"     ❌ Batch failed after 3 attempts!")
                        raise e
            
            time.sleep(0.1)  # Rate limiting
    
    def process_chunk(self, movies, chunk_num):
        """Process a chunk of movies"""
        logger.info(f"📦 Processing chunk {chunk_num} ({len(movies):,} movies)")
        
        # Create texts and metadata
        texts = []
        metadata_list = []
        
        for movie in tqdm(movies, desc="   Creating texts"):
            text = self.create_movie_text(movie)
            metadata = self.create_metadata(movie)
            
            if text and metadata:
                texts.append(text)
                metadata_list.append(metadata)
        
        if not texts:
            logger.warning(f"   ⚠️  No valid texts created for chunk {chunk_num}")
            return 0
        
        # Generate embeddings
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
        self.upload_vectors(embeddings, metadata_list, self.processed_count)
        
        processed = len(texts)
        self.processed_count += processed
        return processed
    
    def load_csv_identifiers(self):
        """Load movie identifiers from CSV to filter which movies to process"""
        if not self.csv_path:
            return None
        
        import pandas as pd
        import os
        
        if not os.path.exists(self.csv_path):
            logger.warning(f"⚠️  CSV file not found: {self.csv_path}")
            return None
        
        logger.info(f"📖 Reading CSV file to identify movies: {self.csv_path}")
        try:
            # Create set to store unique identifiers (theater_id + date_sh + time_sh + title + auditorium)
            self.csv_unique_keys = set()
            self.csv_titles = set()
            
            # Read CSV in chunks to build unique identifier set
            chunk_size = 50000
            total_rows = sum(1 for _ in open(self.csv_path)) - 1
            logger.info(f"   CSV has {total_rows:,} rows, reading to build unique identifiers...")
            
            for chunk_num, chunk in enumerate(pd.read_csv(self.csv_path, chunksize=chunk_size, low_memory=False), 1):
                # Create unique keys from CSV records
                # Use: theater_id + date_sh + time_sh + title + auditorium as unique identifier
                chunk['date_sh'] = pd.to_datetime(chunk['date_sh'], errors='coerce')
                chunk['time_sh'] = pd.to_datetime(chunk['time_sh'], errors='coerce').dt.time
                
                # Create unique key for each row
                for idx, row in chunk.iterrows():
                    try:
                        theater_id = str(row.get('theater_id', '')).strip()
                        date_sh = row.get('date_sh')
                        time_sh = row.get('time_sh')
                        title = str(row.get('title', '')).strip()
                        auditorium = str(row.get('auditorium', '')).strip()
                        
                        if pd.notna(date_sh) and pd.notna(time_sh) and theater_id and title:
                            # Create unique key: theater_id|date|time|title|auditorium
                            unique_key = f"{theater_id}|{date_sh.date()}|{time_sh}|{title}|{auditorium}"
                            self.csv_unique_keys.add(unique_key)
                            
                            # Also track titles
                            if title:
                                self.csv_titles.add(title)
                    except Exception as e:
                        logger.warning(f"   ⚠️  Skipping row {idx} in chunk {chunk_num}: {e}")
                        continue
                
                if chunk_num % 10 == 0:
                    logger.info(f"   Processed {chunk_num * chunk_size:,} rows, found {len(self.csv_unique_keys):,} unique records so far...")
            
            # Get date range from the unique keys if we have them
            if self.csv_unique_keys:
                # Extract dates from keys
                dates = []
                for key in list(self.csv_unique_keys)[:1000]:  # Sample first 1000 to get date range
                    try:
                        parts = key.split('|')
                        if len(parts) >= 2:
                            date_str = parts[1]
                            dates.append(pd.to_datetime(date_str))
                    except:
                        continue
                
                if dates:
                    self.csv_date_range = (min(dates), max(dates))
                    logger.info(f"   Date range: {self.csv_date_range[0]} to {self.csv_date_range[1]}")
            
            logger.info(f"   Found {len(self.csv_titles)} unique titles")
            logger.info(f"   Found {len(self.csv_unique_keys):,} unique showtime records in CSV")
            
            return True
        except Exception as e:
            logger.error(f"❌ Error reading CSV: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def get_movie_queryset(self):
        """Get queryset of movies to process (filtered by CSV if provided)"""
        if self.csv_path and self.csv_unique_keys:
            # Use exact matching with unique keys from CSV
            from django.db.models import Q
            
            # First filter by title and date range to narrow down
            queryset = Movie.objects.filter(title__in=list(self.csv_titles))
            
            if self.csv_date_range:
                queryset = queryset.filter(
                    date_sh__gte=self.csv_date_range[0].date(),
                    date_sh__lte=self.csv_date_range[1].date()
                )
            
            # Now filter to only exact matches from CSV
            matching_ids = []
            logger.info(f"   Matching {len(self.csv_unique_keys):,} unique CSV records to database...")
            
            # Process in batches to avoid memory issues
            batch_size = 10000
            unique_keys_list = list(self.csv_unique_keys)
            
            for i in range(0, len(unique_keys_list), batch_size):
                batch_keys = unique_keys_list[i:i + batch_size]
                batch_q_objects = []
                
                for key in batch_keys:
                    try:
                        parts = key.split('|')
                        if len(parts) >= 5:
                            theater_id = parts[0]
                            date_str = parts[1]
                            time_str = parts[2]
                            title = parts[3]
                            auditorium = parts[4]
                            
                            # Parse date and time
                            from datetime import datetime
                            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                            time_obj = datetime.strptime(time_str, '%H:%M:%S').time()
                            
                            batch_q_objects.append(
                                Q(theater_id=theater_id) &
                                Q(date_sh=date_obj) &
                                Q(time_sh=time_obj) &
                                Q(title=title) &
                                Q(auditorium=auditorium)
                            )
                    except Exception as e:
                        continue
                
                if batch_q_objects:
                    # Combine Q objects with OR
                    combined_q = batch_q_objects[0]
                    for q in batch_q_objects[1:]:
                        combined_q |= q
                    
                    # Get matching IDs
                    batch_ids = queryset.filter(combined_q).values_list('id', flat=True)
                    matching_ids.extend(list(batch_ids))
                
                if (i // batch_size) % 10 == 0:
                    logger.info(f"   Processed {i + len(batch_keys):,} keys, found {len(matching_ids):,} matches...")
            
            # Final queryset with exact matches
            if matching_ids:
                final_queryset = Movie.objects.filter(id__in=matching_ids)
                logger.info(f"📊 Filtered to {final_queryset.count():,} exact matches from CSV (out of {len(self.csv_unique_keys):,} CSV records)")
                return final_queryset
            else:
                logger.warning("⚠️  No exact matches found!")
                return Movie.objects.none()
        elif self.csv_path and self.csv_titles:
            # Fallback to title + date range filtering if unique keys not available
            queryset = Movie.objects.filter(title__in=list(self.csv_titles))
            if self.csv_date_range:
                queryset = queryset.filter(
                    date_sh__gte=self.csv_date_range[0].date(),
                    date_sh__lte=self.csv_date_range[1].date()
                )
            logger.info(f"📊 Filtered to {queryset.count():,} movies from CSV (using title+date filter)")
            return queryset
        else:
            # Process all movies if no CSV specified
            return Movie.objects.all()
    
    def run_precision_pipeline(self):
        """Run the precision pipeline"""
        logger.info("🚀 Starting Precision Entelligence Pipeline")
        if self.csv_path:
            logger.info(f"📁 Processing only movies from CSV: {self.csv_path}")
        logger.info("=" * 80)
        
        # Initialize components
        self.initialize_components()
        
        # Load CSV identifiers if CSV path provided
        if self.csv_path:
            self.load_csv_identifiers()
        
        # Get queryset of movies to process
        movie_queryset = self.get_movie_queryset()
        total_movies = movie_queryset.count()
        logger.info(f"📊 Total movies to process: {total_movies:,}")
        
        if total_movies == 0:
            logger.warning("⚠️  No movies found to process!")
            return
        
        # Process in chunks
        chunk_size = self.config['CHUNK_SIZE']
        total_chunks = (total_movies + chunk_size - 1) // chunk_size
        
        logger.info(f"📦 Processing in {total_chunks} chunks of {chunk_size:,} movies each")
        logger.info("")
        
        for chunk_num in range(1, total_chunks + 1):
            start_idx = (chunk_num - 1) * chunk_size
            end_idx = start_idx + chunk_size
            
            # Get chunk of movies
            movies = movie_queryset[start_idx:end_idx]
            movies_list = list(movies)
            
            if not movies_list:
                break
            
            # Process chunk
            chunk_start_time = time.time()
            processed = self.process_chunk(movies_list, chunk_num)
            chunk_time = time.time() - chunk_start_time
            
            logger.info(f"✅ Chunk {chunk_num} processed in {chunk_time:.1f}s ({processed:,} vectors)")
            logger.info("")
            
            # Checkpoint every N chunks
            if chunk_num % self.config['CHECKPOINT_INTERVAL'] == 0:
                logger.info(f"💾 Checkpoint: {self.processed_count:,} vectors processed so far")
            
            # Clear memory
            del movies_list
            gc.collect()
        
        # Final stats
        time.sleep(2)
        stats = self.index.describe_index_stats()
        
        logger.info("=" * 80)
        logger.info("✅ PRECISION PIPELINE COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"📊 Final Summary:")
        logger.info(f"   • Total vectors created: {self.processed_count:,}")
        logger.info(f"   • Total vectors in Pinecone: {stats['total_vector_count']:,}")
        logger.info(f"   • Index name: {self.config['INDEX_NAME']}")
        logger.info("=" * 80)

