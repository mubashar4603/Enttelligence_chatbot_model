#!/usr/bin/env python3
"""
Script to complete the missing 35K+ records from the precision pipeline
This script processes the remaining data from chunk 150 onwards
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm
import time
import json
import os
import gc
from datetime import datetime
from django.conf import settings
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MissingDataCompleter:
    def __init__(self):
        """Initialize the missing data completer"""
        self.config = {
            'CSV_PATH': "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv",
            'CHUNK_SIZE': 50000,
            'BATCH_SIZE': 256,
            'INDEX_NAME': "customer-database-vectors",
            'DIMENSION': 768,
            'EMBEDDING_MODEL': "BAAI/bge-base-en-v1.5",
            'PRECISION_DECIMALS': 2,
            'VALIDATION_THRESHOLD': 0.001,
            'CHECKPOINT_INTERVAL': 2
        }
        
        self.model = None
        self.index = None
        
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
    
    def validate_data_integrity(self, chunk: pd.DataFrame) -> dict:
        """Validate data integrity for precision processing"""
        validation_results = {
            'total_records': len(chunk),
            'valid_records': 0,
            'invalid_records': 0,
            'price_errors': 0,
            'seat_errors': 0,
            'date_errors': 0
        }
        
        for idx, row in chunk.iterrows():
            is_valid = True
            
            # Check price validity
            try:
                if pd.notna(row['price']):
                    price_str = str(row['price']).replace('$', '').replace(',', '').strip()
                    float(price_str)
            except (ValueError, TypeError):
                validation_results['price_errors'] += 1
                is_valid = False
            
            # Check seat validity
            try:
                if pd.notna(row['reserved']) and pd.notna(row['total_seats']):
                    reserved = int(row['reserved'])
                    total_seats = int(row['total_seats'])
                    if reserved < 0 or total_seats <= 0 or reserved > total_seats:
                        validation_results['seat_errors'] += 1
                        is_valid = False
            except (ValueError, TypeError):
                validation_results['seat_errors'] += 1
                is_valid = False
            
            # Check date validity
            try:
                if pd.notna(row['date_sh']):
                    pd.to_datetime(row['date_sh'])
            except (ValueError, TypeError):
                validation_results['date_errors'] += 1
                is_valid = False
            
            if is_valid:
                validation_results['valid_records'] += 1
            else:
                validation_results['invalid_records'] += 1
        
        # Calculate precision metrics
        validation_results['precision_metrics'] = {
            'validity_rate': validation_results['valid_records'] / validation_results['total_records'],
            'price_error_rate': validation_results['price_errors'] / validation_results['total_records'],
            'seat_error_rate': validation_results['seat_errors'] / validation_results['total_records'],
            'date_error_rate': validation_results['date_errors'] / validation_results['total_records']
        }
        
        return validation_results
    
    def create_precision_chunks(self, chunk: pd.DataFrame) -> list:
        """Create precision-focused chunks with exact calculations"""
        chunks = []
        
        # Validate data integrity first
        validation = self.validate_data_integrity(chunk)
        
        if validation['precision_metrics']['validity_rate'] < 0.95:
            logger.warning(f"⚠️  Low data validity: {validation['precision_metrics']['validity_rate']:.2%}")
        
        # 1. Individual Film Performance Chunks (Exact Calculations)
        logger.info("   Creating individual film performance chunks...")
        for idx, row in chunk.iterrows():
            try:
                # Precise price calculation - handle dollar signs properly
                price_clean = 0.0
                if pd.notna(row['price']):
                    try:
                        price_str = str(row['price']).replace('$', '').replace(',', '').strip()
                        price_clean = round(float(price_str), self.config['PRECISION_DECIMALS']) if price_str else 0.0
                    except (ValueError, TypeError):
                        price_clean = 0.0
                
                # Precise seat calculations
                reserved = int(row['reserved']) if pd.notna(row['reserved']) else 0
                total_seats = int(row['total_seats']) if pd.notna(row['total_seats']) else 0
                
                # Precise sales calculation
                sales_estimate = round(price_clean * reserved, self.config['PRECISION_DECIMALS'])
                
                # Precise occupancy calculation
                occupancy_rate = round((reserved / total_seats) * 100, self.config['PRECISION_DECIMALS']) if total_seats > 0 else 0.0
                
                # Create precise text with exact values
                performance_text = f"""
