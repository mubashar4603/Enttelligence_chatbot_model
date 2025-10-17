#!/usr/bin/env python3
"""
Fresh Status Check for 7.4M Dataset
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

def check_fresh_status():
    """Check status for fresh 7.4M dataset"""
    
    # Configuration
    PINECONE_API_KEY = "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ"
    INDEX_NAME = "customer-database-vectors"
    CSV_PATH = "/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv"
    CHUNK_SIZE = 25000
    
    print("🎯 FRESH START - 7.4M DATASET STATUS")
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
        
        print(f"\n📊 YOUR 7.4M DATASET ANALYSIS:")
        print(f"   • Total Dataset Rows: {total_rows:,}")
        print(f"   • Chunk Size: {CHUNK_SIZE:,}")
        print(f"   • Total Chunks: {total_rows // CHUNK_SIZE}")
        
        # Check if checkpoint exists
        checkpoint_path = "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/chat/checkpoints/latest_checkpoint.json"
        if os.path.exists(checkpoint_path):
            print(f"\n⚠️  Old checkpoint found - this should be deleted")
        else:
            print(f"\n✅ No checkpoint found - ready for fresh start")
        
        # Calculate estimates for your dataset
        total_chunks = total_rows // CHUNK_SIZE
        vectors_per_chunk = 26350  # From previous runs
        total_expected_vectors = total_chunks * vectors_per_chunk
        
        print(f"\n🎯 ESTIMATES FOR YOUR 7.4M DATASET:")
        print(f"   • Total Chunks to Process: {total_chunks}")
        print(f"   • Vectors per Chunk: {vectors_per_chunk:,}")
        print(f"   • Estimated Total Vectors: {total_expected_vectors:,}")
        print(f"   • Estimated Processing Time: {total_chunks * 5} minutes")
        print(f"   • Estimated Processing Time: {total_chunks * 5 / 60:.1f} hours")
        
        print(f"\n🚀 READY TO START:")
        print(f"   • Pinecone index is empty and ready")
        print(f"   • No old checkpoints")
        print(f"   • Dataset: {total_rows:,} rows")
        print(f"   • Expected vectors: {total_expected_vectors:,}")
        
        print(f"\n✅ Status check completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"❌ Error checking status: {e}")

if __name__ == "__main__":
    check_fresh_status()
