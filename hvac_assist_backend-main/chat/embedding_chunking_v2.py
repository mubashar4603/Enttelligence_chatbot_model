import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm
import time
import json
from datetime import datetime
import os
from django.conf import settings


# ==================== CONFIGURATION ====================
class Config:
    """Configuration for the pipeline"""
    # Pinecone settings
    PINECONE_API_KEY = settings.PINECONE_API_KEY  # Replace with your API key
    PINECONE_ENVIRONMENT = "us-east-1"  # or your preferred region
    INDEX_NAME = "customer-database-vectors"
    DIMENSION = 768  # bge-base-en-v1.5 dimension

    # Embedding settings
    EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
    BATCH_SIZE = 256

    # Data processing settings
    CSV_CHUNK_SIZE = 50000

    # Checkpoint settings
    CHECKPOINT_DIR = "checkpoints"
    SAVE_CHECKPOINT_EVERY = 2000  # Save progress every N rows


# ==================== 1. DATA PREPROCESSING ====================
def preprocess_movie_data(csv_path, chunksize=50000):
    """
    Load and preprocess movie ticketing dataset in chunks.

    Args:
        csv_path (str): Path to the CSV file
        chunksize (int): Number of rows per chunk

    Returns:
        tuple: (DataFrame, list of text snippets, list of metadata dicts)
    """
    print("\n" + "=" * 60, flush=True)
    print("STEP 1: DATA PREPROCESSING", flush=True)
    print("=" * 60, flush=True)

    try:
        df_list = []
        rows_loaded = 0

        print(f"📂 Reading CSV: {csv_path}", flush=True)

        chunks = pd.read_csv(csv_path, chunksize=chunksize, low_memory=False, nrows=1000000)

        for i, chunk in enumerate(chunks):
            print(f"  Processing chunk {i + 1}... ({len(chunk)} rows)", flush=True)

            # Convert date columns
            date_columns = ['date_sh', 'last_updates', 'running_date', 'release_date']
            for col in date_columns:
                if col in chunk.columns:
                    chunk[col] = pd.to_datetime(chunk[col], errors='coerce')

            df_list.append(chunk)
            rows_loaded += len(chunk)

        print("🔗 Concatenating all chunks...", flush=True)
        df = pd.concat(df_list, ignore_index=True)

        # Define text columns
        text_columns = [
            'title', 'genre', 'rating', 'studio_name', 'theater_name',
            'theater_city', 'theater_state', 'language_format', 'screen_format',
            'movie_format', 'country', 'amenities', 'dma'
        ]

        # Handle missing values
        print("🧹 Cleaning text columns...", flush=True)
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].fillna('Unknown').astype(str).str.strip()
            else:
                print(f"  ⚠️  Column '{col}' not found - using default", flush=True)
                df[col] = 'Unknown'

        # Create structured text for embeddings
        print("📝 Creating structured text for embeddings...", flush=True)
        texts = []
        metadata_list = []

        for idx, row in tqdm(df.iterrows(), total=len(df), desc="  Processing rows"):
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
                if field in df.columns and pd.notna(row[field]):
                    try:
                        metadata[field] = float(row[field])
                    except:
                        pass

            # Add date as timestamp
            if 'date_sh' in df.columns and pd.notna(row['date_sh']):
                try:
                    metadata['show_date'] = int(row['date_sh'].timestamp())
                except:
                    pass

            metadata_list.append(metadata)

        print(f"\n✅ Preprocessing complete!", flush=True)
        print(f"   📊 Total rows: {len(df)}", flush=True)
        print(f"   📝 Text snippets created: {len(texts)}", flush=True)
        print(f"   🏷️  Metadata records: {len(metadata_list)}", flush=True)
        print(f"\n📄 Sample text (first record):", flush=True)
        print(f"   {texts[0][:250]}...", flush=True)

        return df, texts, metadata_list

    except Exception as e:
        print(f"\n❌ Error in preprocessing: {e}", flush=True)
        raise


# ==================== 2. EMBEDDING GENERATION ====================
def generate_embeddings(texts, batch_size=256, model_name="BAAI/bge-base-en-v1.5"):
    """
    Generate embeddings using BGE model.

    Args:
        texts (list): List of text snippets
        batch_size (int): Batch size for encoding
        model_name (str): Hugging Face model name

    Returns:
        np.ndarray: Array of embeddings (shape: [n_texts, 768])
    """
    print("\n" + "=" * 60, flush=True)
    print("STEP 2: EMBEDDING GENERATION", flush=True)
    print("=" * 60, flush=True)

    try:
        print(f"🤖 Loading model: {model_name}", flush=True)
        model = SentenceTransformer(model_name)

        print(f"🔢 Generating embeddings for {len(texts)} texts...", flush=True)
        print(f"   Batch size: {batch_size}", flush=True)
        print(f"   Dimension: 768", flush=True)

        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True  # Important for similarity search
        )

        print(f"\n✅ Embeddings generated!", flush=True)
        print(f"   Shape: {embeddings.shape}", flush=True)
        print(f"   Memory: {embeddings.nbytes / 1024 / 1024:.2f} MB", flush=True)

        # Save embeddings as backup
        backup_path = "embeddings_backup.npy"
        np.save(backup_path, embeddings)
        print(f"   💾 Backup saved: {backup_path}", flush=True)

        return embeddings

    except Exception as e:
        print(f"\n❌ Error in embedding generation: {e}", flush=True)
        raise


