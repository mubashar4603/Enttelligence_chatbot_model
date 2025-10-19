#!/usr/bin/env python3
"""
Check Checkpoint Status
Quick script to verify the current checkpoint status for the precision pipeline
"""

import json
import os
from datetime import datetime

def check_checkpoint_status():
    """Check and display current checkpoint status"""
    
    checkpoint_file = "checkpoints/precision_checkpoint.json"
    summary_file = "checkpoints/checkpoint_summary.json"
    
    print("🔍 Checking Checkpoint Status...")
    print("=" * 50)
    
    # Check if checkpoint files exist
    if not os.path.exists(checkpoint_file):
        print("❌ No checkpoint file found!")
        return
    
    # Load precision checkpoint
    with open(checkpoint_file, 'r') as f:
        checkpoint = json.load(f)
    
    print(f"📊 Precision Pipeline Status:")
    print(f"   Current Chunk: {checkpoint['chunk_number']}")
    print(f"   Records Processed: {checkpoint['total_processed']:,}")
    print(f"   Progress: {checkpoint['progress_percentage']}%")
    print(f"   Next Chunk: {checkpoint['next_chunk']}")
    print(f"   Remaining Chunks: {checkpoint['estimated_remaining_chunks']}")
    print(f"   Status: {checkpoint['status']}")
    print(f"   Last Updated: {checkpoint['timestamp']}")
    
    # Load summary if available
    if os.path.exists(summary_file):
        with open(summary_file, 'r') as f:
            summary = json.load(f)
        
        print(f"\n📈 Summary:")
        print(f"   Total Records: 7,485,544")
        print(f"   Remaining Records: {summary['checkpoint_summary']['remaining_records']:,}")
        print(f"   Estimated Completion: {summary['next_steps']['estimated_completion_time']}")
        print(f"   Chunk Size: {summary['checkpoint_settings']['chunk_size']:,}")
    
    print(f"\n✅ Ready to Resume!")
    print(f"🚀 Command: python manage.py run_entelligence_pipeline")
    print(f"   Will start from chunk {checkpoint['next_chunk']}")

if __name__ == "__main__":
    check_checkpoint_status()
