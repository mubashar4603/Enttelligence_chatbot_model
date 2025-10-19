#!/usr/bin/env python3
"""
🔍 SIMPLE PINECONE VECTOR COUNT CHECKER
Check actual vectors in Pinecone without Django dependencies
"""

import json
import os
from datetime import datetime
from pinecone import Pinecone

class SimplePineconeChecker:
    def __init__(self):
        """Initialize Pinecone connection"""
        self.config = {
            'PINECONE_API_KEY': "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ",
            'INDEX_NAME': "customer-database-vectors"
        }
        
        # Initialize Pinecone
        self.pc = Pinecone(api_key=self.config['PINECONE_API_KEY'])
        self.index = self.pc.Index(self.config['INDEX_NAME'])
    
    def get_pinecone_stats(self):
        """Get current Pinecone index statistics"""
        try:
            print("🔍 Checking Pinecone index statistics...")
            
            # Get index stats
            stats = self.index.describe_index_stats()
            
            print("📊 PINECONE INDEX STATISTICS:")
            print("=" * 50)
            print(f"Index Name: {self.config['INDEX_NAME']}")
            print(f"Total Vectors: {stats.total_vector_count:,}")
            print(f"Dimension: {stats.dimension}")
            print(f"Index Fullness: {stats.index_fullness:.2%}")
            
            return {
                'total_vectors': stats.total_vector_count,
                'dimension': stats.dimension,
                'index_fullness': stats.index_fullness,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error getting Pinecone stats: {e}")
            return None
    
    def check_sample_vectors(self, limit=3):
        """Check sample vectors to verify data quality"""
        try:
            print(f"\n🔍 Checking sample vectors (limit: {limit})...")
            
            # Query for sample vectors
            query_response = self.index.query(
                vector=[0.0] * 768,  # Dummy vector for sampling
                top_k=limit,
                include_metadata=True
            )
            
            print("📋 SAMPLE VECTORS:")
            print("-" * 40)
            
            for i, match in enumerate(query_response.matches):
                metadata = match.metadata
                print(f"Vector {i+1}:")
                print(f"  ID: {match.id}")
                print(f"  Title: {metadata.get('title', 'N/A')}")
                print(f"  Theater: {metadata.get('theater_name', 'N/A')}")
                print(f"  Reserved: {metadata.get('reserved', 'N/A')}")
                print(f"  Price: {metadata.get('price', 'N/A')}")
                print(f"  Chunk: {metadata.get('chunk_idx', 'N/A')}")
                print()
            
            return query_response.matches
            
        except Exception as e:
            print(f"❌ Error checking sample vectors: {e}")
            return []
    
    def update_checkpoint(self, pinecone_stats):
        """Update checkpoint with actual Pinecone vector count"""
        try:
            checkpoint_dir = "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/checkpoints"
            checkpoint_path = os.path.join(checkpoint_dir, 'pinecone_vector_checkpoint.json')
            
            # Create checkpoint data
            checkpoint_data = {
                'timestamp': datetime.now().isoformat(),
                'pinecone_stats': pinecone_stats,
                'total_vectors_in_pinecone': pinecone_stats['total_vectors'],
                'index_fullness': pinecone_stats['index_fullness'],
                'dimension': pinecone_stats['dimension'],
                'checkpoint_type': 'pinecone_vector_count',
                'status': 'verified'
            }
            
            # Ensure checkpoint directory exists
            os.makedirs(checkpoint_dir, exist_ok=True)
            
            # Save checkpoint
            with open(checkpoint_path, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            
            print(f"💾 Checkpoint updated: {checkpoint_path}")
            print(f"📊 Total vectors in Pinecone: {pinecone_stats['total_vectors']:,}")
            
            return checkpoint_data
            
        except Exception as e:
            print(f"❌ Error updating checkpoint: {e}")
            return None
    
    def compare_with_existing_checkpoints(self, pinecone_stats):
        """Compare current Pinecone count with existing checkpoints"""
        try:
            print("\n🔍 COMPARING WITH EXISTING CHECKPOINTS:")
            print("-" * 50)
            
            checkpoint_dir = "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/checkpoints"
            
            # Check existing checkpoints
            checkpoint_files = [
                'precision_checkpoint.json',
                'latest_checkpoint.json',
                'gpu_optimized_final.json'
            ]
            
            for checkpoint_file in checkpoint_files:
                checkpoint_path = os.path.join(checkpoint_dir, checkpoint_file)
                
                if os.path.exists(checkpoint_path):
                    with open(checkpoint_path, 'r') as f:
                        checkpoint_data = json.load(f)
                    
                    print(f"\n📄 {checkpoint_file}:")
                    print(f"  Timestamp: {checkpoint_data.get('timestamp', 'N/A')}")
                    
                    # Extract vector counts from different checkpoint formats
                    vectors_created = checkpoint_data.get('total_vectors_created', 
                                                        checkpoint_data.get('total_processed', 0))
                    
                    print(f"  Vectors Created: {vectors_created:,}")
                    print(f"  Pinecone Vectors: {pinecone_stats['total_vectors']:,}")
                    
                    if vectors_created > 0:
                        match_percentage = (pinecone_stats['total_vectors'] / vectors_created) * 100
                        print(f"  Match: {match_percentage:.1f}%")
                        
                        if match_percentage < 95:
                            print(f"  ⚠️  Warning: Significant difference detected!")
                        elif match_percentage > 105:
                            print(f"  ⚠️  Warning: More vectors in Pinecone than expected!")
                        else:
                            print(f"  ✅ Good match!")
                else:
                    print(f"\n📄 {checkpoint_file}: Not found")
            
        except Exception as e:
            print(f"❌ Error comparing checkpoints: {e}")
    
    def run_full_check(self):
        """Run complete Pinecone vector check and checkpoint update"""
        print("🚀 PINECONE VECTOR COUNT CHECKER")
        print("=" * 60)
        
        # Get Pinecone statistics
        pinecone_stats = self.get_pinecone_stats()
        
        if not pinecone_stats:
            print("❌ Failed to get Pinecone statistics")
            return False
        
        # Check sample vectors
        sample_vectors = self.check_sample_vectors(limit=3)
        
        # Compare with existing checkpoints
        self.compare_with_existing_checkpoints(pinecone_stats)
        
        # Update checkpoint
        checkpoint_data = self.update_checkpoint(pinecone_stats)
        
        if checkpoint_data:
            print("\n✅ CHECK COMPLETED SUCCESSFULLY!")
            print(f"📊 Total vectors in Pinecone: {pinecone_stats['total_vectors']:,}")
            print(f"💾 Checkpoint updated with current count")
            return True
        else:
            print("\n❌ CHECK FAILED!")
            return False

def main():
    """Main function"""
    checker = SimplePineconeChecker()
    success = checker.run_full_check()
    
    if success:
        print("\n🎉 Pinecone vector count verified and checkpoint updated!")
    else:
        print("\n💥 Failed to verify Pinecone vector count!")

if __name__ == "__main__":
    main()