Film Performance Record:
Title: {row['title']}
Genre: {row['genre']} | Rating: {row['rating']}
Studio: {row['studio_name']}
Theater: {row['theater_name']}
Location: {row['theater_city']}, {row['theater_state']}
Circuit: {row['circuit_name']}
Date: {row['date_sh']} | Time: {row['time_sh']}
Format: {row['screen_format']} | Language: {row['language_format']}

Exact Calculations:
Price: ${price_clean:.2f}
Reserved Seats: {reserved:,}
Total Seats: {total_seats:,}
Occupancy Rate: {occupancy_rate:.2f}%
Sales Estimate: ${sales_estimate:.2f}

Technical Details:
Auditorium: {row['auditorium']}
Amenities: {row['amenities']}
DMA: {row['dma']}
Country: {row['country']}
Runtime: {row['runtime']} minutes
""".strip()
                
                metadata = {
                    'chunk_type': 'film_performance',
                    'title': str(row['title']),
                    'genre': str(row['genre']),
                    'rating': str(row['rating']),
                    'studio_name': str(row['studio_name']),
                    'theater_name': str(row['theater_name']),
                    'theater_city': str(row['theater_city']),
                    'theater_state': str(row['theater_state']),
                    'circuit_name': str(row['circuit_name']),
                    'date_sh': str(row['date_sh']),
                    'time_sh': str(row['time_sh']),
                    'screen_format': str(row['screen_format']),
                    'language_format': str(row['language_format']),
                    'auditorium': str(row['auditorium']),
                    'amenities': str(row['amenities']),
                    'dma': str(row['dma']),
                    'country': str(row['country']),
                    'runtime': str(row['runtime']),
                    
                    # Precise numerical values
                    'price': price_clean,
                    'reserved': reserved,
                    'total_seats': total_seats,
                    'occupancy_rate': occupancy_rate,
                    'sales_estimate': sales_estimate,
                    
                    # Validation data
                    'data_validity': validation['precision_metrics']['validity_rate'],
                    'row_index': int(idx),
                    'year': int(str(row['date_sh'])[:4]) if pd.notna(row['date_sh']) else None
                }
                
                chunks.append((performance_text, metadata))
                
            except Exception as e:
                logger.warning(f"   ⚠️  Skipped row {idx} due to error: {e}")
                continue
        
        # 2. Movie Summary Chunks (Aggregated Data)
        logger.info("   Creating movie summary chunks...")
        movie_groups = chunk.groupby('title')
        for title, movie_data in movie_groups:
            if len(movie_data) >= 5:  # Only movies with significant data
                try:
                    # Calculate aggregated metrics
                    total_reserved = movie_data['reserved'].sum()
                    avg_price = movie_data['price'].apply(lambda x: float(str(x).replace('$', '')) if pd.notna(x) else 0.0).mean()
                    total_sales = (movie_data['reserved'] * movie_data['price'].apply(lambda x: float(str(x).replace('$', '')) if pd.notna(x) else 0.0)).sum()
                    theaters_count = movie_data['theater_name'].nunique()
                    
                    summary_text = f"""
Movie Summary: {title}
Genre: {movie_data['genre'].iloc[0]} | Rating: {movie_data['rating'].iloc[0]}
Studio: {movie_data['studio_name'].iloc[0]}

Aggregated Performance:
Total Reserved Seats: {total_reserved:,}
Average Price: ${avg_price:.2f}
Total Sales Estimate: ${total_sales:,.2f}
Theaters Showing: {theaters_count:,}

