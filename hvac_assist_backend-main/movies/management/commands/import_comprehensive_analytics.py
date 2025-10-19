#!/usr/bin/env python3
"""
COMPREHENSIVE MULTI-TABLE ANALYTICS IMPORT
Imports CSV data into Movies + Analytics tables for complex query answering
Optimized for comparative analysis, performance predictions, and market opportunities
"""

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from movies.models import Movie, FilmPerformanceSummary, TheaterPerformance, MarketAnalysis, ComparativeAnalysis
import pandas as pd
import os
import time
import json
from datetime import datetime, date, time as dt_time
import logging
from decimal import Decimal, InvalidOperation
from tqdm import tqdm
import psycopg2
from psycopg2.extras import execute_values
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Comprehensive multi-table import for analytics and comparative analysis'

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
            help='Clear existing records before inserting',
        )
        parser.add_argument(
            '--checkpoint-interval',
            type=int,
            default=2,
            help='Save checkpoint every N chunks (default: 2)',
        )
        parser.add_argument(
            '--tables',
            nargs='+',
            choices=['movies', 'film_summary', 'theater_performance', 'market_analysis', 'comparative_analysis', 'all'],
            default=['all'],
            help='Which tables to populate (default: all)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting COMPREHENSIVE ANALYTICS IMPORT')
        )
        self.stdout.write(
            self.style.SUCCESS('📊 Multi-table import for complex query answering')
        )
        self.stdout.write(
            self.style.SUCCESS(f'📋 Tables: {", ".join(options["tables"])}')
        )
        
        try:
            # Initialize import process
            self.start_time = time.time()
            csv_path = options['csv_path']
            chunk_size = options['chunk_size']
            checkpoint_interval = options['checkpoint_interval']
            tables = options['tables']
            
            # Check if CSV file exists
            if not os.path.exists(csv_path):
                self.stdout.write(
                    self.style.ERROR(f'❌ CSV file not found: {csv_path}')
                )
                return
            
            # Reset database if requested
            if options['reset']:
                self.reset_tables(tables)
            
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
            self.process_csv_comprehensive(
                csv_path, chunk_size, checkpoint_interval, 
                start_chunk, total_processed, total_rows, tables
            )
            
            self.stdout.write(
                self.style.SUCCESS('✅ Comprehensive analytics import completed!')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Import failed: {e}')
            )
            logger.exception("Comprehensive import failed")
            raise

    def reset_tables(self, tables):
        """Reset specified tables"""
        self.stdout.write('🗑️ Clearing existing records...')
        
        if 'all' in tables or 'movies' in tables:
            Movie.objects.all().delete()
            self.stdout.write('✅ Movies table cleared')
        
        if 'all' in tables or 'film_summary' in tables:
            FilmPerformanceSummary.objects.all().delete()
            self.stdout.write('✅ FilmPerformanceSummary table cleared')
        
        if 'all' in tables or 'theater_performance' in tables:
            TheaterPerformance.objects.all().delete()
            self.stdout.write('✅ TheaterPerformance table cleared')
        
        if 'all' in tables or 'market_analysis' in tables:
            MarketAnalysis.objects.all().delete()
            self.stdout.write('✅ MarketAnalysis table cleared')
        
        if 'all' in tables or 'comparative_analysis' in tables:
            ComparativeAnalysis.objects.all().delete()
            self.stdout.write('✅ ComparativeAnalysis table cleared')
        
        self.stdout.write('✅ Database cleared')

    def get_total_rows(self, csv_path):
        """Get total number of rows in CSV file"""
        with open(csv_path, 'r') as f:
            return sum(1 for line in f) - 1  # Subtract header

    def load_checkpoint(self):
        """Load existing checkpoint if available"""
        checkpoint_path = 'checkpoints/comprehensive_analytics_checkpoint.json'
        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                return json.load(f)
        return {'chunk_number': 0, 'total_processed': 0}

    def save_checkpoint(self, chunk_number, total_processed, table_stats):
        """Save progress checkpoint"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'chunk_number': chunk_number,
            'total_processed': total_processed,
            'table_stats': table_stats,
            'status': 'in_progress'
        }
        
        os.makedirs('checkpoints', exist_ok=True)
        checkpoint_path = 'checkpoints/comprehensive_analytics_checkpoint.json'
        
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

    def safe_str(self, value, max_length=255):
        """Safely convert value to string with length limit"""
        try:
            if pd.isna(value):
                return ''
            str_value = str(value).strip()
            return str_value[:max_length] if len(str_value) > max_length else str_value
        except Exception:
            return ''

    def process_csv_comprehensive(self, csv_path, chunk_size, checkpoint_interval, 
                                start_chunk, total_processed, total_rows, tables):
        """Process CSV file comprehensively for all tables"""
        
        chunk_iterator = pd.read_csv(csv_path, chunksize=chunk_size, low_memory=False)
        table_stats = {
            'movies': 0,
            'film_summary': 0,
            'theater_performance': 0,
            'market_analysis': 0,
            'comparative_analysis': 0
        }
        
        # Create progress bar
        total_chunks = (total_rows + chunk_size - 1) // chunk_size
        pbar = tqdm(total=total_chunks, desc="Processing chunks", unit="chunk")
        
        for chunk_num, chunk_df in enumerate(chunk_iterator, start=1):
            if chunk_num < start_chunk:
                pbar.update(1)
                continue
            
            chunk_start_time = time.time()
            
            try:
                # Store chunk size before processing
                chunk_size_actual = len(chunk_df)
                
                # Process chunk for all tables
                chunk_stats = self.process_chunk_comprehensive(chunk_df, chunk_num, tables)
                
                # Update total stats
                for table, count in chunk_stats.items():
                    table_stats[table] += count
                
                total_processed += chunk_size_actual
                
                # Clear memory
                del chunk_df
                
                # Save checkpoint periodically
                if chunk_num % checkpoint_interval == 0:
                    self.save_checkpoint(chunk_num, total_processed, table_stats)
                
                # Show progress
                chunk_time = time.time() - chunk_start_time
                progress = (total_processed / total_rows) * 100
                
                # Update progress bar
                pbar.set_postfix({
                    'Processed': f'{total_processed:,}',
                    'Progress': f'{progress:.1f}%',
                    'Speed': f'{chunk_size_actual/chunk_time:.0f} rec/s'
                })
                pbar.update(1)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Chunk {chunk_num} failed: {e}')
                )
                pbar.close()
                raise
        
        pbar.close()
        
        # Final checkpoint
        self.save_final_checkpoint(total_processed, table_stats)

    def process_chunk_comprehensive(self, chunk_df, chunk_num, tables):
        """Process a single chunk for all tables"""
        chunk_stats = {
            'movies': 0,
            'film_summary': 0,
            'theater_performance': 0,
            'market_analysis': 0,
            'comparative_analysis': 0
        }
        
        # Process Movies table
        if 'all' in tables or 'movies' in tables:
            movies_count = self.process_movies_chunk(chunk_df, chunk_num)
            chunk_stats['movies'] = movies_count
        
        # Process Analytics tables
        if 'all' in tables or 'film_summary' in tables:
            film_summary_count = self.process_film_summary_chunk(chunk_df, chunk_num)
            chunk_stats['film_summary'] = film_summary_count
        
        if 'all' in tables or 'theater_performance' in tables:
            theater_performance_count = self.process_theater_performance_chunk(chunk_df, chunk_num)
            chunk_stats['theater_performance'] = theater_performance_count
        
        if 'all' in tables or 'market_analysis' in tables:
            market_analysis_count = self.process_market_analysis_chunk(chunk_df, chunk_num)
            chunk_stats['market_analysis'] = market_analysis_count
        
        if 'all' in tables or 'comparative_analysis' in tables:
            comparative_analysis_count = self.process_comparative_analysis_chunk(chunk_df, chunk_num)
            chunk_stats['comparative_analysis'] = comparative_analysis_count
        
        return chunk_stats

    def process_movies_chunk(self, chunk_df, chunk_num):
        """Process Movies table chunk with bulk operations"""
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
                logger.warning(f"⚠️ Skipping row {idx} in movies chunk {chunk_num}: {e}")
                continue
        
        # Bulk insert Movies using raw SQL
        if movies_data:
            inserted_count = self.bulk_insert_movies(movies_data, 1000)
            return inserted_count
        
        return 0

    def bulk_insert_movies(self, movies_data, bulk_size):
        """Perform bulk insert using raw SQL for maximum performance"""
        try:
            with connection.cursor() as cursor:
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
                
                total_inserted = 0
                for i in range(0, len(movies_data), bulk_size):
                    batch = movies_data[i:i + bulk_size]
                    execute_values(
                        cursor, insert_sql, batch, 
                        template=None, page_size=bulk_size
                    )
                    total_inserted += len(batch)
                
                return total_inserted
                
        except Exception as e:
            logger.error(f"❌ Bulk insert failed: {e}")
            return 0

    def process_film_summary_chunk(self, chunk_df, chunk_num):
        """Process FilmPerformanceSummary chunk for comparative analysis"""
        film_summaries = []
        
        # Group by title for aggregation
        for title, movie_group in chunk_df.groupby('title'):
            try:
                # Calculate aggregated metrics
                total_reserved = movie_group['reserved'].sum()
                total_seats = movie_group['total_seats'].sum()
                
                # Calculate total sales
                prices_clean = []
                for price in movie_group['price']:
                    try:
                        price_str = str(price).replace('$', '').replace(',', '').strip()
                        if ',' in price_str:
                            price_str = price_str.split(',')[0]
                        prices_clean.append(float(price_str) if price_str else 0.0)
                    except (ValueError, TypeError):
                        prices_clean.append(0.0)
                
                total_sales = sum(price * reserved for price, reserved in zip(prices_clean, movie_group['reserved']))
                avg_price = np.mean(prices_clean) if prices_clean else 0.0
                overall_occupancy = (total_reserved / total_seats * 100) if total_seats > 0 else 0.0
                
                first_movie = movie_group.iloc[0]
                
                # Calculate performance patterns for comparative analysis
                dod_growth = self.calculate_dod_growth(movie_group)
                weekend_ratio = self.calculate_weekend_ratio(movie_group)
                peak_time = self.find_peak_time(movie_group)
                best_format = self.find_best_format(movie_group)
                top_market = self.find_top_market(movie_group)
                
                film_summary_data = {
                    'title': self.safe_str(title, 255),
                    'genre': self.safe_str(first_movie.get('genre', ''), 100),
                    'rating': self.safe_str(first_movie.get('rating', ''), 20),
                    'studio_name': self.safe_str(first_movie.get('studio_name', ''), 255),
                    'release_date': self.parse_date(first_movie.get('release_date')),
                    'total_reserved': int(total_reserved),
                    'total_seats': int(total_seats),
                    'total_sales': Decimal(str(round(total_sales, 2))),
                    'avg_price': Decimal(str(round(avg_price, 2))),
                    'overall_occupancy': round(overall_occupancy, 2),
                    'theater_count': movie_group['theater_id'].nunique(),
                    'city_count': movie_group['theater_city'].nunique(),
                    'circuit_count': movie_group['circuit_name'].nunique(),
                    'format_count': movie_group['screen_format'].nunique(),
                    'dod_growth': round(dod_growth, 2) if dod_growth else None,
                    'weekend_ratio': round(weekend_ratio, 2) if weekend_ratio else None,
                    'peak_time': peak_time,
                    'best_format': best_format,
                    'top_market': top_market,
                    'year': int(str(first_movie.get('date_sh', ''))[:4]) if pd.notna(first_movie.get('date_sh')) else 2024,
                }
                
                film_summaries.append(FilmPerformanceSummary(**film_summary_data))
                
            except Exception as e:
                logger.warning(f"⚠️ Skipping film summary for {title}: {e}")
                continue
        
        # Bulk insert FilmPerformanceSummary
        if film_summaries:
            with transaction.atomic():
                FilmPerformanceSummary.objects.bulk_create(film_summaries, batch_size=500)
        
        return len(film_summaries)

    def process_theater_performance_chunk(self, chunk_df, chunk_num):
        """Process TheaterPerformance chunk for opportunity analysis"""
        theater_performances = []
        
        # Group by theater_id for aggregation
        for theater_id, theater_group in chunk_df.groupby('theater_id'):
            try:
                # Calculate aggregated metrics
                total_reserved = theater_group['reserved'].sum()
                total_seats = theater_group['total_seats'].sum()
                total_sales = sum(
                    float(str(price).replace('$', '').replace(',', '').split(',')[0] or 0) * reserved 
                    for price, reserved in zip(theater_group['price'], theater_group['reserved'])
                )
                
                first_theater = theater_group.iloc[0]
                
                # Calculate opportunity metrics
                capacity_utilization = (total_reserved / total_seats * 100) if total_seats > 0 else 0.0
                price_optimization = self.calculate_price_optimization(theater_group)
                market_position = self.determine_market_position(capacity_utilization)
                
                theater_performance_data = {
                    'theater_name': self.safe_str(first_theater.get('theater_name', ''), 255),
                    'theater_city': self.safe_str(first_theater.get('theater_city', ''), 100),
                    'theater_state': self.safe_str(first_theater.get('theater_state', ''), 50),
                    'circuit_name': self.safe_str(first_theater.get('circuit_name', ''), 255),
                    'dma': self.safe_str(first_theater.get('dma', ''), 100),
                    'total_capacity': int(total_seats),
                    'total_reserved': int(total_reserved),
                    'total_sales': Decimal(str(round(total_sales, 2))),
                    'avg_price': Decimal(str(round(np.mean([float(str(p).replace('$', '').replace(',', '').split(',')[0] or 0) for p in theater_group['price']]), 2))),
                    'overall_occupancy': round(capacity_utilization, 2),
                    'movie_count': theater_group['title'].nunique(),
                    'capacity_utilization': round(capacity_utilization, 2),
                    'price_optimization': round(price_optimization, 2),
                    'market_position': market_position,
                    'amenities': self.safe_str(first_theater.get('amenities', ''), 1000),
                    'year': int(str(first_theater.get('date_sh', ''))[:4]) if pd.notna(first_theater.get('date_sh')) else 2024,
                }
                
                theater_performances.append(TheaterPerformance(**theater_performance_data))
                
            except Exception as e:
                logger.warning(f"⚠️ Skipping theater performance for {theater_id}: {e}")
                continue
        
        # Bulk insert TheaterPerformance
        if theater_performances:
            with transaction.atomic():
                TheaterPerformance.objects.bulk_create(theater_performances, batch_size=500)
        
        return len(theater_performances)

    def process_market_analysis_chunk(self, chunk_df, chunk_num):
        """Process MarketAnalysis chunk for market insights"""
        market_analyses = []
        
        # Group by city and state for market analysis
        for (city, state), market_group in chunk_df.groupby(['theater_city', 'theater_state']):
            try:
                # Calculate market metrics
                total_reserved = market_group['reserved'].sum()
                total_seats = market_group['total_seats'].sum()
                total_sales = sum(
                    float(str(price).replace('$', '').replace(',', '').split(',')[0] or 0) * reserved 
                    for price, reserved in zip(market_group['price'], market_group['reserved'])
                )
                
                # Calculate market diversity
                price_values = [float(str(p).replace('$', '').replace(',', '').split(',')[0] or 0) for p in market_group['price']]
                
                market_analysis_data = {
                    'city': self.safe_str(city, 100),
                    'state': self.safe_str(state, 50),
                    'dma': self.safe_str(market_group.iloc[0].get('dma', ''), 100),
                    'date': self.parse_date(market_group.iloc[0].get('date_sh')),
                    'total_market_capacity': int(total_seats),
                    'total_market_reserved': int(total_reserved),
                    'total_market_sales': Decimal(str(round(total_sales, 2))),
                    'market_occupancy': round((total_reserved / total_seats * 100) if total_seats > 0 else 0, 2),
                    'theater_count': market_group['theater_id'].nunique(),
                    'circuit_diversity': market_group['circuit_name'].nunique(),
                    'format_diversity': market_group['screen_format'].nunique(),
                    'price_range_min': Decimal(str(round(min(price_values), 2))) if price_values else Decimal('0.00'),
                    'price_range_max': Decimal(str(round(max(price_values), 2))) if price_values else Decimal('0.00'),
                    'capacity_utilization': round((total_reserved / total_seats * 100) if total_seats > 0 else 0, 2),
                    'year': int(str(market_group.iloc[0].get('date_sh', ''))[:4]) if pd.notna(market_group.iloc[0].get('date_sh')) else 2024,
                }
                
                market_analyses.append(MarketAnalysis(**market_analysis_data))
                
            except Exception as e:
                logger.warning(f"⚠️ Skipping market analysis for {city}, {state}: {e}")
                continue
        
        # Bulk insert MarketAnalysis
        if market_analyses:
            with transaction.atomic():
                MarketAnalysis.objects.bulk_create(market_analyses, batch_size=500)
        
        return len(market_analyses)

    def process_comparative_analysis_chunk(self, chunk_df, chunk_num):
        """Process ComparativeAnalysis chunk for comp title analysis"""
        comparative_analyses = []
        
        # Group by title for comparative analysis
        for title, movie_group in chunk_df.groupby('title'):
            try:
                # Calculate aggregated metrics
                total_reserved = movie_group['reserved'].sum()
                total_seats = movie_group['total_seats'].sum()
                
                # Calculate total sales
                prices_clean = []
                for price in movie_group['price']:
                    try:
                        price_str = str(price).replace('$', '').replace(',', '').strip()
                        if ',' in price_str:
                            price_str = price_str.split(',')[0]
                        prices_clean.append(float(price_str) if price_str else 0.0)
                    except (ValueError, TypeError):
                        prices_clean.append(0.0)
                
                total_sales = sum(price * reserved for price, reserved in zip(prices_clean, movie_group['reserved']))
                avg_price = np.mean(prices_clean) if prices_clean else 0.0
                overall_occupancy = (total_reserved / total_seats * 100) if total_seats > 0 else 0.0
                
                first_movie = movie_group.iloc[0]
                
                # Calculate comparative metrics
                dod_growth = self.calculate_dod_growth(movie_group)
                market_penetration = self.calculate_market_penetration(movie_group)
                geographic_spread = movie_group['theater_city'].nunique()
                circuit_diversity = movie_group['circuit_name'].nunique()
                format_diversity = movie_group['screen_format'].nunique()
                
                # Create performance profile for complex analysis
                performance_profile = {
                    'genre': first_movie.get('genre', ''),
                    'rating': first_movie.get('rating', ''),
                    'studio': first_movie.get('studio_name', ''),
                    'dod_growth': dod_growth,
                    'weekend_ratio': self.calculate_weekend_ratio(movie_group),
                    'peak_time': self.find_peak_time(movie_group),
                    'best_format': self.find_best_format(movie_group),
                    'top_market': self.find_top_market(movie_group),
                    'price_sensitivity': self.calculate_price_sensitivity(movie_group),
                    'format_performance': self.calculate_format_performance(movie_group),
                    'geographic_performance': self.calculate_geographic_performance(movie_group)
                }
                
                comparative_analysis_data = {
                    'title': self.safe_str(title, 255),
                    'genre': self.safe_str(first_movie.get('genre', ''), 100),
                    'rating': self.safe_str(first_movie.get('rating', ''), 20),
                    'studio_name': self.safe_str(first_movie.get('studio_name', ''), 255),
                    'release_date': self.parse_date(first_movie.get('release_date')),
                    'total_reserved': int(total_reserved),
                    'total_seats': int(total_seats),
                    'total_sales': Decimal(str(round(total_sales, 2))),
                    'avg_price': Decimal(str(round(avg_price, 2))),
                    'overall_occupancy': round(overall_occupancy, 2),
                    'dod_growth': round(dod_growth, 2) if dod_growth else None,
                    'market_penetration': round(market_penetration, 2),
                    'geographic_spread': geographic_spread,
                    'circuit_diversity': circuit_diversity,
                    'format_diversity': format_diversity,
                    'peak_time': self.find_peak_time(movie_group),
                    'best_format': self.find_best_format(movie_group),
                    'top_market': self.find_top_market(movie_group),
                    'weekend_ratio': round(self.calculate_weekend_ratio(movie_group), 2) if self.calculate_weekend_ratio(movie_group) else None,
                    'performance_profile': performance_profile,
                    'year': int(str(first_movie.get('date_sh', ''))[:4]) if pd.notna(first_movie.get('date_sh')) else 2024,
                }
                
                comparative_analyses.append(ComparativeAnalysis(**comparative_analysis_data))
                
            except Exception as e:
                logger.warning(f"⚠️ Skipping comparative analysis for {title}: {e}")
                continue
        
        # Bulk insert ComparativeAnalysis
        if comparative_analyses:
            with transaction.atomic():
                ComparativeAnalysis.objects.bulk_create(comparative_analyses, batch_size=500)
        
        return len(comparative_analyses)

    # Helper methods for analytics calculations
    def calculate_dod_growth(self, movie_group):
        """Calculate day-over-day growth"""
        try:
            # Group by date and calculate daily totals
            daily_totals = movie_group.groupby('date_sh')['reserved'].sum().sort_index()
            if len(daily_totals) > 1:
                growth_rates = daily_totals.pct_change().dropna()
                return growth_rates.mean() * 100
            return None
        except:
            return None

    def calculate_weekend_ratio(self, movie_group):
        """Calculate weekend vs weekday performance ratio"""
        try:
            movie_group['day_of_week'] = pd.to_datetime(movie_group['date_sh']).dt.dayofweek
            weekend_mask = movie_group['day_of_week'].isin([5, 6])  # Saturday, Sunday
            weekend_total = movie_group[weekend_mask]['reserved'].sum()
            weekday_total = movie_group[~weekend_mask]['reserved'].sum()
            return weekend_total / weekday_total if weekday_total > 0 else None
        except:
            return None

    def find_peak_time(self, movie_group):
        """Find peak showtime"""
        try:
            time_performance = movie_group.groupby('time_sh')['reserved'].sum()
            return str(time_performance.idxmax()) if not time_performance.empty else ''
        except:
            return ''

    def find_best_format(self, movie_group):
        """Find best performing format"""
        try:
            format_performance = movie_group.groupby('screen_format')['reserved'].sum()
            return format_performance.idxmax() if not format_performance.empty else ''
        except:
            return ''

    def find_top_market(self, movie_group):
        """Find top performing market"""
        try:
            market_performance = movie_group.groupby(['theater_city', 'theater_state'])['reserved'].sum()
            top_market = market_performance.idxmax()
            return f"{top_market[0]}, {top_market[1]}" if top_market else ''
        except:
            return ''

    def calculate_price_optimization(self, theater_group):
        """Calculate price optimization potential"""
        try:
            avg_price = np.mean([float(str(p).replace('$', '').replace(',', '').split(',')[0] or 0) for p in theater_group['price']])
            occupancy_rate = theater_group['reserved'].sum() / theater_group['total_seats'].sum() * 100
            # Simple optimization score based on price vs occupancy
            return (occupancy_rate / avg_price) * 100 if avg_price > 0 else 0
        except:
            return 0

    def determine_market_position(self, capacity_utilization):
        """Determine market position based on capacity utilization"""
        if capacity_utilization >= 80:
            return 'High'
        elif capacity_utilization >= 60:
            return 'Medium'
        else:
            return 'Low'

    def calculate_market_penetration(self, movie_group):
        """Calculate market penetration"""
        try:
            total_theaters = movie_group['theater_id'].nunique()
            total_cities = movie_group['theater_city'].nunique()
            return (total_theaters / total_cities) if total_cities > 0 else 0
        except:
            return 0

    def calculate_price_sensitivity(self, movie_group):
        """Calculate price sensitivity"""
        try:
            price_reserved = movie_group[['price', 'reserved']].copy()
            price_reserved['price_clean'] = price_reserved['price'].apply(
                lambda x: float(str(x).replace('$', '').replace(',', '').split(',')[0] or 0)
            )
            correlation = price_reserved['price_clean'].corr(price_reserved['reserved'])
            return correlation if not pd.isna(correlation) else 0
        except:
            return 0

    def calculate_format_performance(self, movie_group):
        """Calculate format performance metrics"""
        try:
            format_performance = movie_group.groupby('screen_format').agg({
                'reserved': 'sum',
                'total_seats': 'sum',
                'price': 'mean'
            })
            format_performance['occupancy'] = format_performance['reserved'] / format_performance['total_seats'] * 100
            return format_performance.to_dict()
        except:
            return {}

    def calculate_geographic_performance(self, movie_group):
        """Calculate geographic performance metrics"""
        try:
            geo_performance = movie_group.groupby(['theater_city', 'theater_state']).agg({
                'reserved': 'sum',
                'total_seats': 'sum'
            })
            geo_performance['occupancy'] = geo_performance['reserved'] / geo_performance['total_seats'] * 100
            return geo_performance.to_dict()
        except:
            return {}

    def save_final_checkpoint(self, total_processed, table_stats):
        """Save final checkpoint"""
        final_checkpoint = {
            'timestamp': datetime.now().isoformat(),
            'total_processed': total_processed,
            'table_stats': table_stats,
            'status': 'completed',
            'completion_time': datetime.now().isoformat()
        }
        
        os.makedirs('checkpoints', exist_ok=True)
        checkpoint_path = 'checkpoints/comprehensive_analytics_final.json'
        
        with open(checkpoint_path, 'w') as f:
            json.dump(final_checkpoint, f, indent=2)
        
        self.stdout.write(f'💾 Final checkpoint saved')
        self.stdout.write(f'📊 Final Statistics:')
        for table, count in table_stats.items():
            self.stdout.write(f'   • {table}: {count:,} records')
        
        total_time = time.time() - self.start_time
        self.stdout.write(f'⏰ Total processing time: {total_time/3600:.2f} hours')
        self.stdout.write(f'⚡ Average speed: {total_processed/total_time:.0f} records/second')
