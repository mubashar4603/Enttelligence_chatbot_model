#!/usr/bin/env python3
"""
Streamlined Entelligence Film Analytics Pipeline
Uses ONLY Pinecone for 7.4M dataset - No FAISS needed
Optimized for comparative analysis queries
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm
import time
import json
from datetime import datetime
import os
import gc
import logging
from typing import Dict, List, Tuple, Any
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from movies.models import Movie
from chat.analytics_models import EmbeddingChunk

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StreamlinedEntelligencePipeline:
    def __init__(self):
        """Initialize the streamlined pipeline - Pinecone only"""
        self.config = self._load_config()
        self.model = None
        self.pc = None
        self.index = None
        
    def _load_config(self):
        """Load configuration"""
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
            logger.info("🚀 Initializing Streamlined Entelligence Pipeline")
            
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
            else:
                logger.info(f"✅ Using existing index: {self.config['INDEX_NAME']}")
            
            self.index = self.pc.Index(self.config['INDEX_NAME'])
            
            logger.info("✅ Components initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize components: {e}")
            raise
    
    def create_comprehensive_chunks(self, chunk: pd.DataFrame) -> List[Tuple[str, Dict]]:
        """Create comprehensive chunks for all query types"""
        chunks = []
        
        # 1. Individual Film Performance Chunks
        logger.info("   Creating individual film performance chunks...")
        for _, row in chunk.iterrows():
            try:
                # Clean price data
                price_clean = float(str(row['price']).replace('$', '')) if pd.notna(row['price']) else 0.0
                
                # Calculate metrics
                sales_estimate = price_clean * row['reserved'] if pd.notna(row['reserved']) else 0
                occupancy_rate = (row['reserved'] / row['total_seats']) * 100 if pd.notna(row['total_seats']) and row['total_seats'] > 0 else 0
                
                performance_text = f"""
