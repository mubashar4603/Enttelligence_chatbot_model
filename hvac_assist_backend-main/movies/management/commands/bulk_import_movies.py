#!/usr/bin/env python3
"""
HIGH-PERFORMANCE BULK INSERT COMMAND
Optimized for 7.4M records with 50k chunks and bulk operations
"""

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from movies.models import Movie, FilmPerformanceSummary, TheaterPerformance, MarketAnalysis, ComparativeAnalysis
import pandas as pd
import numpy as np
import os
import time
import json
from datetime import datetime, date, time as dt_time
import logging
from decimal import Decimal, InvalidOperation
from tqdm import tqdm
import psycopg2
from psycopg2.extras import execute_values
import gc
import psutil

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'High-performance bulk import of CSV data into Movies table'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-path',
            type=str,
            default='/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv',
            help='Path to the CSV file',
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=50000,
            help='Number of records to process per chunk (default: 50000)',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Clear existing Movie records before inserting',
        )
        parser.add_argument(
            '--checkpoint-interval',
            type=int,
            default=2,
            help='Save checkpoint every N chunks (default: 2)',
        )
        parser.add_argument(
            '--bulk-size',
            type=int,
            default=1000,
            help='Bulk insert batch size (default: 1000)',
        )
        parser.add_argument(
            '--memory-limit-mb',
            type=int,
            default=4096,
            help='Memory limit in MB before forcing garbage collection (default: 4096)',
        )
        parser.add_argument(
            '--analytics-chunk-size',
            type=int,
            default=10000,
            help='Chunk size for analytics processing (default: 10000)',
        )
        parser.add_argument(
            '--clear-checkpoints',
            action='store_true',
            help='Clear existing checkpoints and start from scratch',
        )
        parser.add_argument(
            '--analytics-tables',
            action='store_true',
            help='Also populate analytics tables (FilmPerformanceSummary, TheaterPerformance, MarketAnalysis)',
        )
        parser.add_argument(
            '--skip-movies',
            action='store_true',
            help='Skip Movies table population (use when Movies table is already populated)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting HIGH-PERFORMANCE Bulk Import')
        )
        
        if options['skip_movies']:
            self.stdout.write(
                self.style.WARNING('⏭️ Skipping Movies table (already populated)')
            )
        
        if options['analytics_tables']:
            self.stdout.write(
                self.style.SUCCESS('📊 Processing Analytics tables')
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'📊 Processing {options["chunk_size"]:,} records per chunk')
        )
        self.stdout.write(
            self.style.SUCCESS(f'⚡ Bulk insert size: {options["bulk_size"]:,} records')
        )
        
        try:
            # Initialize import process
            self.start_time = time.time()
            csv_path = options['csv_path']
            chunk_size = options['chunk_size']
            checkpoint_interval = options['checkpoint_interval']
            bulk_size = options['bulk_size']
            
            # Check if CSV file exists
            if not os.path.exists(csv_path):
                self.stdout.write(
                    self.style.ERROR(f'❌ CSV file not found: {csv_path}')
                )
                return
            
            # Reset database if requested
            if options['reset']:
                self.stdout.write('🗑️ Clearing existing data...')
                if not options['skip_movies']:
                    self.stdout.write('🗑️ Clearing existing Movie records...')
                    Movie.objects.all().delete()
                
                # Always clear analytics tables when reset is requested
                self.stdout.write('🗑️ Clearing analytics tables...')
                
                try:
                    film_count = FilmPerformanceSummary.objects.count()
                    theater_count = TheaterPerformance.objects.count()
                    market_count = MarketAnalysis.objects.count()
                    comparative_count = ComparativeAnalysis.objects.count()
                    
                    # Use raw SQL to ensure complete clearing
                    with connection.cursor() as cursor:
                        cursor.execute("DELETE FROM movies_filmperformancesummary")
                        cursor.execute("DELETE FROM movies_theaterperformance") 
                        cursor.execute("DELETE FROM movies_marketanalysis")
                        cursor.execute("DELETE FROM movies_comparativeanalysis")
                    
                    # Reset auto-increment sequences
                    with connection.cursor() as cursor:
                        cursor.execute("ALTER SEQUENCE movies_filmperformancesummary_id_seq RESTART WITH 1")
                        cursor.execute("ALTER SEQUENCE movies_theaterperformance_id_seq RESTART WITH 1")
                        cursor.execute("ALTER SEQUENCE movies_marketanalysis_id_seq RESTART WITH 1")
                        cursor.execute("ALTER SEQUENCE movies_comparativeanalysis_id_seq RESTART WITH 1")
                    
                    self.stdout.write(f'✅ Cleared {film_count:,} FilmPerformanceSummary, {theater_count:,} TheaterPerformance, {market_count:,} MarketAnalysis, {comparative_count:,} ComparativeAnalysis records')
                    self.stdout.write('✅ Database cleared and sequences reset')
                    
                except Exception as e:
                    self.stdout.write(f'⚠️ Error during clearing: {e}')
                    # Fallback to Django ORM
                    FilmPerformanceSummary.objects.all().delete()
                    TheaterPerformance.objects.all().delete()
                    MarketAnalysis.objects.all().delete()
                    ComparativeAnalysis.objects.all().delete()
                    self.stdout.write('✅ Database cleared (fallback method)')
            
            # Get total row count
            total_rows = self.get_total_rows(csv_path)
            self.stdout.write(f'📈 Total rows in CSV: {total_rows:,}')
            
            # Handle checkpoint clearing
            if options['clear_checkpoints']:
                self.clear_checkpoints()
                start_chunk = 1
                total_processed = 0
                self.stdout.write(
                    self.style.SUCCESS('🚀 Starting from scratch (checkpoints cleared)')
                )
            else:
                # Check for existing checkpoint
                checkpoint_data = self.load_checkpoint()
                start_chunk = checkpoint_data.get('chunk_number', 0) + 1
                total_processed = checkpoint_data.get('total_processed', 0)
                
                if start_chunk > 1:
                    self.stdout.write(
                        self.style.WARNING(f'🔄 Resuming from chunk {start_chunk}')
                    )
                    self.stdout.write(f'📊 Already processed: {total_processed:,} records')
                else:
                    self.stdout.write(
                        self.style.SUCCESS('🚀 Starting from beginning')
                    )
            
            # Process CSV in chunks with bulk operations
            self.process_csv_bulk(
                csv_path, chunk_size, checkpoint_interval, 
                start_chunk, total_processed, total_rows, bulk_size, 
                options['analytics_tables'], options['skip_movies'],
                options['memory_limit_mb'], options['analytics_chunk_size']
            )
            
            self.stdout.write(
                self.style.SUCCESS('✅ High-performance bulk import completed successfully!')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Import failed: {e}')
            )
            logger.exception("Bulk import failed")
            raise

    def get_memory_usage_mb(self):
        """Get current memory usage in MB"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except:
            return 0

    def force_memory_cleanup(self):
        """Force garbage collection and memory cleanup"""
        gc.collect()
        if hasattr(gc, 'collect'):
            gc.collect()

    def check_memory_limit(self, memory_limit_mb):
        """Check if memory usage exceeds limit and cleanup if needed"""
        current_memory = self.get_memory_usage_mb()
        if current_memory > memory_limit_mb:
            self.stdout.write(
                self.style.WARNING(f'🧹 Memory usage: {current_memory:.1f}MB > {memory_limit_mb}MB limit. Forcing cleanup...')
            )
            self.force_memory_cleanup()
            new_memory = self.get_memory_usage_mb()
            self.stdout.write(f'✅ Memory after cleanup: {new_memory:.1f}MB')

    def clear_checkpoints(self):
        """Clear all existing checkpoints"""
        checkpoint_files = [
            'checkpoints/bulk_import_checkpoint.json',
            'checkpoints/bulk_import_final.json'
        ]
        
        cleared_files = []
        for checkpoint_file in checkpoint_files:
            if os.path.exists(checkpoint_file):
                os.remove(checkpoint_file)
                cleared_files.append(checkpoint_file)
        
        if cleared_files:
            self.stdout.write(
                self.style.SUCCESS(f'🗑️ Cleared checkpoint files: {", ".join(cleared_files)}')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ No checkpoint files found to clear')
            )

    def get_total_rows(self, csv_path):
        """Get total number of rows in CSV file"""
        with open(csv_path, 'r') as f:
            return sum(1 for line in f) - 1  # Subtract header

    def load_checkpoint(self):
        """Load existing checkpoint if available"""
        checkpoint_path = 'checkpoints/bulk_import_checkpoint.json'
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                return json.load(f)
        return {'chunk_number': 0, 'total_processed': 0}

    def save_checkpoint(self, chunk_number, total_processed, total_inserted):
        """Save progress checkpoint"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'chunk_number': chunk_number,
            'total_processed': total_processed,
            'total_inserted': total_inserted,
            'status': 'in_progress'
        }
        
        os.makedirs('checkpoints', exist_ok=True)
        checkpoint_path = 'checkpoints/bulk_import_checkpoint.json'
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        self.stdout.write(f'💾 Checkpoint saved: {total_processed:,} records processed')

    def parse_price(self, price_str):
        """Parse price string and return Decimal"""
        try:
            if pd.isna(price_str) or price_str == '':
                return Decimal('0.00')
            
            price_clean = str(price_str).replace('$', '').replace(',', '').strip()
            if ',' in price_clean:
                price_clean = price_clean.split(',')[0]
            
            return Decimal(price_clean) if price_clean else Decimal('0.00')
        except (ValueError, InvalidOperation):
            return Decimal('0.00')

    def parse_date(self, date_str):
        """Parse date string and return date object"""
        try:
            if pd.isna(date_str) or date_str == '':
                return date.today()
            
            date_str = str(date_str).strip()
            
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            
            return date.today()
        except Exception:
            return date.today()

    def parse_time(self, time_str):
        """Parse time string and return time object"""
        try:
            if pd.isna(time_str) or time_str == '':
                return dt_time(0, 0, 0)
            
            time_str = str(time_str).strip()
            
            for fmt in ['%H:%M:%S', '%H:%M', '%I:%M %p', '%I:%M:%S %p']:
                try:
                    return datetime.strptime(time_str, fmt).time()
                except ValueError:
                    continue
            
            return dt_time(0, 0, 0)
        except Exception:
            return dt_time(0, 0, 0)

    def parse_datetime(self, datetime_str):
        """Parse datetime string and return datetime object"""
        try:
            if pd.isna(datetime_str) or datetime_str == '':
                return datetime.now()
            
            datetime_str = str(datetime_str).strip()
            
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M']:
                try:
                    return datetime.strptime(datetime_str, fmt)
                except ValueError:
                    continue
            
            return datetime.now()
        except Exception:
            return datetime.now()

    def safe_int(self, value, default=0):
        """Safely convert value to integer"""
        try:
            if pd.isna(value) or value == '':
                return default
            return int(float(str(value)))
        except (ValueError, TypeError):
            return default

    def safe_decimal(self, value, default=0.0):
        """Safely convert value to Decimal, handling NaN and invalid values"""
        try:
            if pd.isna(value) or value == 'NaN' or value == '' or value is None:
                return default
            return Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation):
            return default

    def safe_float(self, value, default=0.0):
        """Safely convert value to float, handling NaN and invalid values"""
        try:
            if pd.isna(value) or value == 'NaN' or value == '' or value is None:
                return default
            return float(str(value))
        except (ValueError, TypeError):
            return default

    def safe_str(self, value, max_length=None):
        """Safely convert value to string, handling NaN and invalid values"""
        try:
            if pd.isna(value) or value is None:
                return ''
            
            # Convert to string and strip whitespace
            str_value = str(value).strip()
            
            # Truncate if max_length is specified
            if max_length and len(str_value) > max_length:
                str_value = str_value[:max_length]
            
            return str_value
        except (ValueError, TypeError):
            return ''

    def process_csv_bulk(self, csv_path, chunk_size, checkpoint_interval, 
                        start_chunk, total_processed, total_rows, bulk_size, analytics_tables=False, skip_movies=False, 
                        memory_limit_mb=4096, analytics_chunk_size=10000):
        """Process CSV file in chunks with bulk operations"""
        
        chunk_iterator = pd.read_csv(csv_path, chunksize=chunk_size, low_memory=False, 
                                    dtype={'price': 'str', 'child': 'str', 'senior': 'str'})
        total_inserted = 0
        
        # Create progress bar
        total_chunks = (total_rows + chunk_size - 1) // chunk_size
        pbar = tqdm(total=total_chunks, desc="Processing chunks", unit="chunk")
        
        # Initial memory check
        initial_memory = self.get_memory_usage_mb()
        self.stdout.write(f'🚀 Starting with {initial_memory:.1f}MB memory usage')
        
        for chunk_num, chunk_df in enumerate(chunk_iterator, start=1):
            if chunk_num < start_chunk:
                pbar.update(1)
                continue
            
            chunk_start_time = time.time()
            
            try:
                # Store chunk size before processing
                chunk_size_actual = len(chunk_df)
                
                # Check memory usage before processing
                self.check_memory_limit(memory_limit_mb)
                
                # Process chunk with bulk operations
                inserted_count = 0
                if not skip_movies:
                    inserted_count = self.process_chunk_bulk(chunk_df, chunk_num, bulk_size)
                    total_inserted += inserted_count
                
                total_processed += chunk_size_actual
                
                # Process analytics tables if requested (with smaller chunks to reduce memory)
                if analytics_tables:
                    analytics_inserted = self.process_analytics_chunk_optimized(chunk_df, chunk_num, analytics_chunk_size)
                    total_inserted += analytics_inserted
                
                # Clear memory explicitly
                del chunk_df
                self.force_memory_cleanup()
                
                # Save checkpoint periodically
                if chunk_num % checkpoint_interval == 0:
                    self.save_checkpoint(chunk_num, total_processed, total_inserted)
                
                # Show progress
                chunk_time = time.time() - chunk_start_time
                progress = (total_processed / total_rows) * 100
                
                # Update progress bar with memory info
                current_memory = self.get_memory_usage_mb()
                if skip_movies and analytics_tables:
                    pbar.set_postfix({
                        'Processed': f'{total_processed:,}',
                        'Analytics': 'Processing',
                        'Progress': f'{progress:.1f}%',
                        'Speed': f'{chunk_size_actual/chunk_time:.0f} rec/s',
                        'Memory': f'{current_memory:.0f}MB'
                    })
                else:
                    pbar.set_postfix({
                        'Processed': f'{total_processed:,}',
                        'Inserted': f'{total_inserted:,}',
                        'Progress': f'{progress:.1f}%',
                        'Speed': f'{chunk_size_actual/chunk_time:.0f} rec/s',
                        'Memory': f'{current_memory:.0f}MB'
                    })
                pbar.update(1)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Chunk {chunk_num} failed: {e}')
                )
                pbar.close()
                raise
        
        pbar.close()
        
        # Final memory check and cleanup
        final_memory = self.get_memory_usage_mb()
        self.force_memory_cleanup()
        cleanup_memory = self.get_memory_usage_mb()
        
        self.stdout.write(f'📊 Final memory usage: {final_memory:.1f}MB → {cleanup_memory:.1f}MB after cleanup')
        self.stdout.write(f'💾 Memory saved: {final_memory - cleanup_memory:.1f}MB')
        
        # Final checkpoint
        self.save_final_checkpoint(total_processed, total_inserted)

    def process_chunk_bulk(self, chunk_df, chunk_num, bulk_size):
        """Process a single chunk with bulk operations"""
        movies_data = []
        
        for idx, row in chunk_df.iterrows():
            try:
                # Parse and prepare data for bulk insert - ALL 46 COLUMNS INCLUDED
                movie_data = (
                    self.safe_str(row.get('theater_id', ''), 100),           # theater_id
                    self.safe_str(row.get('mm_id', ''), 100),               # mm_id
                    self.safe_str(row.get('circuit_name', ''), 255),        # circuit_name
                    self.safe_str(row.get('theater_name', ''), 255),        # theater_name
                    self.safe_str(row.get('theater_address', ''), 255),    # theater_address
                    self.safe_str(row.get('theater_city', ''), 100),        # theater_city
                    self.safe_str(row.get('theater_state', ''), 50),        # theater_state
                    self.safe_str(row.get('theater_zip', ''), 20),          # theater_zip
                    self.safe_str(row.get('country', ''), 50),              # country
                    self.safe_str(row.get('dma', ''), 100),                 # dma
                    self.safe_str(row.get('title', ''), 255),               # title
                    self.safe_str(row.get('studio_name', ''), 255),        # studio_name
                    self.parse_date(row.get('release_date')),               # release_date
                    self.safe_int(row.get('runtime')),                      # runtime
                    self.safe_str(row.get('genre', ''), 100),               # genre
                    self.safe_str(row.get('rating', ''), 20),               # rating
                    self.parse_date(row.get('date_sh')),                    # date_sh
                    self.parse_time(row.get('time_sh')),                    # time_sh
                    self.safe_str(row.get('auditorium', ''), 50),           # auditorium
                    self.safe_str(row.get('screen_format', ''), 50),       # screen_format
                    self.safe_str(row.get('movie_format', ''), 50),        # movie_format
                    self.safe_str(row.get('language_format', ''), 50),     # language_format
                    self.parse_price(row.get('price')),                     # price
                    self.parse_price(row.get('child')),                     # child
                    self.parse_price(row.get('senior')),                    # senior
                    self.safe_int(row.get('total_seats')),                  # total_seats
                    self.safe_int(row.get('available')),                   # available
                    self.safe_int(row.get('reserved')),                    # reserved
                    self.safe_int(row.get('checkered')),                   # checkered
                    self.safe_int(row.get('actual_total_seats')),          # actual_total_seats
                    self.safe_int(row.get('actual_available')),            # actual_available
                    self.safe_int(row.get('actual_reserved')),             # actual_reserved
                    self.safe_int(row.get('actual_checkered')),            # actual_checkered
                    self.safe_int(row.get('before_reserved')),             # before_reserved
                    self.safe_int(row.get('on_reserved')),                 # on_reserved
                    self.safe_int(row.get('after_reserved')),              # after_reserved
                    self.safe_str(row.get('seating_type', ''), 50),        # seating_type
                    self.safe_str(row.get('amenities', ''), 1000),          # amenities
                    bool(row.get('ticket_availability', True)),            # ticket_availability
                    bool(row.get('is_ticketing', True)),                   # is_ticketing
                    self.safe_str(row.get('source_flag', ''), 50),         # source_flag
                    self.parse_datetime(row.get('last_updates')),          # last_updates
                    self.parse_date(row.get('running_date')),               # running_date
                    self.parse_datetime(row.get('dsr_date_sh')),           # dsr_date_sh
                    self.parse_datetime(row.get('dsr_last_updates')),      # dsr_last_updates
                )
                
                movies_data.append(movie_data)
                
            except Exception as e:
                logger.warning(f"⚠️ Skipping row {idx} in chunk {chunk_num}: {e}")
                continue
        
        # Bulk insert using raw SQL for maximum performance
        if movies_data:
            inserted_count = self.bulk_insert_movies(movies_data, bulk_size)
            return inserted_count
        
        return 0

    def bulk_insert_movies(self, movies_data, bulk_size):
        """Perform bulk insert using raw SQL for maximum performance with memory optimization"""
        try:
            with connection.cursor() as cursor:
                # Prepare the SQL statement - ALL 46 COLUMNS INCLUDED (excluding auto-generated id)
                insert_sql = """
                INSERT INTO movies (
                    theater_id, mm_id, circuit_name, theater_name, theater_address,
                    theater_city, theater_state, theater_zip, country, dma,
                    title, studio_name, release_date, runtime, genre, rating,
                    date_sh, time_sh, auditorium, screen_format, movie_format,
                    language_format, price, child, senior, total_seats, available,
                    reserved, checkered, actual_total_seats, actual_available,
                    actual_reserved, actual_checkered, before_reserved, on_reserved,
                    after_reserved, seating_type, amenities, ticket_availability,
                    is_ticketing, source_flag, last_updates, running_date,
                    dsr_date_sh, dsr_last_updates
                ) VALUES %s
                """
                
                # Insert in smaller batches for better memory management
                total_inserted = 0
                optimized_bulk_size = min(bulk_size, 500)  # Reduce batch size for memory efficiency
                
                for i in range(0, len(movies_data), optimized_bulk_size):
                    batch = movies_data[i:i + optimized_bulk_size]
                    execute_values(
                        cursor, insert_sql, batch, 
                        template=None, page_size=optimized_bulk_size
                    )
                    total_inserted += len(batch)
                    
                    # Clear batch from memory immediately
                    del batch
                    
                    # Force garbage collection every few batches to prevent memory buildup
                    if i % (optimized_bulk_size * 5) == 0:
                        self.force_memory_cleanup()
                
                return total_inserted
                
        except Exception as e:
            logger.error(f"❌ Bulk insert failed: {e}")
            # Fallback to Django bulk_create
            return self.fallback_bulk_create(movies_data)

    def fallback_bulk_create(self, movies_data):
        """Fallback to Django bulk_create if raw SQL fails with memory optimization"""
        try:
            # Process in smaller batches to avoid memory issues
            batch_size = 500
            total_created = 0
            
            for i in range(0, len(movies_data), batch_size):
                batch_data = movies_data[i:i + batch_size]
                movies_to_create = []
                
                for data_tuple in batch_data:
                    movie_data = {
                        'theater_id': data_tuple[0],
                        'mm_id': data_tuple[1],
                        'circuit_name': data_tuple[2],
                        'theater_name': data_tuple[3],
                        'theater_address': data_tuple[4],
                        'theater_city': data_tuple[5],
                        'theater_state': data_tuple[6],
                        'theater_zip': data_tuple[7],
                        'country': data_tuple[8],
                        'dma': data_tuple[9],
                        'title': data_tuple[10],
                        'studio_name': data_tuple[11],
                        'release_date': data_tuple[12],
                        'runtime': data_tuple[13],
                        'genre': data_tuple[14],
                        'rating': data_tuple[15],
                        'date_sh': data_tuple[16],
                        'time_sh': data_tuple[17],
                        'auditorium': data_tuple[18],
                        'screen_format': data_tuple[19],
                        'movie_format': data_tuple[20],
                        'language_format': data_tuple[21],
                        'price': data_tuple[22],
                        'child': data_tuple[23],
                        'senior': data_tuple[24],
                        'total_seats': data_tuple[25],
                        'available': data_tuple[26],
                        'reserved': data_tuple[27],
                        'checkered': data_tuple[28],
                        'actual_total_seats': data_tuple[29],
                        'actual_available': data_tuple[30],
                        'actual_reserved': data_tuple[31],
                        'actual_checkered': data_tuple[32],
                        'before_reserved': data_tuple[33],
                        'on_reserved': data_tuple[34],
                        'after_reserved': data_tuple[35],
                        'seating_type': data_tuple[36],
                        'amenities': data_tuple[37],
                        'ticket_availability': data_tuple[38],
                        'is_ticketing': data_tuple[39],
                        'source_flag': data_tuple[40],
                        'last_updates': data_tuple[41],
                        'running_date': data_tuple[42],
                        'dsr_date_sh': data_tuple[43],
                        'dsr_last_updates': data_tuple[44],
                    }
                    movies_to_create.append(Movie(**movie_data))
                
                # Insert batch and clean up immediately
                with transaction.atomic():
                    Movie.objects.bulk_create(movies_to_create, batch_size=batch_size)
                
                total_created += len(movies_to_create)
                
                # Clean up memory
                del movies_to_create, batch_data
                if i % (batch_size * 5) == 0:
                    self.force_memory_cleanup()
            
            return total_created
            
        except Exception as e:
            logger.error(f"❌ Fallback bulk create failed: {e}")
            return 0

    def save_final_checkpoint(self, total_processed, total_inserted):
        """Save final checkpoint"""
        final_checkpoint = {
            'timestamp': datetime.now().isoformat(),
            'total_processed': total_processed,
            'total_inserted': total_inserted,
            'status': 'completed',
            'completion_time': datetime.now().isoformat()
        }
        
        os.makedirs('checkpoints', exist_ok=True)
        checkpoint_path = 'checkpoints/bulk_import_final.json'
        
        with open(checkpoint_path, 'w') as f:
            json.dump(final_checkpoint, f, indent=2)
        
        self.stdout.write(f'💾 Final checkpoint saved: {total_inserted:,} records inserted')
        self.stdout.write(f'📊 Total processing time: {time.time() - self.start_time:.2f} seconds')
        self.stdout.write(f'⚡ Average speed: {total_processed/(time.time() - self.start_time):.0f} records/second')

    def process_analytics_chunk(self, chunk_df, chunk_num):
        """Process analytics tables from chunk data"""
        total_analytics_inserted = 0
        try:
            # Process FilmPerformanceSummary
            film_count = self.process_film_performance_summary(chunk_df, chunk_num)
            total_analytics_inserted += film_count
            
            # Process TheaterPerformance
            theater_count = self.process_theater_performance(chunk_df, chunk_num)
            total_analytics_inserted += theater_count
            
            # Process MarketAnalysis
            market_count = self.process_market_analysis(chunk_df, chunk_num)
            total_analytics_inserted += market_count
            
            # Process ComparativeAnalysis
            comparative_count = self.process_comparative_analysis(chunk_df, chunk_num)
            total_analytics_inserted += comparative_count
            
        except Exception as e:
            logger.warning(f"⚠️ Analytics processing failed for chunk {chunk_num}: {e}")
        
        return total_analytics_inserted

    def process_analytics_chunk_optimized(self, chunk_df, chunk_num, analytics_chunk_size):
        """Process analytics tables with memory optimization"""
        total_analytics_inserted = 0
        try:
            # Process in smaller sub-chunks to reduce memory usage
            chunk_size = len(chunk_df)
            if chunk_size <= analytics_chunk_size:
                # Process entire chunk if it's small enough
                total_analytics_inserted = self.process_analytics_chunk(chunk_df, chunk_num)
            else:
                # Process in smaller sub-chunks
                for start_idx in range(0, chunk_size, analytics_chunk_size):
                    end_idx = min(start_idx + analytics_chunk_size, chunk_size)
                    sub_chunk = chunk_df.iloc[start_idx:end_idx].copy()
                    
                    try:
                        sub_inserted = self.process_analytics_chunk(sub_chunk, f"{chunk_num}_{start_idx}")
                        total_analytics_inserted += sub_inserted
                        # Clean up sub-chunk immediately
                        del sub_chunk
                        self.force_memory_cleanup()
                    except Exception as e:
                        logger.warning(f"⚠️ Sub-chunk analytics processing failed for chunk {chunk_num}_{start_idx}: {e}")
                        continue
                        
        except Exception as e:
            logger.warning(f"⚠️ Optimized analytics processing failed for chunk {chunk_num}: {e}")
        
        return total_analytics_inserted

    def process_film_performance_summary(self, chunk_df, chunk_num):
        """Process FilmPerformanceSummary from chunk with memory optimization"""
        try:
            film_summaries = []
            
            # Use more memory-efficient aggregation
            grouped = chunk_df.groupby('title')
            
            # Process each group and clean up immediately
            for title, movie_group in grouped:
                try:
                    # Calculate aggregated metrics more efficiently
                    total_reserved = movie_group['reserved'].sum()
                    total_seats = movie_group['total_seats'].sum()
                    
                    # Optimize price calculation
                    price_values = movie_group['price'].astype(str).str.replace('$', '').str.replace(',', '')
                    price_values = price_values.str.split(',').str[0]
                    price_values = pd.to_numeric(price_values, errors='coerce').fillna(0.0)
                    
                    total_sales = (price_values * movie_group['reserved']).sum()
                    avg_price = price_values.mean() if len(price_values) > 0 else 0.0
                    overall_occupancy = (total_reserved / total_seats * 100) if total_seats > 0 else 0.0
                    
                    first_movie = movie_group.iloc[0]
                    
                    film_summary_data = {
                        'title': self.safe_str(title, 255),
                        'genre': self.safe_str(first_movie.get('genre', ''), 100),
                        'rating': self.safe_str(first_movie.get('rating', ''), 20),
                        'studio_name': self.safe_str(first_movie.get('studio_name', ''), 255),
                        'release_date': self.parse_date(first_movie.get('release_date')),
                        'total_reserved': int(total_reserved),
                        'total_seats': int(total_seats),
                        'total_sales': self.safe_decimal(total_sales),
                        'avg_price': self.safe_decimal(avg_price),
                        'overall_occupancy': self.safe_float(overall_occupancy),
                        'theater_count': movie_group['theater_id'].nunique(),
                        'city_count': movie_group['theater_city'].nunique(),
                        'circuit_count': movie_group['circuit_name'].nunique(),
                        'format_count': movie_group['screen_format'].nunique(),
                        'year': int(str(first_movie.get('date_sh', ''))[:4]) if pd.notna(first_movie.get('date_sh')) else 2024,
                    }
                    
                    film_summaries.append(FilmPerformanceSummary(**film_summary_data))
                    
                    # Clean up group data immediately
                    del movie_group, price_values
                    
                except Exception as e:
                    logger.warning(f"⚠️ Skipping film summary for {title}: {e}")
                    continue
            
            # Clean up grouped data
            del grouped
            
            # Bulk insert FilmPerformanceSummary in smaller batches
            if film_summaries:
                with transaction.atomic():
                    batch_size = min(250, len(film_summaries))  # Smaller batch size
                    for i in range(0, len(film_summaries), batch_size):
                        batch = film_summaries[i:i + batch_size]
                        FilmPerformanceSummary.objects.bulk_create(batch, batch_size=batch_size, ignore_conflicts=True)
                        del batch
            
            # Return count and clean up summaries list
            count = len(film_summaries)
            del film_summaries
            return count
            
        except Exception as e:
            logger.error(f"❌ FilmPerformanceSummary processing failed: {e}")
            return 0

    def process_theater_performance(self, chunk_df, chunk_num):
        """Process TheaterPerformance from chunk with memory optimization"""
        try:
            theater_performances = []
            
            # Use more memory-efficient aggregation
            grouped = chunk_df.groupby('theater_id')
            
            # Process each group and clean up immediately
            for theater_id, theater_group in grouped:
                try:
                    # Calculate aggregated metrics
                    total_reserved = theater_group['reserved'].sum()
                    total_seats = theater_group['total_seats'].sum()
                    
                    # Optimize price calculation
                    price_values = theater_group['price'].astype(str).str.replace('$', '').str.replace(',', '')
                    price_values = price_values.str.split(',').str[0]
                    price_values = pd.to_numeric(price_values, errors='coerce').fillna(0.0)
                    
                    total_sales = (price_values * theater_group['reserved']).sum()
                    avg_price = price_values.mean() if len(price_values) > 0 else 0.0
                    capacity_utilization = (total_reserved / total_seats * 100) if total_seats > 0 else 0.0
                    
                    first_theater = theater_group.iloc[0]
                    
                    theater_performance_data = {
                        'theater_name': self.safe_str(first_theater.get('theater_name', ''), 255),
                        'theater_city': self.safe_str(first_theater.get('theater_city', ''), 100),
                        'theater_state': self.safe_str(first_theater.get('theater_state', ''), 50),
                        'circuit_name': self.safe_str(first_theater.get('circuit_name', ''), 255),
                        'dma': self.safe_str(first_theater.get('dma', ''), 100),
                        'total_capacity': int(total_seats),
                        'total_reserved': int(total_reserved),
                        'total_sales': self.safe_decimal(total_sales),
                        'avg_price': self.safe_decimal(avg_price),
                        'overall_occupancy': round(capacity_utilization, 2),
                        'movie_count': theater_group['title'].nunique(),
                        'capacity_utilization': round(capacity_utilization, 2),
                        'price_optimization': 0.0,  # Simplified for now
                        'market_position': 'Medium',  # Simplified for now
                        'amenities': self.safe_str(first_theater.get('amenities', ''), 1000),
                        'year': int(str(first_theater.get('date_sh', ''))[:4]) if pd.notna(first_theater.get('date_sh')) else 2024,
                    }
                    
                    theater_performances.append(TheaterPerformance(**theater_performance_data))
                    
                    # Clean up group data immediately
                    del theater_group, price_values
                    
                except Exception as e:
                    logger.warning(f"⚠️ Skipping theater performance for {theater_id}: {e}")
                    continue
            
            # Clean up grouped data
            del grouped
            
            # Bulk insert TheaterPerformance in smaller batches
            if theater_performances:
                with transaction.atomic():
                    batch_size = min(250, len(theater_performances))  # Smaller batch size
                    for i in range(0, len(theater_performances), batch_size):
                        batch = theater_performances[i:i + batch_size]
                        TheaterPerformance.objects.bulk_create(batch, batch_size=batch_size, ignore_conflicts=True)
                        del batch
            
            # Return count and clean up performances list
            count = len(theater_performances)
            del theater_performances
            return count
            
        except Exception as e:
            logger.error(f"❌ TheaterPerformance processing failed: {e}")
            return 0

    def process_market_analysis(self, chunk_df, chunk_num):
        """Process MarketAnalysis from chunk with memory optimization"""
        try:
            market_analyses = []
            
            # Use more memory-efficient aggregation
            grouped = chunk_df.groupby(['theater_city', 'theater_state'])
            
            # Process each group and clean up immediately
            for (city, state), market_group in grouped:
                try:
                    # Calculate market metrics
                    total_reserved = market_group['reserved'].sum()
                    total_seats = market_group['total_seats'].sum()
                    
                    # Optimize price calculation
                    price_values = market_group['price'].astype(str).str.replace('$', '').str.replace(',', '')
                    price_values = price_values.str.split(',').str[0]
                    price_values = pd.to_numeric(price_values, errors='coerce').fillna(0.0)
                    
                    total_sales = (price_values * market_group['reserved']).sum()
                    market_occupancy = (total_reserved / total_seats * 100) if total_seats > 0 else 0
                    
                    market_analysis_data = {
                        'city': self.safe_str(city, 100),
                        'state': self.safe_str(state, 50),
                        'dma': self.safe_str(market_group.iloc[0].get('dma', ''), 100),
                        'date': self.parse_date(market_group.iloc[0].get('date_sh')),
                        'total_market_capacity': int(total_seats),
                        'total_market_reserved': int(total_reserved),
                        'total_market_sales': self.safe_decimal(total_sales),
                        'market_occupancy': round(market_occupancy, 2),
                        'theater_count': market_group['theater_id'].nunique(),
                        'circuit_diversity': market_group['circuit_name'].nunique(),
                        'format_diversity': market_group['screen_format'].nunique(),
                        'price_range_min': self.safe_decimal(price_values.min()) if len(price_values) > 0 else Decimal('0.00'),
                        'price_range_max': self.safe_decimal(price_values.max()) if len(price_values) > 0 else Decimal('0.00'),
                        'capacity_utilization': round(market_occupancy, 2),
                        'year': int(str(market_group.iloc[0].get('date_sh', ''))[:4]) if pd.notna(market_group.iloc[0].get('date_sh')) else 2024,
                    }
                    
                    market_analyses.append(MarketAnalysis(**market_analysis_data))
                    
                    # Clean up group data immediately
                    del market_group, price_values
                    
                except Exception as e:
                    logger.warning(f"⚠️ Skipping market analysis for {city}, {state}: {e}")
                    continue
            
            # Clean up grouped data
            del grouped
            
            # Bulk insert MarketAnalysis in smaller batches
            if market_analyses:
                with transaction.atomic():
                    batch_size = min(250, len(market_analyses))  # Smaller batch size
                    for i in range(0, len(market_analyses), batch_size):
                        batch = market_analyses[i:i + batch_size]
                        MarketAnalysis.objects.bulk_create(batch, batch_size=batch_size, ignore_conflicts=True)
                        del batch
            
            # Return count and clean up analyses list
            count = len(market_analyses)
            del market_analyses
            return count
            
        except Exception as e:
            logger.error(f"❌ MarketAnalysis processing failed: {e}")
            return 0

    def process_comparative_analysis(self, chunk_df, chunk_num):
        """Process ComparativeAnalysis from chunk with memory optimization"""
        try:
            comparative_analyses = []
            
            # Use more memory-efficient aggregation
            grouped = chunk_df.groupby('title')
            
            # Process each group and clean up immediately
            for title, movie_group in grouped:
                try:
                    # Calculate aggregated metrics
                    total_reserved = movie_group['reserved'].sum()
                    total_seats = movie_group['total_seats'].sum()
                    
                    # Optimize price calculation
                    price_values = movie_group['price'].astype(str).str.replace('$', '').str.replace(',', '')
                    price_values = price_values.str.split(',').str[0]
                    price_values = pd.to_numeric(price_values, errors='coerce').fillna(0.0)
                    
                    total_sales = (price_values * movie_group['reserved']).sum()
                    avg_price = price_values.mean() if len(price_values) > 0 else 0.0
                    overall_occupancy = (total_reserved / total_seats * 100) if total_seats > 0 else 0.0
                    
                    first_movie = movie_group.iloc[0]
                    
                    # Create performance profile for complex analysis
                    performance_profile = {
                        'genre': first_movie.get('genre', ''),
                        'rating': first_movie.get('rating', ''),
                        'studio': first_movie.get('studio_name', ''),
                        'geographic_spread': movie_group['theater_city'].nunique(),
                        'circuit_diversity': movie_group['circuit_name'].nunique(),
                        'format_diversity': movie_group['screen_format'].nunique(),
                    }
                    
                    comparative_analysis_data = {
                        'title': self.safe_str(title, 255),
                        'genre': self.safe_str(first_movie.get('genre', ''), 100),
                        'rating': self.safe_str(first_movie.get('rating', ''), 20),
                        'studio_name': self.safe_str(first_movie.get('studio_name', ''), 255),
                        'release_date': self.parse_date(first_movie.get('release_date')),
                        'total_reserved': int(total_reserved),
                        'total_seats': int(total_seats),
                        'total_sales': self.safe_decimal(total_sales),
                        'avg_price': self.safe_decimal(avg_price),
                        'overall_occupancy': self.safe_float(overall_occupancy),
                        'dod_growth': None,  # Simplified for now
                        'market_penetration': movie_group['theater_id'].nunique() / movie_group['theater_city'].nunique() if movie_group['theater_city'].nunique() > 0 else 0,
                        'geographic_spread': movie_group['theater_city'].nunique(),
                        'circuit_diversity': movie_group['circuit_name'].nunique(),
                        'format_diversity': movie_group['screen_format'].nunique(),
                        'peak_time': '',  # Simplified for now
                        'best_format': '',  # Simplified for now
                        'top_market': '',  # Simplified for now
                        'weekend_ratio': None,  # Simplified for now
                        'performance_profile': performance_profile,
                        'year': int(str(first_movie.get('date_sh', ''))[:4]) if pd.notna(first_movie.get('date_sh')) else 2024,
                    }
                    
                    comparative_analyses.append(ComparativeAnalysis(**comparative_analysis_data))
                    
                    # Clean up group data immediately
                    del movie_group, price_values
                    
                except Exception as e:
                    logger.warning(f"⚠️ Skipping comparative analysis for {title}: {e}")
                    continue
            
            # Clean up grouped data
            del grouped
            
            # Bulk insert ComparativeAnalysis in smaller batches
            if comparative_analyses:
                with transaction.atomic():
                    batch_size = min(250, len(comparative_analyses))  # Smaller batch size
                    for i in range(0, len(comparative_analyses), batch_size):
                        batch = comparative_analyses[i:i + batch_size]
                        ComparativeAnalysis.objects.bulk_create(batch, batch_size=batch_size, ignore_conflicts=True)
                        del batch
            
            # Return count and clean up analyses list
            count = len(comparative_analyses)
            del comparative_analyses
            return count
            
        except Exception as e:
            logger.error(f"❌ ComparativeAnalysis processing failed: {e}")
            return 0