Release Details:
Release Date: {movie_data['release_date'].iloc[0]}
Runtime: {movie_data['runtime'].iloc[0]} minutes
Country: {movie_data['country'].iloc[0]}
""".strip()
                    
                    metadata = {
                        'chunk_type': 'movie_summary',
                        'title': str(title),
                        'genre': str(movie_data['genre'].iloc[0]),
                        'rating': str(movie_data['rating'].iloc[0]),
                        'studio_name': str(movie_data['studio_name'].iloc[0]),
                        'total_reserved': int(total_reserved),
                        'avg_price': round(avg_price, self.config['PRECISION_DECIMALS']),
                        'total_sales': round(total_sales, self.config['PRECISION_DECIMALS']),
                        'theaters_count': int(theaters_count),
                        'release_date': str(movie_data['release_date'].iloc[0]),
                        'runtime': str(movie_data['runtime'].iloc[0]),
                        'country': str(movie_data['country'].iloc[0]),
                        'data_validity': validation['precision_metrics']['validity_rate']
                    }
                    
                    chunks.append((summary_text, metadata))
                    
                except Exception as e:
                    logger.warning(f"   ⚠️  Skipped movie summary for {title}: {e}")
                    continue
        
        # 3. Theater Performance Chunks
        logger.info("   Creating theater performance chunks...")
        theater_groups = chunk.groupby(['theater_name', 'theater_city'])
        for (theater_name, theater_city), theater_data in theater_groups:
            if len(theater_data) >= 3:  # Only theaters with significant data
                try:
                    total_reserved = theater_data['reserved'].sum()
                    total_seats = theater_data['total_seats'].sum()
                    avg_occupancy = (total_reserved / total_seats * 100) if total_seats > 0 else 0.0
                    movies_count = theater_data['title'].nunique()
                    
                    theater_text = f"""
Theater Performance: {theater_name}
Location: {theater_city}, {theater_data['theater_state'].iloc[0]}
Circuit: {theater_data['circuit_name'].iloc[0]}

Performance Metrics:
Total Reserved Seats: {total_reserved:,}
Total Capacity: {total_seats:,}
Average Occupancy: {avg_occupancy:.2f}%
Movies Showing: {movies_count:,}