Film: {row['title']}
Genre: {row['genre']} | Rating: {row['rating']}
Studio: {row['studio_name']}
Theater: {row['theater_name']} in {row['theater_city']}, {row['theater_state']}
Circuit: {row['circuit_name']}
Date: {row['date_sh']} at {row['time_sh']}
Format: {row['screen_format']} | Language: {row['language_format']}
Price: ${price_clean:.2f} | Reserved: {row['reserved']:,} | Total Seats: {row['total_seats']:,}
Occupancy: {occupancy_rate:.1f}% | Sales: ${sales_estimate:,.2f}
Amenities: {row['amenities']}
DMA: {row['dma']} | Country: {row['country']}
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
                    'price': price_clean,
                    'reserved': int(row['reserved']) if pd.notna(row['reserved']) else 0,
                    'total_seats': int(row['total_seats']) if pd.notna(row['total_seats']) else 0,
                    'occupancy_rate': round(occupancy_rate, 2),
                    'sales_estimate': round(sales_estimate, 2),
                    'amenities': str(row['amenities']),
                    'dma': str(row['dma']),
                    'country': str(row['country']),
                    'year': int(str(row['date_sh'])[:4]) if pd.notna(row['date_sh']) else None
                }
                
                chunks.append((performance_text, metadata))
                
            except Exception as e:
                logger.warning(f"   ⚠️  Skipping row due to error: {e}")
                continue
        
        # 2. Movie Summary Chunks (Grouped by Title)
        logger.info("   Creating movie summary chunks...")
        movie_groups = chunk.groupby('title')
        
        for title, movie_data in movie_groups:
            try:
                # Calculate aggregated metrics
                total_reserved = movie_data['reserved'].sum()
                total_seats = movie_data['total_seats'].sum()
                
                # Clean prices
                prices_clean = []
                for price in movie_data['price']:
                    try:
                        prices_clean.append(float(str(price).replace('$', '')))
                    except:
                        prices_clean.append(0.0)
                
                total_sales = sum(price * reserved for price, reserved in zip(prices_clean, movie_data['reserved']))
                avg_price = np.mean(prices_clean) if prices_clean else 0.0
                overall_occupancy = (total_reserved / total_seats) * 100 if total_seats > 0 else 0
                
                first_movie = movie_data.iloc[0]
                
                summary_text = f"""
Movie Summary: {title}
Genre: {first_movie['genre']} | Rating: {first_movie['rating']}
Studio: {first_movie['studio_name']}
Release Date: {first_movie['release_date']}

Performance Overview:
- Total Reserved Seats: {total_reserved:,}
- Total Capacity: {total_seats:,}
- Overall Occupancy: {overall_occupancy:.1f}%
- Total Sales: ${total_sales:,.2f}
- Average Price: ${avg_price:.2f}

Market Reach:
- Theaters: {movie_data['theater_name'].nunique()}
- Cities: {movie_data['theater_city'].nunique()}
- Circuits: {movie_data['circuit_name'].nunique()}
- Formats: {movie_data['screen_format'].nunique()}

Top Markets: {', '.join(movie_data.groupby('theater_city')['reserved'].sum().sort_values(ascending=False).head(3).index.tolist())}
Top Formats: {', '.join(movie_data['screen_format'].value_counts().head(3).index.tolist())}
""".strip()
                
                metadata = {
                    'chunk_type': 'movie_summary',
                    'title': str(title),
                    'genre': str(first_movie['genre']),
                    'rating': str(first_movie['rating']),
                    'studio_name': str(first_movie['studio_name']),
                    'total_reserved': int(total_reserved),
                    'total_seats': int(total_seats),
                    'overall_occupancy': round(overall_occupancy, 2),
                    'total_sales': round(total_sales, 2),
                    'avg_price': round(avg_price, 2),
                    'theater_count': movie_data['theater_name'].nunique(),
                    'city_count': movie_data['theater_city'].nunique(),
                    'circuit_count': movie_data['circuit_name'].nunique(),
                    'format_count': movie_data['screen_format'].nunique(),
                    'year': int(str(first_movie['date_sh'])[:4]) if pd.notna(first_movie['date_sh']) else None
                }
                
                chunks.append((summary_text, metadata))
                
            except Exception as e:
                logger.warning(f"   ⚠️  Skipping movie group due to error: {e}")
                continue
        
        # 3. Theater Performance Chunks (Grouped by Theater)
        logger.info("   Creating theater performance chunks...")
        theater_groups = chunk.groupby(['theater_name', 'theater_city'])
        
        for (theater_name, theater_city), theater_data in theater_groups:
            try:
                # Calculate theater metrics
                total_capacity = theater_data['total_seats'].sum()
                total_reserved = theater_data['reserved'].sum()
                
                # Clean prices
                prices_clean = []
                for price in theater_data['price']:
                    try:
                        prices_clean.append(float(str(price).replace('$', '')))
                    except:
                        prices_clean.append(0.0)
                
                total_sales = sum(price * reserved for price, reserved in zip(prices_clean, theater_data['reserved']))
                avg_price = np.mean(prices_clean) if prices_clean else 0.0
                overall_occupancy = (total_reserved / total_capacity) * 100 if total_capacity > 0 else 0
                
                theater_text = f"""
Theater: {theater_name}
Location: {theater_city}, {theater_data.iloc[0]['theater_state']}
Circuit: {theater_data.iloc[0]['circuit_name']}
DMA: {theater_data.iloc[0]['dma']}

Performance Metrics:
- Total Capacity: {total_capacity:,} seats
- Reserved Seats: {total_reserved:,} seats
- Overall Occupancy: {overall_occupancy:.1f}%
- Total Sales: ${total_sales:,.2f}
- Average Price: ${avg_price:.2f}

Current Movies: {theater_data['title'].nunique()} titles
Formats Available: {', '.join(theater_data['screen_format'].unique())}
Amenities: {theater_data.iloc[0]['amenities']}

Top Performing Movies:
{chr(10).join([f'- {title}: {data['reserved']:,} seats' for title, data in theater_data.groupby('title')['reserved'].sum().sort_values(ascending=False).head(3).items()])}
""".strip()
                
                metadata = {
                    'chunk_type': 'theater_performance',
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
                    'movie_count': theater_data['title'].nunique(),
                    'amenities': str(theater_data.iloc[0]['amenities']),
                    'year': int(str(theater_data.iloc[0]['date_sh'])[:4]) if pd.notna(theater_data.iloc[0]['date_sh']) else None
                }
                
                chunks.append((theater_text, metadata))
                
            except Exception as e:
                logger.warning(f"   ⚠️  Skipping theater group due to error: {e}")
                continue
        
        logger.info(f"   Created {len(chunks)} total chunks")
        return chunks
    
    def process_chunk(self, chunk: pd.DataFrame, chunk_num: int, total_processed: int) -> int:
        """Process a single chunk and create embeddings"""
        logger.info(f"📦 Processing chunk {chunk_num} ({len(chunk):,} rows)")
        
        # Create comprehensive chunks
        chunks = self.create_comprehensive_chunks(chunk)
        
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
        self.upload_vectors(embeddings, metadata_list, total_processed)
        
        return len(chunks)
    
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
    
    def save_checkpoint(self, chunk_num: int, total_processed: int):
        """Save processing checkpoint"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'chunk_number': chunk_num,
            'total_processed': total_processed
        }
        
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'streamlined_checkpoint.json')
        os.makedirs(self.config['CHECKPOINT_DIR'], exist_ok=True)
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        logger.info(f"💾 Checkpoint saved: {total_processed:,} records processed")
    
    def run_pipeline(self):
        """Run the streamlined pipeline"""
        logger.info("🚀 Starting Streamlined Entelligence Pipeline")
        logger.info("=" * 80)
        
        # Initialize components
        self.initialize_components()
        
        # Load data from CSV
        logger.info(f"📊 Loading data from {self.config['CSV_PATH']}...")
        
        if not os.path.exists(self.config['CSV_PATH']):
            logger.error(f"❌ CSV file not found: {self.config['CSV_PATH']}")
            return
        
        # Get total row count
        with open(self.config['CSV_PATH'], 'r') as f:
            total_rows = sum(1 for line in f) - 1  # Subtract header
        
        logger.info(f"📈 Total rows in dataset: {total_rows:,}")
        
        # Check for existing checkpoint
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'streamlined_checkpoint.json')
        skip_chunks = 0
        total_processed = 0
        
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
                skip_chunks = checkpoint['chunk_number']
                total_processed = checkpoint['total_processed']
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
                    self.save_checkpoint(chunk_num, total_processed)
                
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
        logger.info("✅ STREAMLINED PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info("=" * 80)
        logger.info(f"📊 Final Summary:")
        logger.info(f"   • Total vectors created: {stats['total_vector_count']:,}")
        logger.info(f"   • Index name: {self.config['INDEX_NAME']}")
        logger.info(f"   • Dimension: {self.config['DIMENSION']}")
        logger.info(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("\n🎯 Your chatbot can now answer:")
        logger.info("   • 'What films are performing like JURASSIC WORLD REBIRTH?'")
        logger.info("   • 'Where are my opportunities?'")
        logger.info("   • 'How is WEAPONS performing in less populated areas?'")
        logger.info("   • 'What showtimes do I want to keep?'")

def main():
    """Main function"""
    pipeline = StreamlinedEntelligencePipeline()
    pipeline.run_pipeline()

if __name__ == "__main__":
    main()
