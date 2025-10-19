#!/usr/bin/env python3
"""
Django management command to insert CSV data into Movies table
Processes 7.4M records in 50k chunks with progress tracking
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from movies.models import Movie
import pandas as pd
import os
import time
import json
from datetime import datetime, date, time as dt_time
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Insert CSV data into Movies table in 50k chunks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-path',
            type=str,
            default='/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv',
            help='Path to the CSV file (default: Entelligence_7.4M_dataset.csv)',
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

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting CSV to Movies Table Import')
        )
        self.stdout.write(
            self.style.SUCCESS(f'📊 Processing {options["chunk_size"]:,} records per chunk')
        )
        
        try:
            # Initialize import process
            csv_path = options['csv_path']
            chunk_size = options['chunk_size']
            checkpoint_interval = options['checkpoint_interval']
            
            # Check if CSV file exists
            if not os.path.exists(csv_path):
                self.stdout.write(
                    self.style.ERROR(f'❌ CSV file not found: {csv_path}')
                )
                return
            
            # Reset database if requested
            if options['reset']:
                self.stdout.write('🗑️ Clearing existing Movie records...')
                Movie.objects.all().delete()
                self.stdout.write('✅ Database cleared')
            
            # Get total row count
            total_rows = self.get_total_rows(csv_path)
            self.stdout.write(f'📈 Total rows in CSV: {total_rows:,}')
            
            # Check for existing checkpoint
            checkpoint_data = self.load_checkpoint()
            start_chunk = checkpoint_data.get('chunk_number', 0) + 1
            total_processed = checkpoint_data.get('total_processed', 0)
            
            if start_chunk > 1:
                self.stdout.write(
                    self.style.WARNING(f'🔄 Resuming from chunk {start_chunk}')
                )
                self.stdout.write(f'📊 Already processed: {total_processed:,} records')
            
            # Process CSV in chunks
            self.process_csv_chunks(
                csv_path, chunk_size, checkpoint_interval, 
                start_chunk, total_processed, total_rows
            )
            
            self.stdout.write(
                self.style.SUCCESS('✅ CSV import completed successfully!')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Import failed: {e}')
            )
            logger.exception("CSV import failed")
            raise

    def get_total_rows(self, csv_path):
        """Get total number of rows in CSV file"""
        with open(csv_path, 'r') as f:
            return sum(1 for line in f) - 1  # Subtract header

    def load_checkpoint(self):
        """Load existing checkpoint if available"""
        checkpoint_path = 'checkpoints/csv_import_checkpoint.json'
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
        checkpoint_path = 'checkpoints/csv_import_checkpoint.json'
        
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        self.stdout.write(f'💾 Checkpoint saved: {total_processed:,} records processed')

    def parse_price(self, price_str):
        """Parse price string and return Decimal"""
        try:
            if pd.isna(price_str) or price_str == '':
                return Decimal('0.00')
            
            # Remove dollar signs and clean
            price_clean = str(price_str).replace('$', '').replace(',', '').strip()
            
            # Handle multiple prices (take first)
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
            
            # Handle different date formats
            date_str = str(date_str).strip()
            
            # Try different date formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            
            # If all formats fail, return today
            return date.today()
            
        except Exception:
            return date.today()

    def parse_time(self, time_str):
        """Parse time string and return time object"""
        try:
            if pd.isna(time_str) or time_str == '':
                return dt_time(0, 0, 0)
            
            time_str = str(time_str).strip()
            
            # Try different time formats
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
            
            # Try different datetime formats
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

    def safe_str(self, value, max_length=255):
        """Safely convert value to string with length limit"""
        try:
            if pd.isna(value):
                return ''
            str_value = str(value).strip()
            return str_value[:max_length] if len(str_value) > max_length else str_value
        except Exception:
            return ''

    def process_csv_chunks(self, csv_path, chunk_size, checkpoint_interval, 
                          start_chunk, total_processed, total_rows):
        """Process CSV file in chunks"""
        
        chunk_iterator = pd.read_csv(csv_path, chunksize=chunk_size, low_memory=False)
        total_inserted = 0
        
        for chunk_num, chunk_df in enumerate(chunk_iterator, start=1):
            if chunk_num < start_chunk:
                continue
            
            chunk_start_time = time.time()
            
            try:
                # Process chunk
                inserted_count = self.process_chunk(chunk_df, chunk_num)
                total_processed += len(chunk_df)
                total_inserted += inserted_count
                
                # Clear memory
                del chunk_df
                
                # Save checkpoint periodically
                if chunk_num % checkpoint_interval == 0:
                    self.save_checkpoint(chunk_num, total_processed, total_inserted)
                
                # Show progress
                chunk_time = time.time() - chunk_start_time
                progress = (total_processed / total_rows) * 100
                
                self.stdout.write(
                    f'✅ Chunk {chunk_num}: {inserted_count:,} records inserted in {chunk_time:.1f}s'
                )
                self.stdout.write(
                    f'📊 Progress: {total_processed:,}/{total_rows:,} ({progress:.1f}%)'
                )
                self.stdout.write(
                    f'📈 Total inserted: {total_inserted:,} records'
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Chunk {chunk_num} failed: {e}')
                )
                raise
        
        # Final checkpoint
        self.save_final_checkpoint(total_processed, total_inserted)

    def process_chunk(self, chunk_df, chunk_num):
        """Process a single chunk and insert into database"""
        movies_to_create = []
        
        for idx, row in chunk_df.iterrows():
            try:
                # Parse and validate data
                movie_data = {
                    'theater_id': self.safe_str(row.get('theater_id', ''), 100),
                    'mm_id': self.safe_str(row.get('mm_id', ''), 100),
                    'circuit_name': self.safe_str(row.get('circuit_name', ''), 255),
                    'theater_name': self.safe_str(row.get('theater_name', ''), 255),
                    'theater_address': self.safe_str(row.get('theater_address', ''), 255),
                    'theater_city': self.safe_str(row.get('theater_city', ''), 100),
                    'theater_state': self.safe_str(row.get('theater_state', ''), 50),
                    'theater_zip': self.safe_str(row.get('theater_zip', ''), 20),
                    'country': self.safe_str(row.get('country', ''), 50),
                    'dma': self.safe_str(row.get('dma', ''), 100),
                    'title': self.safe_str(row.get('title', ''), 255),
                    'studio_name': self.safe_str(row.get('studio_name', ''), 255),
                    'release_date': self.parse_date(row.get('release_date')),
                    'runtime': self.safe_int(row.get('runtime')),
                    'genre': self.safe_str(row.get('genre', ''), 100),
                    'rating': self.safe_str(row.get('rating', ''), 20),
                    'date_sh': self.parse_date(row.get('date_sh')),
                    'time_sh': self.parse_time(row.get('time_sh')),
                    'auditorium': self.safe_str(row.get('auditorium', ''), 50),
                    'screen_format': self.safe_str(row.get('screen_format', ''), 50),
                    'movie_format': self.safe_str(row.get('movie_format', ''), 50),
                    'language_format': self.safe_str(row.get('language_format', ''), 50),
                    'price': self.parse_price(row.get('price')),
                    'child': self.parse_price(row.get('child')),
                    'senior': self.parse_price(row.get('senior')),
                    'total_seats': self.safe_int(row.get('total_seats')),
                    'available': self.safe_int(row.get('available')),
                    'reserved': self.safe_int(row.get('reserved')),
                    'checkered': self.safe_int(row.get('checkered')),
                    'actual_total_seats': self.safe_int(row.get('actual_total_seats')),
                    'actual_available': self.safe_int(row.get('actual_available')),
                    'actual_reserved': self.safe_int(row.get('actual_reserved')),
                    'actual_checkered': self.safe_int(row.get('actual_checkered')),
                    'before_reserved': self.safe_int(row.get('before_reserved')),
                    'on_reserved': self.safe_int(row.get('on_reserved')),
                    'after_reserved': self.safe_int(row.get('after_reserved')),
                    'seating_type': self.safe_str(row.get('seating_type', ''), 50),
                    'amenities': self.safe_str(row.get('amenities', ''), 1000),
                    'ticket_availability': bool(row.get('ticket_availability', True)),
                    'is_ticketing': bool(row.get('is_ticketing', True)),
                    'source_flag': self.safe_str(row.get('source_flag', ''), 50),
                    'last_updates': self.parse_datetime(row.get('last_updates')),
                    'running_date': self.parse_date(row.get('running_date')),
                    'dsr_date_sh': self.parse_datetime(row.get('dsr_date_sh')),
                    'dsr_last_updates': self.parse_datetime(row.get('dsr_last_updates')),
                }
                
                movies_to_create.append(Movie(**movie_data))
                
            except Exception as e:
                logger.warning(f"⚠️ Skipping row {idx} in chunk {chunk_num}: {e}")
                continue
        
        # Bulk insert
        if movies_to_create:
            with transaction.atomic():
                Movie.objects.bulk_create(movies_to_create, batch_size=1000)
        
        return len(movies_to_create)

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
        checkpoint_path = 'checkpoints/csv_import_final.json'
        
        with open(checkpoint_path, 'w') as f:
            json.dump(final_checkpoint, f, indent=2)
        
        self.stdout.write(f'💾 Final checkpoint saved: {total_inserted:,} records inserted')
