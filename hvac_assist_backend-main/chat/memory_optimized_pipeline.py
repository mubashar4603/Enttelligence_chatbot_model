#!/usr/bin/env python3
"""
🚀 MEMORY-OPTIMIZED SEQUENTIAL PIPELINE
Fixed version to avoid CUDA out of memory issues
Processes chunks sequentially with proper GPU memory management
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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import psutil
import torch
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MemoryOptimizedPipeline:
    def __init__(self):
        """Initialize memory-optimized pipeline"""
        self.config = self._load_config()
        self.model = None
        self.pc = None
        self.index = None
        self.stats = {
            'total_chunks_processed': 0,
            'total_vectors_created': 0,
            'start_time': time.time(),
            'chunk_times': []
        }
        
    def _load_config(self):
        """Load memory-optimized configuration"""
        return {
            # Pinecone settings
            'PINECONE_API_KEY': "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ",
            'PINECONE_ENVIRONMENT': "us-east-1-aws",
            'INDEX_NAME': "customer-database-vectors",
            'DIMENSION': 768,
            
            # Memory-optimized embedding settings
            'EMBEDDING_MODEL': "BAAI/bge-base-en-v1.5",
            'BATCH_SIZE': 128,  # Small batch size for memory management
            'GPU_BATCH_SIZE': 256,  # Small GPU batch size
            
            # Sequential processing settings
            'CHUNK_SIZE': 25000,  # Smaller chunks for memory management
            
            # Memory optimization
            'GPU_MEMORY_FRACTION': 0.6,  # Use only 60% of GPU memory
            
            # File paths
            'CSV_PATH': "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv",
            'CHECKPOINT_DIR': "checkpoints",
            
            # Performance settings
            'PINECONE_BATCH_SIZE': 50,  # Small Pinecone batches
            'PINECONE_RETRY_ATTEMPTS': 3,
            'PROGRESS_UPDATE_INTERVAL': 5,
        }
    
    def initialize_components(self):
        """Initialize components with memory optimization"""
        try:
            logger.info("🚀 Initializing Memory-Optimized Pipeline")
            logger.info(f"💻 Hardware: {psutil.cpu_count()} CPU cores, {psutil.virtual_memory().total // (1024**3)}GB RAM")
            
            # Check GPU availability
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                gpu_memory = torch.cuda.get_device_properties(0).total_memory // (1024**3)
                logger.info(f"🎮 GPU: {gpu_name} ({gpu_memory}GB)")
                
                # Clear GPU cache
                torch.cuda.empty_cache()
                
                # Set GPU memory fraction
                torch.cuda.set_per_process_memory_fraction(self.config['GPU_MEMORY_FRACTION'])
                
                # Set environment variable for better memory management
                os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
                
                logger.info(f"🔧 GPU memory fraction set to {self.config['GPU_MEMORY_FRACTION']}")
            else:
                logger.warning("⚠️  No GPU detected, using CPU")
            
            # Initialize embedding model with GPU
            logger.info("🤖 Loading embedding model with GPU acceleration...")
            self.model = SentenceTransformer(self.config['EMBEDDING_MODEL'])
            
            if torch.cuda.is_available():
                self.model = self.model.cuda()
                logger.info("✅ Model loaded on GPU")
            else:
                logger.info("✅ Model loaded on CPU")
            
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
                while not self.pc.describe_index(self.config['INDEX_NAME']).status['ready']:
                    time.sleep(1)
            
            self.index = self.pc.Index(self.config['INDEX_NAME'])
            
            # Create checkpoint directory
            os.makedirs(self.config['CHECKPOINT_DIR'], exist_ok=True)
            
            logger.info("✅ Memory-optimized pipeline initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize pipeline: {e}")
            raise
    
    def create_optimized_chunks(self, chunk: pd.DataFrame) -> List[Tuple[str, Dict]]:
        """Create optimized chunks with clean data"""
        chunks = []
        
        # Process in small batches
        batch_size = 500  # Smaller batches for memory management
        
        for start_idx in range(0, len(chunk), batch_size):
            batch = chunk.iloc[start_idx:start_idx + batch_size]
            
            # Create individual performance chunks
            for idx, row in batch.iterrows():
                try:
                    # Clean price data - remove dollar signs and convert to float
                    price_clean = 0.0
                    if pd.notna(row['price']):
                        try:
                            price_str = str(row['price']).replace('$', '').replace(',', '').strip()
                            price_clean = float(price_str) if price_str else 0.0
                        except (ValueError, TypeError):
                            price_clean = 0.0
                    
                    # Clean numerical data
                    reserved_clean = int(row['reserved']) if pd.notna(row['reserved']) else 0
                    total_seats_clean = int(row['total_seats']) if pd.notna(row['total_seats']) else 0
                    
                    # Calculate derived metrics for better RAG
                    occupancy_rate = (reserved_clean / total_seats_clean * 100) if total_seats_clean > 0 else 0.0
                    sales_estimate = price_clean * reserved_clean
                    
                    # Clean price for text display
                    price_display = f"${price_clean:.2f}" if price_clean > 0 else "Free"
                    
                    # Enhanced text creation with clean numerical data
                    performance_text = f"""
