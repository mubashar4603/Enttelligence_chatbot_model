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


# ==================== CONFIGURATION ====================
class Config:
    """Configuration for the pipeline"""
    # Pinecone settings
    PINECONE_API_KEY = settings.PINECONE_API_KEY  
    PINECONE_ENVIRONMENT = "us-east-1"
    INDEX_NAME = "customer-XXXXabase-vectors"
    DIMENSION = 768

    # Embedding settings
    EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
    BATCH_SIZE = 256

    # Data processing settings
    CHUNK_SIZE = 50000  # Process 50k rows at a time

    # Checkpoint settings
    CHECKPOINT_DIR = "checkpoints"


# ==================== HELPER FUNCTIONS ====================
def process_chunk_text(chunk):
    """
    Process a single chunk and create text + metadata.
    
    Args:
        chunk (DataFrame): Chunk of data
        
    Returns:
        tuple: (texts, metadata_list)
    """
    # Convert date columns
    date_columns = ['date_sh', 'last_updates', 'running_date', 'release_date']
    for col in date_columns:
        if col in chunk.columns:
            chunk[col] = pd.to_datetime(chunk[col], errors='coerce')

    # Define text columns
    text_columns = [
        'title', 'genre', 'rating', 'studio_name', 'theater_name',
        'theater_city', 'theater_state', 'language_format', 'screen_format',
        'movie_format', 'country', 'amenities', 'dma'
    ]

    # Handle missing values
    for col in text_columns:
        if col in chunk.columns:
            chunk[col] = chunk[col].fillna('Unknown').astype(str).str.strip()
        else:
            chunk[col] = 'Unknown'

    # Create structured text for embeddings
    texts = []
    metadata_list = []

    for idx, row in chunk.iterrows():
        # Build rich text description
        text_parts = []

        # Movie info
        if row['title'] != 'Unknown':
            text_parts.append(f"Title: {row['title']}")
        if row['genre'] != 'Unknown':
            text_parts.append(f"Genre: {row['genre']}")
        if row['rating'] != 'Unknown':
            text_parts.append(f"Rating: {row['rating']}")
        if row['studio_name'] != 'Unknown':
            text_parts.append(f"Studio: {row['studio_name']}")

        # Theater info
        theater_parts = []
        if row['theater_name'] != 'Unknown':
            theater_parts.append(row['theater_name'])
        if row['theater_city'] != 'Unknown':
            theater_parts.append(row['theater_city'])
        if row['theater_state'] != 'Unknown':
            theater_parts.append(row['theater_state'])
        if theater_parts:
            text_parts.append(f"Theater: {', '.join(theater_parts)}")

        # Format info
        format_parts = []
        if row['language_format'] != 'Unknown':
            format_parts.append(row['language_format'])
        if row['screen_format'] != 'Unknown':
            format_parts.append(row['screen_format'])
        if row['movie_format'] != 'Unknown':
            format_parts.append(row['movie_format'])
        if format_parts:
            text_parts.append(f"Format: {' '.join(format_parts)}")

        # Additional details
        if row['amenities'] != 'Unknown':
            text_parts.append(f"Amenities: {row['amenities']}")
        if row['country'] != 'Unknown':
            text_parts.append(f"Country: {row['country']}")
        if row['dma'] != 'Unknown':
            text_parts.append(f"Market: {row['dma']}")

        full_text = ". ".join(text_parts) + "."
        texts.append(full_text)

        # Create metadata for Pinecone
        metadata = {
            'id': str(row.get('id', idx)),
            'theater_id': str(row.get('theater_id', '')),
            'theater_name': row['theater_name'],
            'city': row['theater_city'],
            'state': row['theater_state'],
            'title': row['title'],
            'genre': row['genre'],
            'rating': row['rating'],
            'studio': row['studio_name'],
            'format': row['screen_format'],
            'country': row['country']
        }

        # Add numerical fields
        numerical_fields = ['price', 'total_seats', 'available', 'reserved', 'runtime']
        for field in numerical_fields:
            if field in chunk.columns and pd.notna(row[field]):
                try:
                    metadata[field] = float(row[field])
                except:
                    pass

        # Add date as timestamp
        if 'date_sh' in chunk.columns and pd.notna(row['date_sh']):
            try:
                metadata['show_date'] = int(row['date_sh'].timestamp())
            except:
                pass

        metadata_list.append(metadata)

    return texts, metadata_list


