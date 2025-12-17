import sys
import os
from django.core.management.base import BaseCommand

# Add data_pipeline to path so we can import it
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(BASE_DIR, 'data_pipeline'))

from pipeline_runner import run_pipeline


class Command(BaseCommand):
    help = 'Run the data pipeline to fetch, process, and cache movie data'

    def handle(self, *args, **options):
        """Execute the pipeline"""
        self.stdout.write(self.style.SUCCESS('Starting data pipeline...'))
        
        try:
            run_pipeline()
            self.stdout.write(self.style.SUCCESS('Pipeline completed successfully!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Pipeline failed: {str(e)}'))
            raise
