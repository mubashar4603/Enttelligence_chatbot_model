#!/usr/bin/env python3
"""
🚀 HIGH-PERFORMANCE THREAD-BASED PARALLEL PIPELINE
Fixed version using threading instead of multiprocessing to avoid pickle issues
Optimized for G4dn instances (16GB RAM + 16GB GPU)
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

class ThreadBasedParallelSystem:
    def __init__(self):
        """Initialize high-performance thread-based parallel system"""
        self.config = self._load_config()
        self.model = None
        self.pc = None
        self.index = None
        self.progress_queue = Queue()
        self.stats = {
            'total_chunks_processed': 0,
            'total_vectors_created': 0,
            'start_time': time.time(),
            'chunk_times': []
        }
        self.lock = threading.Lock()
        
    def _load_config(self):
        """Load optimized configuration for G4dn instance"""
        return {
            # Pinecone settings
            'PINECONE_API_KEY': "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ",
            'PINECONE_ENVIRONMENT': "us-east-1-aws",
            'INDEX_NAME': "customer-database-vectors",
            'DIMENSION': 768,
            
            # GPU-optimized embedding settings
            'EMBEDDING_MODEL': "BAAI/bge-base-en-v1.5",
            'BATCH_SIZE': 256,  # Reduced for memory management
            'GPU_BATCH_SIZE': 512,  # Reduced for memory management
            
            # Thread-based processing settings
            'NUM_THREADS': 4,  # Reduced threads to prevent GPU memory conflicts
            'CHUNK_SIZE': 50000,  # Smaller chunks for better memory management
            
            # Memory optimization
            'MAX_MEMORY_USAGE': 0.8,  # Use 80% of available RAM
            'GPU_MEMORY_FRACTION': 0.7,  # Use 70% of GPU memory to prevent conflicts
            
            # File paths
            'CSV_PATH': "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv",
            'CHECKPOINT_DIR': "checkpoints",
            'TEMP_DIR': "temp_parallel",
            
            # Performance settings
            'PINECONE_BATCH_SIZE': 100,  # Smaller Pinecone batches for stability
            'PINECONE_RETRY_ATTEMPTS': 5,
            'PROGRESS_UPDATE_INTERVAL': 5,  # Update progress every 5 chunks
        }
    
    def initialize_components(self):
        """Initialize components with GPU optimization"""
        try:
            logger.info("🚀 Initializing High-Performance Thread-Based Parallel System")
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
            
            # Create temp directory for parallel processing
            os.makedirs(self.config['TEMP_DIR'], exist_ok=True)
            os.makedirs(self.config['CHECKPOINT_DIR'], exist_ok=True)
            
            logger.info("✅ High-performance thread-based system initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize system: {e}")
            raise
    
    def create_optimized_chunks(self, chunk: pd.DataFrame) -> List[Tuple[str, Dict]]:
        """Create optimized chunks with thread-friendly processing"""
        chunks = []
        
        # Process in thread-friendly batches
        batch_size = 1000  # Process 1000 rows at a time within chunk
        
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
    
    def process_chunk_thread(self, chunk_data: Tuple[int, pd.DataFrame]) -> Tuple[int, List[Tuple[str, Dict]], np.ndarray]:
        """Process chunk in thread worker"""
        chunk_num, chunk = chunk_data
        
        try:
            # Create chunks
            chunks = self.create_optimized_chunks(chunk)
            
            if not chunks:
                return chunk_num, [], np.array([])
            
            # Generate embeddings with GPU acceleration
            texts = [chunk[0] for chunk in chunks]
            
            # Use smaller batch size for memory management
            batch_size = self.config['GPU_BATCH_SIZE'] if torch.cuda.is_available() else self.config['BATCH_SIZE']
            
            # Clear GPU cache before processing
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,  # Disable progress bar in parallel workers
                convert_to_numpy=True,
                normalize_embeddings=True,
                device='cuda' if torch.cuda.is_available() else 'cpu'
            )
            
            # Clear GPU cache after processing
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            return chunk_num, chunks, embeddings
            
        except Exception as e:
            logger.error(f"❌ Error processing chunk {chunk_num}: {e}")
            return chunk_num, [], np.array([])
    
    def upload_vectors_thread(self, vectors_batch: List[Dict]) -> bool:
        """Upload vectors in thread with retry logic"""
        try:
            result = self.index.upsert(vectors=vectors_batch, timeout=60)
            return result.get('upserted_count', 0) == len(vectors_batch)
        except Exception as e:
            logger.warning(f"⚠️  Upload batch failed: {e}")
            return False
    
    def progress_monitor(self):
        """Monitor progress in separate thread"""
        while True:
            try:
                progress_data = self.progress_queue.get(timeout=1)
                if progress_data is None:  # Shutdown signal
                    break
                
                chunk_num, chunk_time, vectors_created = progress_data
                
                with self.lock:
                    self.stats['chunk_times'].append(chunk_time)
                    self.stats['total_chunks_processed'] += 1
                    self.stats['total_vectors_created'] += vectors_created
                
                # Calculate ETA
                if len(self.stats['chunk_times']) > 1:
                    avg_chunk_time = np.mean(self.stats['chunk_times'])
                    remaining_chunks = self.estimated_total_chunks - chunk_num
                    eta_seconds = remaining_chunks * avg_chunk_time
                    eta_time = datetime.fromtimestamp(time.time() + eta_seconds).strftime('%H:%M:%S')
                    
                    logger.info(f"📊 Progress: Chunk {chunk_num} | "
                              f"Vectors: {self.stats['total_vectors_created']:,} | "
                              f"ETA: {eta_time}")
                
            except:
                continue
    
    def run_thread_parallel_pipeline(self):
        """Run the high-performance thread-based parallel pipeline"""
        logger.info("🚀 Starting High-Performance Thread-Based Parallel Pipeline")
        logger.info("=" * 80)
        logger.info("⚡ OPTIMIZED FOR G4DN INSTANCE (16GB RAM + 16GB GPU)")
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
        
        self.estimated_total_chunks = (total_rows + self.config['CHUNK_SIZE'] - 1) // self.config['CHUNK_SIZE']
        
        logger.info(f"📈 Dataset: {total_rows:,} rows")
        logger.info(f"📦 Chunk size: {self.config['CHUNK_SIZE']:,} rows")
        logger.info(f"🔄 Estimated chunks: {self.estimated_total_chunks}")
        logger.info(f"🧵 Threads: {self.config['NUM_THREADS']}")
        
        # Start progress monitor
        progress_thread = threading.Thread(target=self.progress_monitor, daemon=True)
        progress_thread.start()
        
        # Check for checkpoint
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'thread_checkpoint.json')
        skip_chunks = 0
        total_processed = 0
        
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
                skip_chunks = checkpoint['chunk_number']
                total_processed = checkpoint['total_processed']
                logger.info(f"📂 CHECKPOINT FOUND! Resuming from chunk {skip_chunks + 1}")
        
        # Process data in parallel using threads
        chunk_iterator = pd.read_csv(self.config['CSV_PATH'], chunksize=self.config['CHUNK_SIZE'], low_memory=False)
        
        # Prepare chunk data for parallel processing
        chunk_data_list = []
        for chunk_num, chunk in enumerate(chunk_iterator, start=1):
            if chunk_num <= skip_chunks:
                continue
            chunk_data_list.append((chunk_num, chunk))
        
        logger.info(f"🔄 Processing {len(chunk_data_list)} chunks in parallel threads...")
        
        # Process chunks in parallel using threads
        with ThreadPoolExecutor(max_workers=self.config['NUM_THREADS']) as executor:
            # Submit all chunks
            future_to_chunk = {
                executor.submit(self.process_chunk_thread, chunk_data): chunk_data[0] 
                for chunk_data in chunk_data_list
            }
            
            # Process results as they complete
            for future in as_completed(future_to_chunk):
                chunk_num = future_to_chunk[future]
                chunk_start_time = time.time()
                
                try:
                    chunk_num_result, chunks, embeddings = future.result()
                    
                    if len(chunks) == 0:
                        logger.warning(f"⚠️  Chunk {chunk_num} produced no chunks")
                        continue
                    
                    # Upload vectors in parallel batches
                    vectors = []
                    for i, (text, metadata) in enumerate(chunks):
                        vector_id = f"thread_{chunk_num}_{i}"
                        vectors.append({
                            "id": vector_id,
                            "values": embeddings[i].tolist(),
                            "metadata": metadata
                        })
                    
                    # Upload in parallel batches using threads
                    upload_success = False
                    batch_size = self.config['PINECONE_BATCH_SIZE']
                    
                    with ThreadPoolExecutor(max_workers=4) as upload_executor:
                        upload_futures = []
                        for i in range(0, len(vectors), batch_size):
                            batch = vectors[i:i + batch_size]
                            upload_futures.append(upload_executor.submit(self.upload_vectors_thread, batch))
                        
                        # Wait for all uploads to complete
                        upload_success = all(future.result() for future in upload_futures)
                    
                    if upload_success:
                        total_processed += len(chunks)
                        chunk_time = time.time() - chunk_start_time
                        
                        # Send progress update
                        self.progress_queue.put((chunk_num, chunk_time, len(chunks)))
                        
                        # Save checkpoint every 10 chunks
                        if chunk_num % self.config['PROGRESS_UPDATE_INTERVAL'] == 0:
                            self.save_checkpoint(chunk_num, total_processed)
                        
                        logger.info(f"✅ Chunk {chunk_num} completed: {len(chunks)} vectors in {chunk_time:.1f}s")
                    else:
                        logger.error(f"❌ Upload failed for chunk {chunk_num}")
                    
                except Exception as e:
                    logger.error(f"❌ Chunk {chunk_num} failed: {e}")
                    continue
        
        # Stop progress monitor
        self.progress_queue.put(None)
        
        # Final verification
        time.sleep(2)
        stats = self.index.describe_index_stats()
        
        total_time = time.time() - self.stats['start_time']
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ HIGH-PERFORMANCE THREAD-BASED PARALLEL PIPELINE COMPLETED!")
        logger.info("=" * 80)
        logger.info(f"📊 Final Summary:")
        logger.info(f"   • Total vectors created: {stats['total_vector_count']:,}")
        logger.info(f"   • Total processing time: {total_time:.1f}s")
        if self.stats['chunk_times']:
            logger.info(f"   • Average chunk time: {np.mean(self.stats['chunk_times']):.1f}s")
            logger.info(f"   • Vectors per second: {stats['total_vector_count'] / total_time:.0f}")
        logger.info(f"   • Thread efficiency: {self.config['NUM_THREADS']}x")
        logger.info(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("\n🚀 PERFORMANCE OPTIMIZATIONS APPLIED:")
        logger.info("   • GPU-accelerated embeddings")
        logger.info("   • Thread-based parallel processing")
        logger.info("   • Concurrent Pinecone uploads")
        logger.info("   • Optimized batch sizes")
        logger.info("   • Real-time progress tracking")
    
    def save_checkpoint(self, chunk_num: int, total_processed: int):
        """Save thread-based checkpoint"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'chunk_number': chunk_num,
            'total_processed': total_processed,
            'thread_settings': {
                'num_threads': self.config['NUM_THREADS'],
                'chunk_size': self.config['CHUNK_SIZE'],
                'batch_size': self.config['BATCH_SIZE']
            }
        }
        
        checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'thread_checkpoint.json')
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        logger.info(f"💾 Thread checkpoint saved: {total_processed:,} records")

def main():
    """Main function"""
    pipeline = ThreadBasedParallelSystem()
    pipeline.run_thread_parallel_pipeline()

if __name__ == "__main__":
    main()