def upload_vectors_to_pinecone(index, embeddings, metadata_list, start_idx, max_retries=3):
    """
    Upload vectors to Pinecone in batches with retry logic.
    
    Args:
        index: Pinecone index
        embeddings (np.ndarray): Embedding vectors
        metadata_list (list): Metadata dictionaries
        start_idx (int): Starting index for vector IDs
        max_retries (int): Maximum retry attempts per batch
    """
    vectors = []
    for i, (embedding, metadata) in enumerate(zip(embeddings, metadata_list)):
        vector_id = f"vec_{start_idx + i}"
        vectors.append({
            "id": vector_id,
            "values": embedding.tolist(),
            "metadata": metadata
        })

    # Upload in batches of 100
    batch_size = 100
    total_batches = (len(vectors) + batch_size - 1) // batch_size
    
    print(f"     Uploading {len(vectors)} vectors in {total_batches} batches...", flush=True)
    
    for i in tqdm(range(0, len(vectors), batch_size), total=total_batches, desc="     Batches"):
        batch = vectors[i:i + batch_size]
        
        # Retry logic
        for attempt in range(max_retries):
            try:
                index.upsert(vectors=batch, timeout=30)
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    print(f"\n     ⚠️  Batch {i//batch_size + 1} failed (attempt {attempt + 1}/{max_retries}): {str(e)[:100]}", flush=True)
                    print(f"     ⏳ Retrying in {wait_time}s...", flush=True)
                    time.sleep(wait_time)
                else:
                    print(f"\n     ❌ Batch {i//batch_size + 1} failed after {max_retries} attempts!", flush=True)
                    raise e
        
        # Small delay between batches to avoid rate limiting
        time.sleep(0.1)


def save_checkpoint(chunk_num, total_processed, config):
    """Save processing checkpoint"""
    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    checkpoint_path = os.path.join(config.CHECKPOINT_DIR, "latest_checkpoint.json")

    with open(checkpoint_path, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'chunk_number': chunk_num,
            'total_processed': total_processed
        }, f, indent=2)


def load_checkpoint(config):
    """Load last checkpoint if exists"""
    checkpoint_path = os.path.join(config.CHECKPOINT_DIR, "latest_checkpoint.json")
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, 'r') as f:
            return json.load(f)
    return None


