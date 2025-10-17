#!/usr/bin/env python3
"""
Corrected Pinecone Index Status Check
"""

import os
import sys
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from pinecone import Pinecone
import json
from datetime import datetime

def check_pinecone_status():
    """Check current Pinecone index status"""
    
    # Configuration
    PINECONE_API_KEY = "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ"
    INDEX_NAME = "customer-database-vectors"
    CSV_PATH = "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv"
    CHUNK_SIZE = 25000
    
    print("🔍 CORRECTED PINECONE INDEX STATUS")
    print("=" * 50)
    
    try:
        # Connect to Pinecone
        print("🔌 Connecting to Pinecone...")
        pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # Get index stats
        index = pc.Index(INDEX_NAME)
        stats = index.describe_index_stats()
        
        print("\n📈 CURRENT PINECONE STATUS:")
        print(f"   • Index Name: {INDEX_NAME}")
        print(f"   • Total Vectors: {stats['total_vector_count']:,}")
        print(f"   • Dimension: {stats['dimension']}")
        print(f"   • Metric: {stats['metric']}")
        
        # Get actual dataset size
        with open(CSV_PATH, 'r') as f:
            total_rows = sum(1 for line in f) - 1  # -1 for header
        
        print(f"\n📊 DATASET ANALYSIS:")
        print(f"   • Total Dataset Rows: {total_rows:,}")
        print(f"   • Chunk Size: {CHUNK_SIZE:,}")
        print(f"   • Total Chunks: {total_rows // CHUNK_SIZE}")
        
        # Check checkpoint status
        checkpoint_path = "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/chat/checkpoints/latest_checkpoint.json"
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
            
            print(f"\n📂 CHECKPOINT STATUS:")
            print(f"   • Last Processed Chunk: {checkpoint['chunk_number']}")
            print(f"   • Records Processed: {checkpoint['total_processed']:,}")
            print(f"   • Timestamp: {checkpoint['timestamp']}")
            
            # Calculate actual progress
            processed_rows = checkpoint['total_processed']
            remaining_rows = total_rows - processed_rows
            progress_percent = (processed_rows / total_rows) * 100
            
            print(f"\n📊 PROGRESS ANALYSIS:")
            print(f"   • Processed Rows: {processed_rows:,}")
            print(f"   • Remaining Rows: {remaining_rows:,}")
            print(f"   • Progress: {progress_percent:.1f}%")
            
            # Vector estimates based on actual data
            vectors_per_chunk = 26350  # From your logs: "Created 26350 precision chunks"
            chunks_processed = checkpoint['chunk_number']
            total_chunks = total_rows // CHUNK_SIZE
            remaining_chunks = total_chunks - chunks_processed
            
            current_vectors = stats['total_vector_count']
            estimated_remaining_vectors = remaining_chunks * vectors_per_chunk
            total_expected_vectors = current_vectors + estimated_remaining_vectors
            
            print(f"\n🎯 VECTOR ANALYSIS:")
            print(f"   • Current Vectors in Pinecone: {current_vectors:,}")
            print(f"   • Vectors per Chunk: {vectors_per_chunk:,}")
            print(f"   • Chunks Processed: {chunks_processed}")
            print(f"   • Remaining Chunks: {remaining_chunks}")
            print(f"   • Estimated Remaining Vectors: {estimated_remaining_vectors:,}")
            print(f"   • Total Expected Vectors: {total_expected_vectors:,}")
            
            # Time estimates
            print(f"\n⏰ TIME ESTIMATES:")
            print(f"   • Estimated Time per Chunk: ~5 minutes")
            print(f"   • Estimated Time Remaining: {remaining_chunks * 5} minutes")
            print(f"   • Estimated Time Remaining: {remaining_chunks * 5 / 60:.1f} hours")
            
            # Check if pipeline is complete
            if remaining_rows <= 0:
                print(f"\n🎉 PIPELINE STATUS: COMPLETED!")
                print(f"   • All {total_rows:,} rows have been processed")
                print(f"   • Total vectors created: {current_vectors:,}")
            else:
                print(f"\n🔄 PIPELINE STATUS: IN PROGRESS")
                print(f"   • {remaining_rows:,} rows remaining to process")
                print(f"   • {remaining_chunks} chunks remaining")
        
        else:
            print(f"\n⚠️  No checkpoint found - pipeline hasn't started yet")
            
            # Calculate total expected vectors
            total_chunks = total_rows // CHUNK_SIZE
            vectors_per_chunk = 26350
            total_expected_vectors = total_chunks * vectors_per_chunk
            
            print(f"\n🎯 INITIAL ESTIMATES:")
            print(f"   • Total Chunks: {total_chunks}")
            print(f"   • Vectors per Chunk: {vectors_per_chunk:,}")
            print(f"   • Estimated Total Vectors: {total_expected_vectors:,}")
            print(f"   • Estimated Processing Time: {total_chunks * 5} minutes")
            print(f"   • Estimated Processing Time: {total_chunks * 5 / 60:.1f} hours")
        
        print(f"\n✅ Status check completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"❌ Error checking Pinecone status: {e}")

if __name__ == "__main__":
    check_pinecone_status()
