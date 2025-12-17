import os
import sys
from s3_manager import S3Manager
from processor import PipelineProcessor
from logger import setup_logger

logger = setup_logger()

# Constants
S3_BUCKET = 'ai-model-data-dump'
S3_FILE_KEY = 'AI Model Data.csv'

# Local path where we download the file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_PATH = os.path.join(BASE_DIR, 'similarity_engine_v2', 'data_pipeline_download.csv')

def run_pipeline():
    """
    Main entry point for the pipeline.
    """
    logger.info("="*50)
    logger.info("🎬 STARTING DATA PIPELINE EXECUTION")
    logger.info("="*50)
    
    try:
        # Check for local override file in the same directory as this script
        # This allows testing without S3 access if the user puts the file here manually
        local_override_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), S3_FILE_KEY)
        
        target_path = DOWNLOAD_PATH
        
        if os.path.exists(local_override_path):
            logger.info(f"⚠️ Found local override file: {local_override_path}")
            logger.info("⏩ Skipping S3 download and using local file.")
            target_path = local_override_path
        else:
            # Step 1: Download from S3
            s3 = S3Manager(bucket_name=S3_BUCKET)
            success = s3.download_file(S3_FILE_KEY, DOWNLOAD_PATH)
            
            if not success:
                logger.error("🛑 Pipeline aborted due to download failure.")
                return False

        # Step 2: Process and Update Cache
        # Use target_path which is either the S3 download or the local override
        processor = PipelineProcessor(input_file_path=target_path)
        processor.run()
        
        logger.info("✨ PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("="*50)
        return True

    except Exception as e:
        logger.critical(f"FATAL ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    run_pipeline()
