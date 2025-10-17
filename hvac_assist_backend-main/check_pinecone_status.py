#!/usr/bin/env python3
"""
Check Pinecone Index Status
Shows current vector count and estimates remaining work
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
    
    # Configuration (same as precision system)
    PINECONE_API_KEY = "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ"
    INDEX_NAME = "customer-database-vectors"
    CSV_PATH = "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv"
    CHUNK_SIZE = 25000
    
    print("🔍 PINECONE INDEX STATUS CHECK")
    print("=" * 50)
    
    try:
        # Connect to Pinecone
        print("🔌 Connecting to Pinecone...")
        pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # Check if index exists
        existing_indexes = pc.list_indexes().names()
        if INDEX_NAME not in existing_indexes:
            print(f"❌ Index '{INDEX_NAME}' does not exist!")
            return
        
        # Get index stats
        print(f"📊 Getting stats for index: {INDEX_NAME}")
        index = pc.Index(INDEX_NAME)
        stats = index.describe_index_stats()
        
        print("\n📈 CURRENT STATUS:")
        print(f"   • Index Name: {INDEX_NAME}")
        print(f"   • Total Vectors: {stats['total_vector_count']:,}")
        print(f"   • Dimension: {stats['dimension']}")
        print(f"   • Metric: {stats['metric']}")
        
        # Check checkpoint status
        checkpoint_path = "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/chat/checkpoints/latest_checkpoint.json"
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
            
            print(f"\n📂 CHECKPOINT STATUS:")
            print(f"   • Last Processed Chunk: {checkpoint['chunk_number']}")
            print(f"   • Records Processed: {checkpoint['total_processed']:,}")
            print(f"   • Timestamp: {checkpoint['timestamp']}")
            
            # Calculate progress
            total_rows = 7485544  # From your dataset
            progress_percent = (checkpoint['total_processed'] / total_rows) * 100
            
            print(f"\n📊 PROGRESS ANALYSIS:")
            print(f"   • Total Dataset Rows: {total_rows:,}")
            print(f"   • Processed Rows: {checkpoint['total_processed']:,}")
            print(f"   • Remaining Rows: {total_rows - checkpoint['total_processed']:,}")
            print(f"   • Progress: {progress_percent:.1f}%")
            
            # Estimate remaining vectors
            # Each chunk creates ~26,350 vectors (from your logs)
            vectors_per_chunk = 26350
            remaining_chunks = (total_rows - checkpoint['total_processed']) // CHUNK_SIZE
            estimated_remaining_vectors = remaining_chunks * vectors_per_chunk
            
            print(f"\n🎯 VECTOR ESTIMATES:")
            print(f"   • Current Vectors in Pinecone: {stats['total_vector_count']:,}")
            print(f"   • Estimated Remaining Vectors: {estimated_remaining_vectors:,}")
            print(f"   • Total Expected Vectors: {stats['total_vector_count'] + estimated_remaining_vectors:,}")
            
            # Time estimates
            if checkpoint['total_processed'] > 0:
                chunks_processed = checkpoint['chunk_number']
                remaining_chunks = (total_rows // CHUNK_SIZE) - chunks_processed
                
                print(f"\n⏰ TIME ESTIMATES:")
                print(f"   • Chunks Processed: {chunks_processed}")
                print(f"   • Remaining Chunks: {remaining_chunks}")
                print(f"   • Estimated Time Remaining: {remaining_chunks * 5} minutes")
        
        else:
            print(f"\n⚠️  No checkpoint found - pipeline hasn't started yet")
            
            # Calculate total expected vectors
            total_chunks = total_rows // CHUNK_SIZE
            vectors_per_chunk = 26350  # From your logs
            total_expected_vectors = total_chunks * vectors_per_chunk
            
            print(f"\n🎯 INITIAL ESTIMATES:")
            print(f"   • Total Dataset Rows: {total_rows:,}")
            print(f"   • Total Chunks: {total_chunks}")
            print(f"   • Estimated Total Vectors: {total_expected_vectors:,}")
            print(f"   • Estimated Processing Time: {total_chunks * 5} minutes")
        
        print(f"\n✅ Status check completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"❌ Error checking Pinecone status: {e}")

if __name__ == "__main__":
    check_pinecone_status()
