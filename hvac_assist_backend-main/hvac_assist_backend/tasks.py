from celery import shared_task
from django.core.management import call_command
from data_pipeline.pipeline_runner import run_pipeline
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def run_data_pipeline_task(self):
    """
    Celery task to run the Data Update Pipeline (S3 -> Cache).
    Scheduled via CELERY_BEAT_SCHEDULE in settings.py.
    """
    logger.info("Task 'run_data_pipeline_task' started by Celery Beat")
    
    try:
        success = run_pipeline()
        if success:
            logger.info("Task 'run_data_pipeline_task' completed successfully")
            return "Success"
        else:
            logger.error("Task 'run_data_pipeline_task' failed")
            return "Failed"
            
    except Exception as e:
        logger.exception(f"Task 'run_data_pipeline_task' raised an exception: {e}")
        raise e
