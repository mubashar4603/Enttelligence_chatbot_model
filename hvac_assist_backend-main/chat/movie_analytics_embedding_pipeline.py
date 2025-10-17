#!/usr/bin/env python3
"""
Advanced Movie Performance Analytics Embedding Pipeline
Optimized for 7.4M records with multi-level chunking strategy
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
from django.conf import settings
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MovieAnalyticsEmbeddingPipeline:
    def __init__(self):
        """Initialize the advanced embedding pipeline"""
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
            'DIMENSION': 768,  # Updated to match your Pinecone setup
            
            # Embedding settings
            'EMBEDDING_MODEL': "BAAI/bge-base-en-v1.5",  # 768 dimensions
            'BATCH_SIZE': 256,  # Optimized for 768 dimensions
            
            # Data processing settings
            'CHUNK_SIZE': 25000,  # Smaller chunks for better memory management
            'MAX_RECORDS_2023': 5000000,  # 5M records from 2023
            'MAX_RECORDS_2024': 5000000,  # 5M records from 2024
            
            # Checkpoint settings
            'CHECKPOINT_DIR': "checkpoints",
        }
    
    def initialize_components(self):
        """Initialize embedding model and Pinecone connection"""
        try:
            logger.info("🤖 Loading embedding model...")
            self.model = SentenceTransformer(self.config['EMBEDDING_MODEL'])
            
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
    
    def create_performance_chunks(self, chunk):
        """Create movie performance analysis chunks"""
        chunks = []
        
        for _, row in chunk.iterrows():
            # Calculate performance metrics
            sales_estimate = row['price'] * row['reserved'] if pd.notna(row['price']) and pd.notna(row['reserved']) else 0
            occupancy_rate = (row['reserved'] / row['total_seats']) * 100 if row['total_seats'] > 0 else 0
            
            performance_text = f"""
Movie Performance Analysis:
Title: {row['title']}
Genre: {row['genre']} | Rating: {row['rating']}
Studio: {row['studio_name']}
Release Date: {row['release_date']}
Running Date: {row['running_date']}

Performance Metrics:
- Reserved Seats: {row['reserved']:,}
- Available Seats: {row['available']:,}
- Total Capacity: {row['total_seats']:,}
- Occupancy Rate: {occupancy_rate:.1f}%
- Sales Estimate: ${sales_estimate:,.2f}
- Average Price: ${row['price']:.2f}

Technical Details:
- Screen Format: {row['screen_format']}
- Movie Format: {row['movie_format']}
- Language: {row['language_format']}
- Runtime: {row['runtime']} minutes
- Country: {row['country']}

Showtime Info:
- Date: {row['date_sh']}
- Time: {row['time_sh']}
- Auditorium: {row['auditorium']}
- Seating Type: {row['seating_type']}
""".strip()
            
            metadata = {
                'chunk_type': 'performance',
                'title': str(row['title']),
                'genre': str(row['genre']),
                'rating': str(row['rating']),
                'studio_name': str(row['studio_name']),
                'reserved_seats': int(row['reserved']) if pd.notna(row['reserved']) else 0,
                'total_seats': int(row['total_seats']) if pd.notna(row['total_seats']) else 0,
                'occupancy_rate': round(occupancy_rate, 2),
                'sales_estimate': round(sales_estimate, 2),
                'price': float(row['price']) if pd.notna(row['price']) else 0.0,
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
                'country': str(row['country'])
            }
            
            chunks.append((performance_text, metadata))
        
        return chunks
    
    def create_theater_chunks(self, chunk):
        """Create theater context chunks (grouped by theater)"""
        chunks = []
        
        # Group by theater
        theater_groups = chunk.groupby(['theater_name', 'theater_city'])
        
        for (theater_name, theater_city), theater_data in theater_groups:
            # Calculate theater metrics
            total_capacity = theater_data['total_seats'].sum()
            total_reserved = theater_data['reserved'].sum()
            total_sales = (theater_data['price'] * theater_data['reserved']).sum()
            avg_price = theater_data['price'].mean()
            
            # Get unique movies
            movies = theater_data['title'].unique()
            
            theater_text = f"""
Theater Analysis:
Name: {theater_name}
Location: {theater_city}, {theater_data.iloc[0]['theater_state']} {theater_data.iloc[0]['theater_zip']}
Circuit: {theater_data.iloc[0]['circuit_name']}
Address: {theater_data.iloc[0]['theater_address']}
DMA: {theater_data.iloc[0]['dma']}

Capacity Metrics:
- Total Seats: {total_capacity:,}
- Reserved Seats: {total_reserved:,}
- Overall Occupancy: {(total_reserved/total_capacity)*100:.1f}%
- Total Sales Estimate: ${total_sales:,.2f}
- Average Ticket Price: ${avg_price:.2f}

Current Movies ({len(movies)} titles):
{', '.join(movies[:5])}{'...' if len(movies) > 5 else ''}

