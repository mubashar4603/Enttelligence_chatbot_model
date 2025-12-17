from django.core.management.base import BaseCommand
from data_pipeline.pipeline_runner import run_pipeline

class Command(BaseCommand):
    help = 'Runs the Data Update Pipeline (S3 -> Cache)'

    def handle(self, *args, **options):
        self.stdout.write("Starting Data Update Pipeline...")
        
        success = run_pipeline()
        
        if success:
            self.stdout.write(self.style.SUCCESS('Successfully ran Data Update Pipeline'))
        else:
            self.stdout.write(self.style.ERROR('Pipeline Failed. Check logs.'))