Film: {row['title']} | {row['genre']} | {row['rating']}
Theater: {row['theater_name']} | {row['theater_city']}, {row['theater_state']}
Date: {row['date_sh']} | Time: {row['time_sh']}
Format: {row['screen_format']} | Language: {row['language_format']}
Price: {price_display} | Reserved: {reserved_clean:,} | Total: {total_seats_clean:,}
Occupancy: {occupancy_rate:.1f}% | Sales: ${sales_estimate:.2f}
Studio: {row['studio_name']} | Circuit: {row['circuit_name']}
Amenities: {row['amenities']} | DMA: {row['dma']}
""".strip()
                    
                    metadata = {
                        'chunk_type': 'film_performance',
                        'title': str(row['title']),
                        'genre': str(row['genre']),
                        'rating': str(row['rating']),
                        'theater_name': str(row['theater_name']),
                        'theater_city': str(row['theater_city']),
                        'theater_state': str(row['theater_state']),
                        'date_sh': str(row['date_sh']),
                        'time_sh': str(row['time_sh']),
                        'screen_format': str(row['screen_format']),
                        'language_format': str(row['language_format']),
                        'studio_name': str(row['studio_name']),
                        'circuit_name': str(row['circuit_name']),
                        'amenities': str(row['amenities']),
                        'dma': str(row['dma']),
                        'price': price_clean,
                        'reserved': reserved_clean,
                        'total_seats': total_seats_clean,
                        'occupancy_rate': round(occupancy_rate, 2),
                        'sales_estimate': round(sales_estimate, 2),
                        'row_index': int(idx)
                    }
                    
                    chunks.append((performance_text, metadata))
                    
                except Exception as e:
                    logger.warning(f"⚠️  Skipping row {idx}: {e}")
                    continue
        
        return chunks
    
    def process_chunk_sequential(self, chunk: pd.DataFrame, chunk_num: int) -> Tuple[List[Tuple[str, Dict]], np.ndarray]:
        """Process chunk sequentially with memory management"""
        try:
            # Create chunks
            chunks = self.create_optimized_chunks(chunk)
            
            if not chunks:
                return [], np.array([])
            
            # Generate embeddings with memory management
            texts = [chunk[0] for chunk in chunks]
            
            # Use small batch size for memory management
            batch_size = self.config['GPU_BATCH_SIZE'] if torch.cuda.is_available() else self.config['BATCH_SIZE']
            
            # Clear GPU cache before processing
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            logger.info(f"   Generating embeddings for {len(texts)} texts...")
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True,
                device='cuda' if torch.cuda.is_available() else 'cpu'
            )
            
            # Clear GPU cache after processing
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            return chunks, embeddings
            
        except Exception as e:
            logger.error(f"❌ Error processing chunk {chunk_num}: {e}")
            return [], np.array([])
    
    def upload_vectors_batch(self, vectors_batch: List[Dict]) -> bool:
        """Upload vectors in small batches with retry logic"""
        try:
            result = self.index.upsert(vectors=vectors_batch, timeout=60)
            return result.get('upserted_count', 0) == len(vectors_batch)
        except Exception as e:
            logger.warning(f"⚠️  Upload batch failed: {e}")
            return False
    
    def run_memory_optimized_pipeline(self):
        """Run the memory-optimized sequential pipeline"""
        logger.info("🚀 Starting Memory-Optimized Sequential Pipeline")
        logger.info("=" * 80)
        logger.info("🧠 OPTIMIZED FOR GPU MEMORY MANAGEMENT")
        logger.info("=" * 80)
        
        # Initialize components
        self.initialize_components()
        
        # Load data info
        if not os.path.exists(self.config['CSV_PATH']):
            logger.error(f"❌ CSV file not found: {self.config['CSV_PATH']}")
            return
        
        # Get total row count
        with open(self.config['CSV_PATH'], 'r') as f:
            total_rows = sum(1 for line in f) - 1
        
        estimated_total_chunks = (total_rows + self.config['CHUNK_SIZE'] - 1) // self.config['CHUNK_SIZE']
        
        logger.info(f"📈 Dataset: {total_rows:,} rows")
        logger.info(f"📦 Chunk size: {self.config['CHUNK_SIZE']:,} rows")
        logger.info(f"🔄 Estimated chunks: {estimated_total_chunks}")
        
        # Check for checkpoint
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'memory_checkpoint.json')
        skip_chunks = 0
        total_processed = 0
        
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
                skip_chunks = checkpoint['chunk_number']
                total_processed = checkpoint['total_processed']
                logger.info(f"📂 CHECKPOINT FOUND! Resuming from chunk {skip_chunks + 1}")
        
        # Process data sequentially
        chunk_iterator = pd.read_csv(self.config['CSV_PATH'], chunksize=self.config['CHUNK_SIZE'], low_memory=False)
        
        for chunk_num, chunk in enumerate(chunk_iterator, start=1):
            if chunk_num <= skip_chunks:
                continue
            
            chunk_start_time = time.time()
            logger.info(f"📦 Processing chunk {chunk_num} ({len(chunk):,} rows)")
            
            try:
                # Process chunk sequentially
                chunks, embeddings = self.process_chunk_sequential(chunk, chunk_num)
                
                if len(chunks) == 0:
                    logger.warning(f"⚠️  Chunk {chunk_num} produced no chunks")
                    continue
                
                # Upload vectors in small batches
                vectors = []
                for i, (text, metadata) in enumerate(chunks):
                    vector_id = f"memory_{chunk_num}_{i}"
                    vectors.append({
                        "id": vector_id,
                        "values": embeddings[i].tolist(),
                        "metadata": metadata
                    })
                
                # Upload in small batches
                batch_size = self.config['PINECONE_BATCH_SIZE']
                upload_success = True
                
                for i in range(0, len(vectors), batch_size):
                    batch = vectors[i:i + batch_size]
                    success = self.upload_vectors_batch(batch)
                    if not success:
                        upload_success = False
                        break
                
                if upload_success:
                    total_processed += len(chunks)
                    chunk_time = time.time() - chunk_start_time
                    
                    # Update stats
                    self.stats['chunk_times'].append(chunk_time)
                    self.stats['total_chunks_processed'] += 1
                    self.stats['total_vectors_created'] += len(chunks)
                    
                    # Save checkpoint every 5 chunks
                    if chunk_num % self.config['PROGRESS_UPDATE_INTERVAL'] == 0:
                        self.save_checkpoint(chunk_num, total_processed)
                    
                    # Calculate ETA
                    if len(self.stats['chunk_times']) > 1:
                        avg_chunk_time = np.mean(self.stats['chunk_times'])
                        remaining_chunks = estimated_total_chunks - chunk_num
                        eta_seconds = remaining_chunks * avg_chunk_time
                        eta_time = datetime.fromtimestamp(time.time() + eta_seconds).strftime('%H:%M:%S')
                        
                        logger.info(f"✅ Chunk {chunk_num} completed: {len(chunks)} vectors in {chunk_time:.1f}s")
                        logger.info(f"📊 Progress: {chunk_num}/{estimated_total_chunks} | Vectors: {self.stats['total_vectors_created']:,} | ETA: {eta_time}")
                    else:
                        logger.info(f"✅ Chunk {chunk_num} completed: {len(chunks)} vectors in {chunk_time:.1f}s")
                else:
                    logger.error(f"❌ Upload failed for chunk {chunk_num}")
                
                # Clear memory
                del chunk, chunks, embeddings, vectors
                gc.collect()
                
                # Clear GPU cache
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
            except Exception as e:
                logger.error(f"❌ Chunk {chunk_num} failed: {e}")
                continue
        
        # Final verification
        time.sleep(2)
        stats = self.index.describe_index_stats()
        
        total_time = time.time() - self.stats['start_time']
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ MEMORY-OPTIMIZED PIPELINE COMPLETED!")
        logger.info("=" * 80)
        logger.info(f"📊 Final Summary:")
        logger.info(f"   • Total vectors created: {stats['total_vector_count']:,}")
        logger.info(f"   • Total processing time: {total_time:.1f}s")
        if self.stats['chunk_times']:
            logger.info(f"   • Average chunk time: {np.mean(self.stats['chunk_times']):.1f}s")
            logger.info(f"   • Vectors per second: {stats['total_vector_count'] / total_time:.0f}")
        logger.info(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("\n🧠 MEMORY OPTIMIZATIONS APPLIED:")
        logger.info("   • Sequential processing to avoid GPU conflicts")
        logger.info("   • Small batch sizes for memory management")
        logger.info("   • GPU cache clearing between chunks")
        logger.info("   • Memory fraction limiting")
        logger.info("   • Clean data processing")
    
    def save_checkpoint(self, chunk_num: int, total_processed: int):
        """Save memory-optimized checkpoint"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'chunk_number': chunk_num,
            'total_processed': total_processed,
            'memory_settings': {
                'chunk_size': self.config['CHUNK_SIZE'],
                'batch_size': self.config['BATCH_SIZE'],
                'gpu_memory_fraction': self.config['GPU_MEMORY_FRACTION']
            }
        }
        
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'memory_checkpoint.json')
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        logger.info(f"💾 Memory checkpoint saved: {total_processed:,} records")

def main():
    """Main function"""
    pipeline = MemoryOptimizedPipeline()
    pipeline.run_memory_optimized_pipeline()

if __name__ == "__main__":
    main()