Theater Details:
Address: {theater_data['theater_address'].iloc[0]}
Zip Code: {theater_data['theater_zip'].iloc[0]}
Amenities: {theater_data['amenities'].iloc[0]}
DMA: {theater_data['dma'].iloc[0]}
""".strip()
                    
                    metadata = {
                        'chunk_type': 'theater_performance',
                        'theater_name': str(theater_name),
                        'theater_city': str(theater_city),
                        'theater_state': str(theater_data['theater_state'].iloc[0]),
                        'circuit_name': str(theater_data['circuit_name'].iloc[0]),
                        'total_reserved': int(total_reserved),
                        'total_seats': int(total_seats),
                        'avg_occupancy': round(avg_occupancy, self.config['PRECISION_DECIMALS']),
                        'movies_count': int(movies_count),
                        'theater_address': str(theater_data['theater_address'].iloc[0]),
                        'theater_zip': str(theater_data['theater_zip'].iloc[0]),
                        'amenities': str(theater_data['amenities'].iloc[0]),
                        'dma': str(theater_data['dma'].iloc[0]),
                        'data_validity': validation['precision_metrics']['validity_rate']
                    }
                    
                    chunks.append((theater_text, metadata))
                    
                except Exception as e:
                    logger.warning(f"   ⚠️  Skipped theater summary for {theater_name}: {e}")
                    continue
        
        logger.info(f"   Created {len(chunks)} precision chunks")
        return chunks
    
    def process_chunk(self, chunk: pd.DataFrame, chunk_num: int, total_processed: int) -> int:
        """Process a single chunk and create embeddings"""
        logger.info(f"📦 Processing chunk {chunk_num} ({len(chunk):,} rows)")
        
        # Create precision chunks
        chunks = self.create_precision_chunks(chunk)
        
        if not chunks:
            logger.warning(f"   ⚠️  No chunks created for chunk {chunk_num}")
            return 0
        
        # Generate embeddings
        texts = [chunk[0] for chunk in chunks]
        metadata_list = [chunk[1] for chunk in chunks]
        
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
        self.upload_vectors_precision(embeddings, metadata_list, total_processed)
        
        return len(chunks)
    
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

    def upload_vectors_precision(self, embeddings: np.ndarray, metadata_list: list, start_idx: int):
        """Upload vectors to Pinecone with precision"""
        vectors = []
        for i, (embedding, metadata) in enumerate(zip(embeddings, metadata_list)):
            # Use a unique prefix to avoid conflicts with existing vectors
            vector_id = f"missing_{metadata['chunk_type']}_{start_idx + i}"
            
            # Convert numpy types to Python native types
            clean_metadata = self.convert_numpy_types(metadata)
            
            vectors.append({
                "id": vector_id,
                "values": embedding.tolist(),
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
                        logger.info(f"     ⏳ Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"     ❌ Batch failed after 3 attempts!")
                        raise e
            
            time.sleep(0.1)  # Rate limiting
    
    def complete_missing_data(self):
        """Complete the missing data processing"""
        logger.info("🚀 Starting Missing Data Completion")
        logger.info("=" * 80)
        
        # Initialize components
        self.initialize_components()
        
        # Get total row count
        logger.info(f"📊 Loading data from {self.config['CSV_PATH']}...")
        with open(self.config['CSV_PATH'], 'r') as f:
            total_rows = sum(1 for line in f) - 1  # Subtract header
        
        logger.info(f"📈 Total rows in dataset: {total_rows:,}")
        
        # Calculate where to start (chunk 150, since we processed up to chunk 149)
        start_chunk = 150
        start_row = (start_chunk - 1) * self.config['CHUNK_SIZE']
        remaining_rows = total_rows - start_row
        
        logger.info(f"📊 Starting from chunk {start_chunk} (row {start_row:,})")
        logger.info(f"📊 Remaining rows to process: {remaining_rows:,}")
        
        # Read the remaining data using a different approach
        logger.info("📖 Reading remaining data using tail approach...")
        try:
            # Create a temporary file with just the remaining data
            import subprocess
            temp_file = "/tmp/remaining_data.csv"
            
            # First, get the header
            header_cmd = f"head -n 1 {self.config['CSV_PATH']} > {temp_file}"
            subprocess.run(header_cmd, shell=True, check=True)
            
            # Then append the last remaining_rows lines
            tail_cmd = f"tail -n {remaining_rows} {self.config['CSV_PATH']} >> {temp_file}"
            subprocess.run(tail_cmd, shell=True, check=True)
            
            # Read the temporary file
            remaining_data = pd.read_csv(temp_file, low_memory=False)
            
            # Clean up temp file
            os.remove(temp_file)
            
            logger.info(f"📊 Successfully read {len(remaining_data):,} remaining rows")
            logger.info(f"📊 Columns: {list(remaining_data.columns)[:5]}...")  # Show first 5 columns
            
            if len(remaining_data) == 0:
                logger.warning("⚠️  No remaining data to process!")
                return
            
            # Process the remaining data
            chunk_start_time = time.time()
            
            try:
                # Process the remaining data as one chunk
                chunk_vectors = self.process_chunk(remaining_data, start_chunk, 0)
                
                # Clear memory
                del remaining_data
                gc.collect()
                
                # Show progress
                chunk_time = time.time() - chunk_start_time
                logger.info(f"✅ Remaining data processed in {chunk_time:.1f}s")
                logger.info(f"📊 Vectors created: {chunk_vectors:,}")
                
            except Exception as e:
                logger.error(f"❌ Processing remaining data failed: {e}")
                raise
                
        except Exception as e:
            logger.error(f"❌ Failed to read remaining data: {e}")
            raise
        
        # Final verification
        time.sleep(2)
        stats = self.index.describe_index_stats()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ MISSING DATA COMPLETION SUCCESSFUL!")
        logger.info("=" * 80)
        logger.info(f"📊 Final Summary:")
        logger.info(f"   • Additional vectors created: {chunk_vectors:,}")
        logger.info(f"   • Total vectors in Pinecone: {stats['total_vector_count']:,}")
        logger.info(f"   • Index name: {self.config['INDEX_NAME']}")
        logger.info(f"   • Dimension: {self.config['DIMENSION']}")
        logger.info(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)


def main():
    """Main function to run the missing data completion"""
    completer = MissingDataCompleter()
    completer.complete_missing_data()


if __name__ == "__main__":
    main()
