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
        self._load_env_credentials()
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3')

    def _load_env_credentials(self):
        """
        Manually load .env file to support AWS keys.
        Handles mapping AWS_ACCESS_KEY -> AWS_ACCESS_KEY_ID
        and AWS_SECRET_KEY -> AWS_SECRET_ACCESS_KEY
        """
        try:
            # Look for .env in project root (parent of data_pipeline)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            env_path = os.path.join(project_root, '.env')
            
            if os.path.exists(env_path):
                logger.info(f"Loading credentials from {env_path}")
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            parts = line.split('=', 1)
                            key = parts[0].strip()
                            value = parts[1].strip()
                            
                            # Remove quotes
                            if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
                                value = value[1:-1]
                                
                            # Map keys for boto3
                            if key == 'AWS_ACCESS_KEY':
                                os.environ['AWS_ACCESS_KEY_ID'] = value
                            elif key == 'AWS_SECRET_KEY':
                                os.environ['AWS_SECRET_ACCESS_KEY'] = value
                            elif key == 'AWS_REGION':
                                os.environ['AWS_DEFAULT_REGION'] = value
                                
        except Exception as e:
            logger.warning(f"Failed to load .env file: {e}")

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