# ==================== MAIN PIPELINE ====================
def main():
    """
    Memory-efficient pipeline: Process in chunks
    CSV Chunk → Embeddings → Pinecone Upload → Clear Memory → Repeat
    """
    print("\n" + "=" * 60, flush=True)
    print("🎬 MEMORY-EFFICIENT RAG PIPELINE", flush=True)
    print("=" * 60, flush=True)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

    # Configuration
    config = Config()

    # CSV path - UPDATE THIS
    csv_path = "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/chat/enttelligence_10M_records.csv"

    if not os.path.exists(csv_path):
        print(f"\n❌ Error: CSV file not found at {csv_path}", flush=True)
        return

    try:
        # Initialize Pinecone
        print(f"\n🔌 Connecting to Pinecone...", flush=True)
        try:
            pc = Pinecone(api_key=config.PINECONE_API_KEY)
            print(f"   ✅ Connected successfully!", flush=True)
        except Exception as e:
            print(f"   ❌ Connection failed: {e}", flush=True)
            raise

        # Create index if doesn't exist
        existing_indexes = pc.list_indexes().names()
        if config.INDEX_NAME not in existing_indexes:
            print(f"🆕 Creating index: {config.INDEX_NAME}", flush=True)
            pc.create_index(
                name=config.INDEX_NAME,
                dimension=config.DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region=config.PINECONE_ENVIRONMENT
                )
            )
            print("⏳ Waiting for index to be ready...", flush=True)
            while not pc.describe_index(config.INDEX_NAME).status['ready']:
                time.sleep(1)
        else:
            print(f"✅ Using existing index: {config.INDEX_NAME}", flush=True)

        index = pc.Index(config.INDEX_NAME)

        # Load embedding model ONCE (reuse for all chunks)
        print(f"\n🤖 Loading embedding model: {config.EMBEDDING_MODEL}", flush=True)
        model = SentenceTransformer(config.EMBEDDING_MODEL)

        # Check for previous checkpoint
        checkpoint = load_checkpoint(config)
        skip_chunks = 0
        total_processed = 0

        if checkpoint:
            print(f"\n📌 CHECKPOINT FOUND!", flush=True)
            print(f"   Last processed: Chunk {checkpoint['chunk_number']}", flush=True)
            print(f"   Total rows done: {checkpoint['total_processed']:,}", flush=True)
            print(f"   Timestamp: {checkpoint['timestamp']}", flush=True)
            print("\n❓ Continue from checkpoint? (y/n): ", end='', flush=True)
            response = input()
            if response.lower() == 'y':
                skip_chunks = checkpoint['chunk_number']
                total_processed = checkpoint['total_processed']
                print(f"   ✅ Resuming from chunk {skip_chunks + 1}...\n", flush=True)
            else:
                print(f"   🔄 Starting fresh (checkpoint ignored)\n", flush=True)

        # Get total row count
        print(f"\n📊 Counting total rows...", flush=True)
        total_rows = sum(1 for _ in open(csv_path)) - 1  # -1 for header
        print(f"   Total rows in CSV: {total_rows:,}", flush=True)

        # Process in chunks
        print(f"\n🔄 Processing in chunks of {config.CHUNK_SIZE:,} rows...", flush=True)
        print("=" * 60, flush=True)

        chunk_iterator = pd.read_csv(csv_path, chunksize=config.CHUNK_SIZE, low_memory=False)

        for chunk_num, chunk in enumerate(chunk_iterator, start=1):
            # Skip already processed chunks
            if chunk_num <= skip_chunks:
                continue

            chunk_start_time = time.time()
            print(f"\n📦 CHUNK {chunk_num} ({len(chunk):,} rows)", flush=True)
            print("-" * 60, flush=True)

            # Step 1: Process text
            print("  1️⃣  Processing text...", flush=True)
            texts, metadata_list = process_chunk_text(chunk)
            del chunk  # Free memory
            gc.collect()

            # Step 2: Generate embeddings
            print("  2️⃣  Generating embeddings...", flush=True)
            embeddings = model.encode(
                texts,
                batch_size=config.BATCH_SIZE,
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True
            )

            # Step 3: Upload to Pinecone
            print("  3️⃣  Uploading to Pinecone...", flush=True)
            try:
                upload_vectors_to_pinecone(index, embeddings, metadata_list, total_processed)
                print(f"     ✅ Upload successful!", flush=True)
            except Exception as e:
                print(f"\n  ❌ Upload failed for chunk {chunk_num}: {e}", flush=True)
                print(f"  💾 Saving embeddings backup for this chunk...", flush=True)
                np.save(f"failed_chunk_{chunk_num}_embeddings.npy", embeddings)
                with open(f"failed_chunk_{chunk_num}_metadata.json", 'w') as f:
                    json.dump(metadata_list, f)
                print(f"  📁 Backup saved. Fix the issue and manually upload this chunk.", flush=True)
                raise e

            # Update counters
            total_processed += len(texts)

            # Step 4: Clear memory
            del texts, metadata_list, embeddings
            gc.collect()

            # Save checkpoint
            save_checkpoint(chunk_num, total_processed, config)

            # Show progress
            chunk_time = time.time() - chunk_start_time
            progress = (total_processed / total_rows) * 100
            print(f"  ✅ Chunk completed in {chunk_time:.1f}s", flush=True)
            print(f"  📊 Progress: {total_processed:,}/{total_rows:,} ({progress:.1f}%)", flush=True)

        # Verify final count
        time.sleep(2)
        stats = index.describe_index_stats()

        print("\n" + "=" * 60, flush=True)
        print("✅ PIPELINE COMPLETED SUCCESSFULLY!", flush=True)
        print("=" * 60, flush=True)
        print(f"📊 Summary:", flush=True)
        print(f"   • Total rows processed: {total_processed:,}", flush=True)
        print(f"   • Vectors in Pinecone: {stats['total_vector_count']:,}", flush=True)
        print(f"   • Index name: {config.INDEX_NAME}", flush=True)
        print(f"\n⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}", flush=True)
        raise


if __name__ == "__main__":
    main()