# ==================== 3. PINECONE UPLOAD ====================
def upload_to_pinecone(texts, embeddings, metadata_list, config):
    """
    Create Pinecone index and upload vectors.

    Args:
        texts (list): Text snippets
        embeddings (np.ndarray): Embedding vectors
        metadata_list (list): Metadata dictionaries
        config (Config): Configuration object

    Returns:
        Pinecone.Index: Pinecone index object
    """
    print("\n" + "=" * 60, flush=True)
    print("STEP 3: PINECONE UPLOAD", flush=True)
    print("=" * 60, flush=True)

    try:
        # Initialize Pinecone
        print(f"🔌 Connecting to Pinecone...", flush=True)
        pc = Pinecone(api_key=config.PINECONE_API_KEY)

        # Check if index exists
        existing_indexes = pc.list_indexes().names()

        

        # Create new index
        print(f"🆕 Creating new index: {config.INDEX_NAME}", flush=True)
        print(f"   Dimension: {config.DIMENSION}", flush=True)
        print(f"   Metric: cosine", flush=True)

        if config.INDEX_NAME not in existing_indexes:
            print(f"⚠️  Index '{config.INDEX_NAME}' already exists")
            pc.create_index(
                name=config.INDEX_NAME,
                dimension=config.DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region=config.PINECONE_ENVIRONMENT
                )
            )

        # Wait for index to be ready
        print("   ⏳ Waiting for index to be ready...", flush=True)
        while not pc.describe_index(config.INDEX_NAME).status['ready']:
            time.sleep(1)

        print("   ✅ Index created successfully!", flush=True)

        # Connect to index
        index = pc.Index(config.INDEX_NAME)

        # Prepare vectors for upload
        print(f"\n📤 Preparing {len(embeddings)} vectors for upload...", flush=True)

        vectors = []
        for i, (embedding, metadata) in enumerate(zip(embeddings, metadata_list)):
            vector_id = f"vec_{i}"
            vectors.append({
                "id": vector_id,
                "values": embedding.tolist(),
                "metadata": metadata
            })

        # Upload in batches
        print(f"⬆️  Uploading vectors in batches of 100...", flush=True)
        batch_size = 100
        total_batches = (len(vectors) + batch_size - 1) // batch_size

        for i in tqdm(range(0, len(vectors), batch_size), total=total_batches, desc="  Uploading"):
            batch = vectors[i:i + batch_size]
            index.upsert(vectors=batch)

        # Verify upload
        time.sleep(2)  # Wait for indexing
        stats = index.describe_index_stats()

        print(f"\n✅ Upload complete!", flush=True)
        print(f"   📊 Total vectors in index: {stats['total_vector_count']}", flush=True)
        print(f"   🎯 Index name: {config.INDEX_NAME}", flush=True)

        return index

    except Exception as e:
        print(f"\n❌ Error in Pinecone upload: {e}", flush=True)
        raise


# ==================== 4. CHECKPOINT MANAGEMENT ====================
def save_checkpoint(step, data, config):
    """Save processing checkpoint"""
    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    checkpoint_path = os.path.join(config.CHECKPOINT_DIR, f"checkpoint_{step}.json")

    with open(checkpoint_path, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'step': step,
            'data': data
        }, f, indent=2)

    print(f"💾 Checkpoint saved: {checkpoint_path}", flush=True)


# ==================== 5. MAIN PIPELINE ====================
def main():
    """
    Main pipeline: Preprocessing → Embedding → Pinecone Upload
    """
    print("\n" + "=" * 60, flush=True)
    print("🎬 MOVIE TICKETING RAG PIPELINE", flush=True)
    print("=" * 60, flush=True)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

    # Configuration
    config = Config()

    # CSV path - UPDATE THIS
    csv_path = "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/chat/enttelligence_10M_records.csv"  # <<<< CHANGE THIS

    if not os.path.exists(csv_path):
        print(f"\n❌ Error: CSV file not found at {csv_path}", flush=True)
        print("   Please update the csv_path in main() function", flush=True)
        return

    try:
        # Step 1: Preprocess data
        df, texts, metadata_list = preprocess_movie_data(
            csv_path=csv_path,
            chunksize=config.CSV_CHUNK_SIZE,
        )

        save_checkpoint('preprocessing', {
            'rows_processed': len(df),
            'texts_created': len(texts)
        }, config)

        # Step 2: Generate embeddings
        embeddings = generate_embeddings(
            texts=texts,
            batch_size=config.BATCH_SIZE,
            model_name=config.EMBEDDING_MODEL
        )

        save_checkpoint('embeddings', {
            'embeddings_shape': list(embeddings.shape),
            'embedding_size_mb': float(embeddings.nbytes / 1024 / 1024)
        }, config)

        # Step 3: Upload to Pinecone
        index = upload_to_pinecone(
            texts=texts,
            embeddings=embeddings,
            metadata_list=metadata_list,
            config=config
        )

        save_checkpoint('pinecone_upload', {
            'index_name': config.INDEX_NAME,
            'vectors_uploaded': len(embeddings)
        }, config)

        # Final summary
        print("\n" + "=" * 60, flush=True)
        print("✅ PIPELINE COMPLETED SUCCESSFULLY!", flush=True)
        print("=" * 60, flush=True)
        print(f"📊 Summary:", flush=True)
        print(f"   • Rows processed: {len(df)}", flush=True)
        print(f"   • Embeddings generated: {len(embeddings)}", flush=True)
        print(f"   • Vectors in Pinecone: {index.describe_index_stats()['total_vector_count']}", flush=True)
        print(f"   • Index name: {config.INDEX_NAME}", flush=True)
        print(f"   • Dimension: {config.DIMENSION}", flush=True)
        print(f"\n⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        print("\n🎯 Next steps:", flush=True)
        print("   1. Run the query pipeline to test RAG", flush=True)
        print("   2. Use index name in query script: '{}'".format(config.INDEX_NAME), flush=True)
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}", flush=True)
        raise


if __name__ == "__main__":
    main()