Amenities: {theater_data.iloc[0]['amenities']}
""".strip()
            
            metadata = {
                'chunk_type': 'theater',
                'theater_name': str(theater_name),
                'theater_city': str(theater_city),
                'theater_state': str(theater_data.iloc[0]['theater_state']),
                'circuit_name': str(theater_data.iloc[0]['circuit_name']),
                'total_capacity': int(total_capacity),
                'total_reserved': int(total_reserved),
                'overall_occupancy': round((total_reserved/total_capacity)*100, 2),
                'total_sales': round(total_sales, 2),
                'avg_price': round(avg_price, 2),
                'movie_count': len(movies),
                'dma': str(theater_data.iloc[0]['dma']),
                'amenities': str(theater_data.iloc[0]['amenities'])
            }
            
            chunks.append((theater_text, metadata))
        
        return chunks
    
    def create_market_chunks(self, chunk):
        """Create market analysis chunks (grouped by city + date)"""
        chunks = []
        
        # Group by city and date
        market_groups = chunk.groupby(['theater_city', 'date_sh'])
        
        for (city, date), market_data in market_groups:
            # Calculate market metrics
            total_market_seats = market_data['total_seats'].sum()
            total_market_reserved = market_data['reserved'].sum()
            market_sales = (market_data['price'] * market_data['reserved']).sum()
            
            # Get top performing movies
            movie_performance = market_data.groupby('title').agg({
                'reserved': 'sum',
                'price': 'mean',
                'total_seats': 'sum'
            }).sort_values('reserved', ascending=False)
            
            top_movies = movie_performance.head(3)
            
            market_text = f"""
Market Analysis:
City: {city}
Date: {date}
State: {market_data.iloc[0]['theater_state']}

Market Performance:
- Total Market Capacity: {total_market_seats:,}
- Total Reserved Seats: {total_market_reserved:,}
- Market Occupancy: {(total_market_reserved/total_market_seats)*100:.1f}%
- Total Market Sales: ${market_sales:,.2f}

Top Performing Movies:
{chr(10).join([f"- {title}: {data['reserved']:,} seats, ${data['price']:.2f} avg" for title, data in top_movies.iterrows()])}

Competition Analysis:
- Total Movies: {market_data['title'].nunique()}
- Total Theaters: {market_data['theater_name'].nunique()}
- Format Mix: {', '.join(market_data['screen_format'].unique())}
""".strip()
            
            metadata = {
                'chunk_type': 'market',
                'city': str(city),
                'date': str(date),
                'state': str(market_data.iloc[0]['theater_state']),
                'total_market_capacity': int(total_market_seats),
                'total_market_reserved': int(total_market_reserved),
                'market_occupancy': round((total_market_reserved/total_market_seats)*100, 2),
                'total_market_sales': round(market_sales, 2),
                'movie_count': market_data['title'].nunique(),
                'theater_count': market_data['theater_name'].nunique(),
                'top_movies': [title for title in top_movies.index[:3]]
            }
            
            chunks.append((market_text, metadata))
        
        return chunks
    
    def process_chunk(self, chunk, chunk_num, total_processed):
        """Process a single chunk and create all embedding types"""
        logger.info(f"📦 Processing chunk {chunk_num} ({len(chunk):,} rows)")
        
        all_chunks = []
        
        # Create different types of chunks
        logger.info("   Creating performance chunks...")
        performance_chunks = self.create_performance_chunks(chunk)
        all_chunks.extend(performance_chunks)
        
        logger.info("   Creating theater chunks...")
        theater_chunks = self.create_theater_chunks(chunk)
        all_chunks.extend(theater_chunks)
        
        logger.info("   Creating market chunks...")
        market_chunks = self.create_market_chunks(chunk)
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
        
        return len(all_chunks)
    
    def upload_vectors(self, embeddings, metadata_list, start_idx):
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
    
    def save_checkpoint(self, chunk_num, total_processed, chunk_type_counts):
        """Save processing checkpoint"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'chunk_number': chunk_num,
            'total_processed': total_processed,
            'chunk_type_counts': chunk_type_counts
        }
        
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'movie_analytics_checkpoint.json')
        os.makedirs(self.config['CHECKPOINT_DIR'], exist_ok=True)
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        logger.info(f"💾 Checkpoint saved: {total_processed:,} records processed")
    
    def run_pipeline(self, csv_path):
        """Run the complete embedding pipeline"""
        logger.info("🚀 Starting Movie Analytics Embedding Pipeline")
        logger.info("=" * 60)
        
        # Initialize components
        self.initialize_components()
        
        # Get total rows for progress tracking
        logger.info("📊 Counting total rows...")
        total_rows = sum(1 for _ in open(csv_path)) - 1  # Subtract header
        logger.info(f"📈 Total rows to process: {total_rows:,}")
        
        # Check for existing checkpoint
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'movie_analytics_checkpoint.json')
        skip_chunks = 0
        total_processed = 0
        chunk_type_counts = {'performance': 0, 'theater': 0, 'market': 0}
        
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
                skip_chunks = checkpoint['chunk_number']
                total_processed = checkpoint['total_processed']
                chunk_type_counts = checkpoint.get('chunk_type_counts', chunk_type_counts)
                logger.info(f"📂 Resuming from checkpoint: chunk {skip_chunks}, {total_processed:,} records")
        
        # Process data in chunks
        chunk_iterator = pd.read_csv(csv_path, chunksize=self.config['CHUNK_SIZE'], low_memory=False)
        
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
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info("=" * 60)
        logger.info(f"📊 Final Summary:")
        logger.info(f"   • Total vectors created: {stats['total_vector_count']:,}")
        logger.info(f"   • Index name: {self.config['INDEX_NAME']}")
        logger.info(f"   • Dimension: {self.config['DIMENSION']}")
        logger.info(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def main():
    """Main function"""
    pipeline = MovieAnalyticsEmbeddingPipeline()
    csv_path = "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv"
    pipeline.run_pipeline(csv_path)

if __name__ == "__main__":
    main()
