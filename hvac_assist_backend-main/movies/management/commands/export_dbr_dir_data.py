"""
Django management command to export all DBR and DIR data for all movies to CSV.
Gets data from MovieDailyPerformance table which already has DBR/DIR and cumulative values.

Usage:
    python manage.py export_dbr_dir_data [--output filename.csv] [--movie "Movie Title"]
"""
import csv
import os
from django.core.management.base import BaseCommand
from django.db.models import Q, Min, Max
from movies.models import MovieDailyPerformance
from decimal import Decimal


class Command(BaseCommand):
    help = 'Export all DBR and DIR data for all movies to CSV file (from MovieDailyPerformance table)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='movie_dbr_dir_data.csv',
            help='Output CSV filename (default: movie_dbr_dir_data.csv)'
        )
        parser.add_argument(
            '--movie',
            type=str,
            default=None,
            help='Filter by specific movie title (optional)'
        )
        parser.add_argument(
            '--include-dbr-only',
            action='store_true',
            help='Include only records with DBR values (presales data)'
        )
        parser.add_argument(
            '--include-dir-only',
            action='store_true',
            help='Include only records with DIR values (post-release data)'
        )

    def handle(self, *args, **options):
        output_file = options['output']
        movie_filter = options['movie']
        include_dbr_only = options['include_dbr_only']
        include_dir_only = options['include_dir_only']

        self.stdout.write(f"Starting export of DBR and DIR data from MovieDailyPerformance table...")
        
        # Build query
        query = MovieDailyPerformance.objects.all()
        
        # Apply filters
        if movie_filter:
            query = query.filter(title__icontains=movie_filter)
            self.stdout.write(f"Filtering for movie: {movie_filter}")
        
        if include_dbr_only:
            query = query.filter(dbr_value__isnull=False)
            self.stdout.write("Including only records with DBR values")
        
        if include_dir_only:
            query = query.filter(dir_value__isnull=False)
            self.stdout.write("Including only records with DIR values")
        
        # Order by title, release_date, date_sh
        query = query.order_by('title', 'release_date', 'date_sh')
        
        total_records = query.count()
        self.stdout.write(f"Found {total_records} records to export")
        
        if total_records == 0:
            self.stdout.write(self.style.WARNING("No records found to export!"))
            return
        
        # Get unique movies for summary
        unique_movies = query.values('title', 'release_date').distinct()
        self.stdout.write(f"Found {unique_movies.count()} unique movies")
        
        # Prepare CSV file
        output_path = os.path.join(os.getcwd(), output_file)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'title',
                'release_date',
                'date_sh',
                'dir_value',
                'dbr_value',
                'total_revenue',
                'total_reserved_seats',
                'total_seats',
                'cumulative_revenue',
                'cumulative_reserved',
                'avg_price',
                'occupancy_rate',
                'dod_revenue_change',
                'dod_reserved_change',
                'calculated_at'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Write data in batches to handle large datasets
            batch_size = 10000
            written = 0
            dbr_values = []
            dir_values = []
            
            self.stdout.write("Writing data to CSV...")
            
            for i in range(0, total_records, batch_size):
                batch = query[i:i + batch_size]
                
                for record in batch:
                    # Convert Decimal to float for CSV
                    def decimal_to_float(value):
                        if value is None:
                            return None
                        if isinstance(value, Decimal):
                            return float(value)
                        return value
                    
                    # Store DBR/DIR values for statistics
                    if record.dbr_value is not None:
                        dbr_values.append(record.dbr_value)
                    if record.dir_value is not None:
                        dir_values.append(record.dir_value)
                    
                    row = {
                        'title': record.title or '',
                        'release_date': record.release_date.isoformat() if record.release_date else '',
                        'date_sh': record.date_sh.isoformat() if record.date_sh else '',
                        'dir_value': record.dir_value if record.dir_value is not None else '',
                        'dbr_value': record.dbr_value if record.dbr_value is not None else '',
                        'total_revenue': decimal_to_float(record.total_revenue) if record.total_revenue else 0.0,
                        'total_reserved_seats': record.total_reserved_seats if record.total_reserved_seats else 0,
                        'total_seats': record.total_seats if record.total_seats else 0,
                        'cumulative_revenue': decimal_to_float(record.cumulative_revenue) if record.cumulative_revenue else 0.0,
                        'cumulative_reserved': record.cumulative_reserved if record.cumulative_reserved else 0,
                        'avg_price': decimal_to_float(record.avg_price) if record.avg_price else '',
                        'occupancy_rate': record.occupancy_rate if record.occupancy_rate is not None else '',
                        'dod_revenue_change': record.dod_revenue_change if record.dod_revenue_change is not None else '',
                        'dod_reserved_change': record.dod_reserved_change if record.dod_reserved_change is not None else '',
                        'calculated_at': record.calculated_at.isoformat() if record.calculated_at else ''
                    }
                    
                    writer.writerow(row)
                    written += 1
                
                if (i + batch_size) % 50000 == 0:
                    self.stdout.write(f"  Processed {min(i + batch_size, total_records)} / {total_records} records...")
            
            self.stdout.write(f"  Completed: {written} records written")
        
        # Print summary
        self.stdout.write(self.style.SUCCESS(f"\n✅ Successfully exported {written} records to: {output_path}"))
        
        # Print summary statistics
        self.stdout.write("\n📊 Summary Statistics:")
        
        # Count records by type
        dbr_count = len(dbr_values)
        dir_count = len(dir_values)
        both_count = query.filter(dbr_value__isnull=False, dir_value__isnull=False).count()
        
        self.stdout.write(f"  - Records with DBR values: {dbr_count}")
        self.stdout.write(f"  - Records with DIR values: {dir_count}")
        self.stdout.write(f"  - Records with both DBR and DIR: {both_count}")
        
        # DBR range
        if dbr_values:
            self.stdout.write(f"  - DBR range: {min(dbr_values)} to {max(dbr_values)}")
        
        # DIR range
        if dir_values:
            self.stdout.write(f"  - DIR range: {min(dir_values)} to {max(dir_values)}")
        
        # Unique movies
        self.stdout.write(f"  - Unique movies: {unique_movies.count()}")
        
        # Calculate First Weekend Revenue (DIR -1, 1, 2) for each movie
        self.stdout.write("\n🎬 First Weekend Revenue (DIR -1, 1, 2):")
        self.stdout.write("Note: First Weekend uses DIR values -1, 1, 2")
        self.stdout.write("SQL Logic: (date_sh - release_date) BETWEEN -1 AND 1 → DIR: -1, 1, 2")
        self.stdout.write("\n⚠️  IMPORTANT: First Weekend Revenue ≠ Cumulative Presales")
        self.stdout.write("   - Cumulative Presales (DBR) = presales BEFORE release")
        self.stdout.write("   - First Weekend Revenue (DIR -1,1,2) = revenue AFTER release")
        
        first_weekend_query = MovieDailyPerformance.objects.filter(
            dir_value__in=[-1, 1, 2]
        )
        if movie_filter:
            first_weekend_query = first_weekend_query.filter(title__icontains=movie_filter)
        
        from django.db.models import Sum
        first_weekend_by_movie = (
            first_weekend_query
            .values('title', 'release_date')
            .annotate(first_weekend_revenue=Sum('total_revenue'))
            .order_by('-first_weekend_revenue')
        )
        
        for movie_data in first_weekend_by_movie[:10]:  # Show top 10
            title = movie_data['title']
            revenue = float(movie_data['first_weekend_revenue'] or 0)
            self.stdout.write(f"  - {title}: ${revenue:,.2f}")
        
        # File size
        file_size = os.path.getsize(output_path)
        file_size_mb = file_size / (1024 * 1024)
        self.stdout.write(f"\n  - File size: {file_size_mb:.2f} MB")

