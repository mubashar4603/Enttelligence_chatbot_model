"""
Management command to pre-calculate and cache movie performance metrics.
This command should be run periodically (e.g., daily via cron) to keep metrics up-to-date.

Usage:
    python manage.py calculate_performance_metrics --all
    python manage.py calculate_performance_metrics --movie "Twisters"
    python manage.py calculate_performance_metrics --batch-size 50000
"""
import logging
from django.core.management.base import BaseCommand
from movies.performance_service import MoviePerformanceService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Calculate and cache movie performance metrics (DIR, DBR, DoD, etc.) for fast analytics queries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Calculate metrics for all movies',
        )
        parser.add_argument(
            '--movie',
            type=str,
            help='Calculate metrics for a specific movie title',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10000,
            help='Number of records to process per batch (default: 10000)',
        )
        parser.add_argument(
            '--update-only',
            action='store_true',
            help='Only update existing records, skip creation',
        )

    def handle(self, *args, **options):
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS("🎬 Movie Performance Metrics Calculator"))
        self.stdout.write("=" * 70)
        
        service = MoviePerformanceService()
        
        if options['all']:
            self.stdout.write("📊 Calculating metrics for ALL movies...")
            self.stdout.write(f"   Batch size: {options['batch_size']}")
            
            try:
                count = service.calculate_daily_performance_bulk(
                    title=None,
                    batch_size=options['batch_size']
                )
                self.stdout.write(self.style.SUCCESS(
                    f"\n✅ Successfully calculated/updated {count} performance records"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"\n❌ Error: {e}"))
                raise
        
        elif options['movie']:
            movie_title = options['movie']
            self.stdout.write(f"📊 Calculating metrics for '{movie_title}'...")
            
            try:
                count = service.calculate_daily_performance_bulk(
                    title=movie_title,
                    batch_size=options['batch_size']
                )
                self.stdout.write(self.style.SUCCESS(
                    f"\n✅ Successfully calculated/updated {count} performance records for '{movie_title}'"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"\n❌ Error: {e}"))
                raise
        
        else:
            self.stdout.write(self.style.WARNING(
                "Please specify --all or --movie <title>"
            ))
            self.stdout.write("\nExample:")
            self.stdout.write("  python manage.py calculate_performance_metrics --all")
            self.stdout.write("  python manage.py calculate_performance_metrics --movie 'Twisters'")

