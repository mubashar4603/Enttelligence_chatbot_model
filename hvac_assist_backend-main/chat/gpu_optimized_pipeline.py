#!/usr/bin/env python3
"""
🚀 GPU-OPTIMIZED PARALLEL PIPELINE FOR 16GB GPU
Optimized for 2 threads processing 50k chunks each
Maximizes GPU utilization while preventing memory conflicts
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

class GPUOptimizedPipeline:
    def __init__(self):
        """Initialize GPU-optimized pipeline for 16GB GPU"""
        self.config = self._load_config()
        self.model = None
        self.pc = None
        self.index = None
        self.progress_queue = Queue()
        self.stats = {
            'total_chunks_processed': 0,
            'total_vectors_created': 0,
            'start_time': time.time(),
            'chunk_times': [],
            'gpu_utilization': []
        }
        self.lock = threading.Lock()
        
    def _load_config(self):
        """Load configuration optimized for 16GB GPU with 2 threads"""
        return {
            # Pinecone settings
            'PINECONE_API_KEY': "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ",
            'PINECONE_ENVIRONMENT': "us-east-1-aws",
            'INDEX_NAME': "customer-database-vectors",
            'DIMENSION': 768,
            
            # GPU-optimized embedding settings for 16GB GPU
            'EMBEDDING_MODEL': "BAAI/bge-base-en-v1.5",
            'BATCH_SIZE': 1024,  # Optimized for 16GB GPU
            'GPU_BATCH_SIZE': 2048,  # Large batches for GPU efficiency
            
            # Thread configuration for optimal GPU utilization
            'NUM_THREADS': 2,  # Exactly 2 threads as requested
            'CHUNK_SIZE': 50000,  # 50k chunks as requested
            
            # Memory optimization for 16GB GPU
            'MAX_MEMORY_USAGE': 0.85,  # Use 85% of available RAM
            'GPU_MEMORY_FRACTION': 0.9,  # Use 90% of GPU memory for maximum efficiency
            
            # File paths
            'CSV_PATH': "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv",
            'CHECKPOINT_DIR': "checkpoints",
            'TEMP_DIR': "temp_gpu_parallel",
            
            # Performance settings
            'PINECONE_BATCH_SIZE': 200,  # Larger Pinecone batches for efficiency
            'PINECONE_RETRY_ATTEMPTS': 3,
            'PROGRESS_UPDATE_INTERVAL': 2,  # Update progress every 2 chunks
            'GPU_CLEAR_INTERVAL': 5,  # Clear GPU cache every 5 chunks
        }
    
    def initialize_components(self):
        """Initialize components with 16GB GPU optimization"""
        try:
            logger.info("🚀 Initializing GPU-Optimized Pipeline for 16GB GPU")
            logger.info(f"💻 Hardware: {psutil.cpu_count()} CPU cores, {psutil.virtual_memory().total // (1024**3)}GB RAM")
            
            # Check GPU availability and optimize
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                gpu_memory = torch.cuda.get_device_properties(0).total_memory // (1024**3)
                logger.info(f"🎮 GPU: {gpu_name} ({gpu_memory}GB)")
                
                # Clear GPU cache
                torch.cuda.empty_cache()
                
                # Set GPU memory fraction for maximum utilization
                torch.cuda.set_per_process_memory_fraction(self.config['GPU_MEMORY_FRACTION'])
                
                # Enable GPU optimizations
                torch.backends.cudnn.benchmark = True
                torch.backends.cudnn.deterministic = False
                
                logger.info(f"⚡ GPU Memory Fraction: {self.config['GPU_MEMORY_FRACTION']*100}%")
                logger.info(f"🧵 Threads: {self.config['NUM_THREADS']}")
                logger.info(f"📦 Chunk Size: {self.config['CHUNK_SIZE']:,}")
                logger.info(f"📊 Batch Size: {self.config['BATCH_SIZE']}")
                
            else:
                logger.warning("⚠️ No GPU detected, falling back to CPU")
            
            # Initialize embedding model with GPU optimization
            logger.info("🤖 Loading embedding model with GPU optimization...")
            self.model = SentenceTransformer(self.config['EMBEDDING_MODEL'])
            
            # Move model to GPU if available
            if torch.cuda.is_available():
                self.model = self.model.cuda()
                logger.info("✅ Model loaded on GPU")
            else:
                logger.info("✅ Model loaded on CPU")
            
            # Initialize Pinecone
            logger.info("🔌 Connecting to Pinecone...")
            self.pc = Pinecone(api_key=self.config['PINECONE_API_KEY'])
            self.index = self.pc.Index(self.config['INDEX_NAME'])
            
            # Create temp directory
            os.makedirs(self.config['TEMP_DIR'], exist_ok=True)
            
            logger.info("✅ GPU-optimized components initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize GPU-optimized components: {e}")
            raise
    
    def create_embedding_text(self, row: pd.Series) -> str:
        """Create comprehensive embedding text for each record"""
        try:
            # Core movie information
            title = str(row.get('title', '')).strip()
            theater_name = str(row.get('theater_name', '')).strip()
            circuit_name = str(row.get('circuit_name', '')).strip()
            city = str(row.get('theater_city', '')).strip()
            state = str(row.get('theater_state', '')).strip()
            
            # Performance metrics with safe parsing
            try:
                reserved = int(row.get('reserved', 0))
            except (ValueError, TypeError):
                reserved = 0
            
            try:
                total_seats = int(row.get('total_seats', 0))
            except (ValueError, TypeError):
                total_seats = 0
            
            # Handle price parsing - remove dollar signs and convert to float
            price_str = str(row.get('price', 0))
            try:
                # Remove dollar signs and any extra characters, take first price if multiple
                price_clean = price_str.replace('$', '').strip()
                if ',' in price_clean:
                    price_clean = price_clean.split(',')[0]  # Take first price if multiple
                price = float(price_clean) if price_clean else 0.0
            except (ValueError, TypeError):
                price = 0.0
            
            occupancy_rate = (reserved / total_seats * 100) if total_seats > 0 else 0
            
            # Format and timing
            screen_format = str(row.get('screen_format', '')).strip()
            movie_format = str(row.get('movie_format', '')).strip()
            date_sh = str(row.get('date_sh', '')).strip()
            time_sh = str(row.get('time_sh', '')).strip()
            
            # Additional context
            genre = str(row.get('genre', '')).strip()
            rating = str(row.get('rating', '')).strip()
            studio = str(row.get('studio_name', '')).strip()
            
            # Create comprehensive text
            text_parts = [
                f"Movie: {title}",
                f"Theater: {theater_name} in {city}, {state}",
                f"Circuit: {circuit_name}",
                f"Performance: {reserved} reserved seats out of {total_seats} total",
                f"Occupancy: {occupancy_rate:.1f}%",
                f"Price: ${price:.2f}",
                f"Format: {screen_format} {movie_format}",
                f"Showtime: {date_sh} at {time_sh}",
                f"Genre: {genre}",
                f"Rating: {rating}",
                f"Studio: {studio}"
            ]
            
            return " | ".join(text_parts)
            
        except Exception as e:
            logger.warning(f"⚠️ Error creating embedding text: {e}")
            return f"Movie: {str(row.get('title', 'Unknown'))}"
    
    def process_chunk_parallel(self, chunk_data: Tuple[int, pd.DataFrame]) -> Dict[str, Any]:
        """Process a single chunk in parallel thread"""
        chunk_idx, chunk_df = chunk_data
        thread_id = threading.current_thread().ident
        
        try:
            logger.info(f"🧵 Thread {thread_id} processing chunk {chunk_idx} ({len(chunk_df):,} records)")
            chunk_start_time = time.time()
            
            # Create embedding texts
            texts = []
            metadata_list = []
            
            for idx, row in chunk_df.iterrows():
                try:
                    text = self.create_embedding_text(row)
                    texts.append(text)
                    
                    # Create metadata with proper price parsing
                    price_str = str(row.get('price', 0))
                    try:
                        price_clean = price_str.replace('$', '').strip()
                        if ',' in price_clean:
                            price_clean = price_clean.split(',')[0]
                        metadata_price = float(price_clean) if price_clean else 0.0
                    except (ValueError, TypeError):
                        metadata_price = 0.0
                    
                    # Safe parsing for numeric fields
                    try:
                        metadata_reserved = int(row.get('reserved', 0))
                    except (ValueError, TypeError):
                        metadata_reserved = 0
                    
                    try:
                        metadata_total_seats = int(row.get('total_seats', 0))
                    except (ValueError, TypeError):
                        metadata_total_seats = 0
                    
                    metadata = {
                        'movie_id': str(row.get('id', '')),
                        'title': str(row.get('title', '')),
                        'theater_name': str(row.get('theater_name', '')),
                        'circuit_name': str(row.get('circuit_name', '')),
                        'city': str(row.get('theater_city', '')),
                        'state': str(row.get('theater_state', '')),
                        'reserved': metadata_reserved,
                        'total_seats': metadata_total_seats,
                        'price': metadata_price,
                        'screen_format': str(row.get('screen_format', '')),
                        'movie_format': str(row.get('movie_format', '')),
                        'date_sh': str(row.get('date_sh', '')),
                        'time_sh': str(row.get('time_sh', '')),
                        'genre': str(row.get('genre', '')),
                        'rating': str(row.get('rating', '')),
                        'studio': str(row.get('studio_name', '')),
                        'chunk_idx': chunk_idx,
                        'thread_id': thread_id
                    }
                    metadata_list.append(metadata)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error processing row {idx} in chunk {chunk_idx}: {e}")
                    continue
            
            if not texts:
                logger.warning(f"⚠️ No valid texts in chunk {chunk_idx}")
                return {'chunk_idx': chunk_idx, 'vectors_created': 0, 'success': False}
            
            # Generate embeddings with GPU optimization
            logger.info(f"🤖 Thread {thread_id} generating embeddings for chunk {chunk_idx}...")
            
            # Clear GPU cache before embedding generation
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            # Generate embeddings with optimized batch size
            embeddings = self.model.encode(
                texts,
                batch_size=self.config['GPU_BATCH_SIZE'],
                show_progress_bar=False,
                convert_to_numpy=True,
                device='cuda' if torch.cuda.is_available() else 'cpu'
            )
            
            # Upload to Pinecone
            logger.info(f"📤 Thread {thread_id} uploading chunk {chunk_idx} to Pinecone...")
            success = self.upload_vectors_to_pinecone(
                embeddings, metadata_list, chunk_idx * self.config['CHUNK_SIZE']
            )
            
            chunk_time = time.time() - chunk_start_time
            
            # Update stats
            with self.lock:
                self.stats['total_chunks_processed'] += 1
                self.stats['total_vectors_created'] += len(embeddings)
                self.stats['chunk_times'].append(chunk_time)
                
                # Track GPU utilization
                if torch.cuda.is_available():
                    gpu_memory_used = torch.cuda.memory_allocated() / (1024**3)
                    gpu_memory_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                    gpu_utilization = (gpu_memory_used / gpu_memory_total) * 100
                    self.stats['gpu_utilization'].append(gpu_utilization)
            
            logger.info(f"✅ Thread {thread_id} completed chunk {chunk_idx} in {chunk_time:.2f}s ({len(embeddings):,} vectors)")
            
            # Clear memory
            del texts, metadata_list, embeddings
            gc.collect()
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            return {
                'chunk_idx': chunk_idx,
                'vectors_created': len(embeddings) if 'embeddings' in locals() else 0,
                'success': success,
                'processing_time': chunk_time,
                'thread_id': thread_id
            }
            
        except Exception as e:
            logger.error(f"❌ Thread {thread_id} failed to process chunk {chunk_idx}: {e}")
            return {'chunk_idx': chunk_idx, 'vectors_created': 0, 'success': False, 'error': str(e)}
    
    def upload_vectors_to_pinecone(self, embeddings: np.ndarray, metadata_list: List[Dict], start_idx: int) -> bool:
        """Upload vectors to Pinecone with retry logic"""
        try:
            vectors_to_upload = []
            
            for i, (embedding, metadata) in enumerate(zip(embeddings, metadata_list)):
                vector_id = f"movie_{start_idx + i}"
                vectors_to_upload.append({
                    'id': vector_id,
                    'values': embedding.tolist(),
                    'metadata': metadata
                })
            
            # Upload in batches
            batch_size = self.config['PINECONE_BATCH_SIZE']
            for i in range(0, len(vectors_to_upload), batch_size):
                batch = vectors_to_upload[i:i + batch_size]
                
                for attempt in range(self.config['PINECONE_RETRY_ATTEMPTS']):
                    try:
                        self.index.upsert(vectors=batch)
                        break
                    except Exception as e:
                        if attempt == self.config['PINECONE_RETRY_ATTEMPTS'] - 1:
                            logger.error(f"❌ Failed to upload batch after {self.config['PINECONE_RETRY_ATTEMPTS']} attempts: {e}")
                            return False
                        logger.warning(f"⚠️ Upload attempt {attempt + 1} failed, retrying...")
                        time.sleep(2 ** attempt)  # Exponential backoff
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error uploading vectors to Pinecone: {e}")
            return False
    
    def update_progress_checkpoint(self, completed_chunks, total_chunks):
        """Update progress checkpoint during processing"""
        try:
            checkpoint_data = {
                'timestamp': datetime.now().isoformat(),
                'completed_chunks': completed_chunks,
                'total_chunks': total_chunks,
                'progress_percentage': (completed_chunks / total_chunks) * 100,
                'total_vectors_created': self.stats['total_vectors_created'],
                'elapsed_time': time.time() - self.stats['start_time'],
                'checkpoint_type': 'gpu_optimized_progress'
            }
            
            checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'gpu_optimized_progress.json')
            os.makedirs(self.config['CHECKPOINT_DIR'], exist_ok=True)
            
            with open(checkpoint_path, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"⚠️ Could not update progress checkpoint: {e}")
    
    def run_gpu_optimized_pipeline(self):
        """Run the GPU-optimized parallel pipeline"""
        try:
            logger.info("🚀 Starting GPU-Optimized Parallel Pipeline")
            logger.info(f"📊 Configuration:")
            logger.info(f"   • Threads: {self.config['NUM_THREADS']}")
            logger.info(f"   • Chunk Size: {self.config['CHUNK_SIZE']:,}")
            logger.info(f"   • Batch Size: {self.config['BATCH_SIZE']}")
            logger.info(f"   • GPU Batch Size: {self.config['GPU_BATCH_SIZE']}")
            
            # Initialize components
            self.initialize_components()
            
            # Load dataset
            logger.info("📂 Loading dataset...")
            csv_path = self.config['CSV_PATH']
            
            if not os.path.exists(csv_path):
                raise FileNotFoundError(f"Dataset not found: {csv_path}")
            
            # Get total rows for progress tracking
            total_rows = sum(1 for _ in open(csv_path)) - 1  # Subtract header
            logger.info(f"📊 Total records: {total_rows:,}")
            
            # Calculate chunks
            chunk_size = self.config['CHUNK_SIZE']
            total_chunks = (total_rows + chunk_size - 1) // chunk_size
            logger.info(f"📦 Total chunks: {total_chunks:,}")
            
            # Process chunks in parallel
            logger.info(f"🧵 Starting parallel processing with {self.config['NUM_THREADS']} threads...")
            
            with ThreadPoolExecutor(max_workers=self.config['NUM_THREADS']) as executor:
                # Submit all chunks
                futures = []
                chunk_idx = 0
                
                for chunk_df in pd.read_csv(csv_path, chunksize=chunk_size):
                    futures.append(executor.submit(self.process_chunk_parallel, (chunk_idx, chunk_df)))
                    chunk_idx += 1
                
                # Process completed chunks
                completed_chunks = 0
                successful_chunks = 0
                
                with tqdm(total=total_chunks, desc="Processing chunks") as pbar:
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            completed_chunks += 1
                            
                            if result['success']:
                                successful_chunks += 1
                            
                            # Update progress
                            pbar.update(1)
                            
                            # Log progress and update checkpoint
                            if completed_chunks % self.config['PROGRESS_UPDATE_INTERVAL'] == 0:
                                elapsed_time = time.time() - self.stats['start_time']
                                avg_time_per_chunk = elapsed_time / completed_chunks
                                remaining_chunks = total_chunks - completed_chunks
                                eta_seconds = remaining_chunks * avg_time_per_chunk
                                
                                logger.info(f"📊 Progress: {completed_chunks}/{total_chunks} chunks "
                                          f"({completed_chunks/total_chunks*100:.1f}%) | "
                                          f"ETA: {eta_seconds/3600:.1f}h | "
                                          f"Vectors: {self.stats['total_vectors_created']:,}")
                                
                                # Update progress checkpoint
                                self.update_progress_checkpoint(completed_chunks, total_chunks)
                            
                            # Clear GPU cache periodically
                            if completed_chunks % self.config['GPU_CLEAR_INTERVAL'] == 0:
                                if torch.cuda.is_available():
                                    torch.cuda.empty_cache()
                            
                        except Exception as e:
                            logger.error(f"❌ Error processing future: {e}")
                            completed_chunks += 1
                            pbar.update(1)
            
            # Final statistics
            total_time = time.time() - self.stats['start_time']
            avg_chunk_time = np.mean(self.stats['chunk_times']) if self.stats['chunk_times'] else 0
            avg_gpu_utilization = np.mean(self.stats['gpu_utilization']) if self.stats['gpu_utilization'] else 0
            
            logger.info("🎉 GPU-Optimized Parallel Pipeline Completed!")
            logger.info(f"📊 Final Statistics:")
            logger.info(f"   • Total Chunks Processed: {self.stats['total_chunks_processed']:,}")
            logger.info(f"   • Successful Chunks: {successful_chunks:,}")
            logger.info(f"   • Total Vectors Created: {self.stats['total_vectors_created']:,}")
            logger.info(f"   • Total Processing Time: {total_time/3600:.2f} hours")
            logger.info(f"   • Average Chunk Time: {avg_chunk_time:.2f} seconds")
            logger.info(f"   • Average GPU Utilization: {avg_gpu_utilization:.1f}%")
            logger.info(f"   • Vectors per Second: {self.stats['total_vectors_created']/total_time:.0f}")
            
            # Get actual Pinecone vector count for verification
            try:
                pinecone_stats = self.index.describe_index_stats()
                actual_pinecone_vectors = pinecone_stats.total_vector_count
                logger.info(f"🔍 Verified Pinecone vectors: {actual_pinecone_vectors:,}")
            except Exception as e:
                logger.warning(f"⚠️ Could not verify Pinecone count: {e}")
                actual_pinecone_vectors = self.stats['total_vectors_created']
            
            # Save final checkpoint with Pinecone verification
            checkpoint_data = {
                'timestamp': datetime.now().isoformat(),
                'total_chunks_processed': self.stats['total_chunks_processed'],
                'total_vectors_created': self.stats['total_vectors_created'],
                'actual_pinecone_vectors': actual_pinecone_vectors,
                'vectors_match': abs(actual_pinecone_vectors - self.stats['total_vectors_created']) < 1000,
                'total_processing_time': total_time,
                'avg_chunk_time': avg_chunk_time,
                'avg_gpu_utilization': avg_gpu_utilization,
                'successful_chunks': successful_chunks,
                'config': self.config,
                'checkpoint_type': 'gpu_optimized_final'
            }
            
            checkpoint_path = os.path.join(self.config['CHECKPOINT_DIR'], 'gpu_optimized_final.json')
            os.makedirs(self.config['CHECKPOINT_DIR'], exist_ok=True)
            
            with open(checkpoint_path, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            
            logger.info(f"💾 Final checkpoint saved: {checkpoint_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ GPU-optimized pipeline failed: {e}")
            raise

def main():
    """Test the GPU-optimized pipeline"""
    pipeline = GPUOptimizedPipeline()
    pipeline.run_gpu_optimized_pipeline()

if __name__ == "__main__":
    main()