#!/usr/bin/env python3
"""
SCALABLE ENTELIGENCE SYSTEM FOR 100M+ RECORDS
Hybrid approach: Pinecone + FAISS + Smart Sampling
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec
from langchain.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
import logging
from typing import Dict, List, Tuple, Any
import os
import json
from datetime import datetime
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from movies.models import Movie
from chat.analytics_models import EmbeddingChunk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScalableEntelligenceSystem:
    def __init__(self):
        """Initialize scalable system for 100M+ records"""
        self.config = self._load_config()
        self.model = None
        self.pc = None
        self.pinecone_index = None
        self.faiss_index = None
        
    def _load_config(self):
        """Load configuration for scalable system"""
        return {
            # Pinecone settings (for high-value data)
            'PINECONE_API_KEY': "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ",
            'PINECONE_ENVIRONMENT': "us-east-1-aws",
            'PINECONE_INDEX_NAME': "customer-database-vectors",
            'DIMENSION': 768,
            
            # FAISS settings (for local storage)
            'FAISS_INDEX_PATH': "faiss_scalable_index",
            'FAISS_BATCH_SIZE': 10000,
            
            # Embedding settings
            'EMBEDDING_MODEL': "BAAI/bge-base-en-v1.5",
            'BATCH_SIZE': 256,
            
            # Scalability settings
            'MAX_PINECONE_VECTORS': 50000000,  # 50M vectors max for Pinecone
            'SAMPLING_RATIO': 0.1,  # 10% sampling for FAISS
            'CHUNK_SIZE': 50000,  # Larger chunks for efficiency
            
            # Data paths
            'CSV_PATH': "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv",
            'CHECKPOINT_DIR': "checkpoints",
        }
    
    def initialize_components(self):
        """Initialize all components"""
        try:
            logger.info("🚀 Initializing Scalable Entelligence System")
            
            # Initialize embedding model
            logger.info("🤖 Loading embedding model...")
            self.model = SentenceTransformer(self.config['EMBEDDING_MODEL'])
            
            # Initialize Pinecone (for high-value data)
            logger.info("🔌 Connecting to Pinecone...")
            self.pc = Pinecone(api_key=self.config['PINECONE_API_KEY'])
            
            # Create or connect to Pinecone index
            existing_indexes = self.pc.list_indexes().names()
            if self.config['PINECONE_INDEX_NAME'] not in existing_indexes:
                logger.info(f"🆕 Creating Pinecone index: {self.config['PINECONE_INDEX_NAME']}")
                self.pc.create_index(
                    name=self.config['PINECONE_INDEX_NAME'],
                    dimension=self.config['DIMENSION'],
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region=self.config['PINECONE_ENVIRONMENT']
                    )
                )
                while not self.pc.describe_index(self.config['PINECONE_INDEX_NAME']).status['ready']:
                    time.sleep(1)
            
            self.pinecone_index = self.pc.Index(self.config['PINECONE_INDEX_NAME'])
            
            # Initialize FAISS (for local storage)
            logger.info("💾 Initializing FAISS for local storage...")
            self.faiss_index = None  # Will be created during processing
            
            logger.info("✅ Scalable system initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize scalable system: {e}")
            raise
    
    def create_smart_chunks(self, chunk: pd.DataFrame, chunk_num: int) -> Tuple[List[Tuple[str, Dict]], List[Tuple[str, Dict]]]:
        """Create smart chunks with sampling strategy"""
        pinecone_chunks = []
        faiss_chunks = []
        
        # 1. HIGH-VALUE CHUNKS → PINECONE (Always include)
        logger.info("   Creating high-value chunks for Pinecone...")
        
        # Movie summaries (always high-value)
        movie_groups = chunk.groupby('title')
        for title, movie_data in movie_groups:
            if len(movie_data) >= 10:  # Only movies with significant data
                summary_text, metadata = self._create_movie_summary_chunk(title, movie_data)
                pinecone_chunks.append((summary_text, metadata))
        
        # Theater summaries (always high-value)
        theater_groups = chunk.groupby(['theater_name', 'theater_city'])
        for (theater_name, theater_city), theater_data in theater_groups:
            if len(theater_data) >= 5:  # Only theaters with significant data
                theater_text, metadata = self._create_theater_summary_chunk(theater_name, theater_city, theater_data)
                pinecone_chunks.append((theater_text, metadata))
        
        # 2. SAMPLED CHUNKS → FAISS (10% sampling)
        logger.info("   Creating sampled chunks for FAISS...")
        
        # Sample individual records
        sample_size = max(1, int(len(chunk) * self.config['SAMPLING_RATIO']))
        sampled_chunk = chunk.sample(n=sample_size, random_state=42)
        
        for _, row in sampled_chunk.iterrows():
            performance_text, metadata = self._create_performance_chunk(row)
            faiss_chunks.append((performance_text, metadata))
        
        logger.info(f"   Created {len(pinecone_chunks)} Pinecone chunks, {len(faiss_chunks)} FAISS chunks")
        return pinecone_chunks, faiss_chunks
    
    def _create_movie_summary_chunk(self, title: str, movie_data: pd.DataFrame) -> Tuple[str, Dict]:
        """Create movie summary chunk"""
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
        
        return summary_text, metadata
    
    def _create_theater_summary_chunk(self, theater_name: str, theater_city: str, theater_data: pd.DataFrame) -> Tuple[str, Dict]:
        """Create theater summary chunk"""
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
""".strip()
        
        metadata = {
            'chunk_type': 'theater_summary',
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
        
        return theater_text, metadata
    
    def _create_performance_chunk(self, row: pd.Series) -> Tuple[str, Dict]:
        """Create individual performance chunk"""
        try:
            price_clean = float(str(row['price']).replace('$', '')) if pd.notna(row['price']) else 0.0
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
            
            return performance_text, metadata
            
        except Exception as e:
            logger.warning(f"   ⚠️  Skipping row due to error: {e}")
            return None, None
    
    def process_chunk(self, chunk: pd.DataFrame, chunk_num: int, total_processed: int) -> int:
        """Process a single chunk with smart sampling"""
        logger.info(f"📦 Processing chunk {chunk_num} ({len(chunk):,} rows)")
        
        # Create smart chunks
        pinecone_chunks, faiss_chunks = self.create_smart_chunks(chunk, chunk_num)
        
        total_vectors = 0
        
        # Process Pinecone chunks (high-value data)
        if pinecone_chunks:
            logger.info(f"   Processing {len(pinecone_chunks)} Pinecone chunks...")
            texts = [chunk[0] for chunk in pinecone_chunks]
            metadata_list = [chunk[1] for chunk in pinecone_chunks]
            
            embeddings = self.model.encode(
                texts,
                batch_size=self.config['BATCH_SIZE'],
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            
            self.upload_to_pinecone(embeddings, metadata_list, total_processed)
            total_vectors += len(pinecone_chunks)
        
        # Process FAISS chunks (sampled data)
        if faiss_chunks:
            logger.info(f"   Processing {len(faiss_chunks)} FAISS chunks...")
            texts = [chunk[0] for chunk in faiss_chunks]
            metadata_list = [chunk[1] for chunk in faiss_chunks]
            
            embeddings = self.model.encode(
                texts,
                batch_size=self.config['BATCH_SIZE'],
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            
            self.update_faiss_index(texts, embeddings, metadata_list)
            total_vectors += len(faiss_chunks)
        
        return total_vectors
    
    def upload_to_pinecone(self, embeddings: np.ndarray, metadata_list: List[Dict], start_idx: int):
        """Upload vectors to Pinecone"""
        vectors = []
        for i, (embedding, metadata) in enumerate(zip(embeddings, metadata_list)):
            vector_id = f"pinecone_{metadata['chunk_type']}_{start_idx + i}"
            vectors.append({
                "id": vector_id,
                "values": embedding.tolist(),
                "metadata": metadata
            })
        
        # Upload in batches
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            self.pinecone_index.upsert(vectors=batch, timeout=30)
            time.sleep(0.1)
    
    def update_faiss_index(self, texts: List[str], embeddings: np.ndarray, metadata_list: List[Dict]):
        """Update FAISS index with new vectors"""
        try:
            # Create embeddings model for FAISS
            embeddings_model = HuggingFaceEmbeddings(model_name=self.config['EMBEDDING_MODEL'])
            
            if self.faiss_index is None:
                # Create new FAISS index
                self.faiss_index = FAISS.from_embeddings(
                    zip(texts, embeddings), 
                    embeddings_model
                )
            else:
                # Add to existing index
                new_index = FAISS.from_embeddings(
                    zip(texts, embeddings), 
                    embeddings_model
                )
                self.faiss_index.merge_from(new_index)
            
            # Save FAISS index
            self.faiss_index.save_local(self.config['FAISS_INDEX_PATH'])
            
        except Exception as e:
            logger.warning(f"⚠️  FAISS update failed: {e}")
    
    def run_scalable_pipeline(self):
        """Run the scalable pipeline"""
        logger.info("🚀 Starting Scalable Entelligence Pipeline")
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
            total_rows = sum(1 for line in f) - 1
        
        logger.info(f"📈 Total rows in dataset: {total_rows:,}")
        
        # Process data in chunks
        chunk_iterator = pd.read_csv(self.config['CSV_PATH'], chunksize=self.config['CHUNK_SIZE'], low_memory=False)
        
        total_processed = 0
        for chunk_num, chunk in enumerate(chunk_iterator, start=1):
            chunk_start_time = time.time()
            
            try:
                # Process chunk
                chunk_vectors = self.process_chunk(chunk, chunk_num, total_processed)
                total_processed += chunk_vectors
                
                # Clear memory
                del chunk
                
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
        stats = self.pinecone_index.describe_index_stats()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ SCALABLE PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info("=" * 80)
        logger.info(f"📊 Final Summary:")
        logger.info(f"   • Pinecone vectors: {stats['total_vector_count']:,}")
        logger.info(f"   • FAISS vectors: ~{int(total_rows * self.config['SAMPLING_RATIO']):,}")
        logger.info(f"   • Total vectors: ~{stats['total_vector_count'] + int(total_rows * self.config['SAMPLING_RATIO']):,}")
        logger.info(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def main():
    """Main function"""
    pipeline = ScalableEntelligenceSystem()
    pipeline.run_scalable_pipeline()

if __name__ == "__main__":
    main()
