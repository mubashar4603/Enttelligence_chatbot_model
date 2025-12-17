import boto3
import os
from botocore.exceptions import ClientError
from logger import setup_logger

logger = setup_logger()

class S3Manager:
    """
    Handles S3 operations for the data pipeline.
    Uses instance metadata credentials (IAM Role) by default.
    """
    def __init__(self, bucket_name='ai-model-data-dump'):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3')

    def download_file(self, s3_key, local_path):
        """
        Download a file from S3 to local path.
        """
        try:
            logger.info(f"⬇️ Downloading s3://{self.bucket_name}/{s3_key} to {local_path}...")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            self.s3_client.download_file(self.bucket_name, s3_key, local_path)
            
            # Verify file exists and has size
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                logger.info(f"✅ Download successful. Size: {os.path.getsize(local_path) / 1024 / 1024:.2f} MB")
                return True
            else:
                logger.error("❌ Download failed: File is empty or missing")
                return False
                
        except ClientError as e:
            if e.response['Error']['Code'] == "404":
                logger.error(f"❌ File not found in S3: {s3_key}")
            else:
                logger.error(f"❌ S3 Error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error downloading from S3: {e}")
            raise
