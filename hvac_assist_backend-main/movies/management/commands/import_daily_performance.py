#!/usr/bin/env python3
"""
Import Daily Performance Data from AI_Data_Dump_All_Titles CSV
Cleans data and populates MovieDailyPerformance table
"""

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from movies.models import MovieDailyPerformance
import pandas as pd
import numpy as np
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from tqdm import tqdm
import re
import os
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import and clean daily performance data from AI_Data_Dump_All_Titles CSV into MovieDailyPerformance table'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-path',
            type=str,
            default='/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv',
            help='Path to the CSV file',
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=10000,
            help='Number of records to process per chunk (default: 10000)',
        )
        parser.add_argument(
            '--skip-delete',
            action='store_true',
            help='Skip deleting existing data (for incremental imports)',
        )

    def clean_numeric_string(self, value):
        """Remove commas and convert to numeric value"""
        if pd.isna(value) or value == '' or value is None:
            return 0
        
        # Convert to string and remove commas
        if isinstance(value, str):
            value = value.replace(',', '').strip()
            # Handle negative values
            if value.startswith('-'):
                try:
                    num = float(value)
                    # Set negative values to 0 (data cleaning)
                    return max(0, num)
                except (ValueError, TypeError):
                    return 0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0
        try:
            num = float(value)
            return max(0, num)  # Ensure non-negative
        except (ValueError, TypeError):
            return 0

    def parse_date(self, date_str):
        """Parse date string in various formats"""
        if pd.isna(date_str) or date_str == '' or date_str is None:
            return None
        
        date_str = str(date_str).strip()
        
        # Try common date formats
        date_formats = [
            '%m/%d/%Y',
            '%Y-%m-%d',
            '%m-%d-%Y',
            '%d/%m/%Y',
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        # If all formats fail, try pandas parsing
        try:
            parsed = pd.to_datetime(date_str)
            return parsed.date()
        except:
            return None

    def calculate_dir_value(self, date_sh, release_date):
        """Calculate DIR (Days In Release) value based on model formula"""
        if date_sh is None or release_date is None:
            return None
        
        if date_sh < release_date:
            # Before release: negative values
            delta = date_sh - release_date
            return delta.days
        else:
            # On or after release: starting from DIR = 1 on release day
            delta = date_sh - release_date
            return delta.days + 1

    def clean_dataframe(self, df):
        """Clean and prepare dataframe for import"""
        self.stdout.write('🧹 Cleaning data...')
        
        # Remove rows with missing critical data
        initial_count = len(df)
        df = df.dropna(subset=['Title', 'release_date', 'Running Date'])
        df = df[df['Title'].notna() & (df['Title'] != '')]
        df = df[df['release_date'].notna() & (df['release_date'] != '')]
        df = df[df['Running Date'].notna() & (df['Running Date'] != '')]
        
        removed = initial_count - len(df)
        if removed > 0:
            self.stdout.write(
                self.style.WARNING(f'   Removed {removed} rows with missing critical data')
            )
        
        # Parse dates
        self.stdout.write('   Parsing dates...')
        df['release_date_parsed'] = df['release_date'].apply(self.parse_date)
        df['date_sh_parsed'] = df['Running Date'].apply(self.parse_date)
        
        # Remove rows where date parsing failed
        before_date_clean = len(df)
        df = df[df['release_date_parsed'].notna()]
        df = df[df['date_sh_parsed'].notna()]
        after_date_clean = len(df)
        
        if before_date_clean != after_date_clean:
            self.stdout.write(
                self.style.WARNING(
                    f'   Removed {before_date_clean - after_date_clean} rows with invalid dates'
                )
            )
        
        # Clean numeric fields
        self.stdout.write('   Cleaning numeric fields...')
        df['total_revenue'] = df['Sales Estimate'].apply(self.clean_numeric_string)
        df['total_reserved_seats'] = df['Reserved'].apply(self.clean_numeric_string).astype(int)
        
        # Clean DBR value - convert to integer, handling various formats
        def clean_dbr(x):
            if pd.isna(x):
                return None
            try:
                # Convert to string, strip whitespace, then to int
                x_str = str(x).strip()
                if x_str == '' or x_str == 'nan':
                    return None
                return int(float(x_str))  # Use float first to handle "1.0" -> 1
            except (ValueError, TypeError):
                return None
        
        df['dbr_value'] = df['DBR'].apply(clean_dbr)
        
        # Calculate DIR value
        self.stdout.write('   Calculating DIR values...')
        df['dir_value'] = df.apply(
            lambda row: self.calculate_dir_value(row['date_sh_parsed'], row['release_date_parsed']),
            axis=1
        )
        
        # Remove rows where DIR calculation failed
        before_dir_clean = len(df)
        df = df[df['dir_value'].notna()]
        after_dir_clean = len(df)
        
        if before_dir_clean != after_dir_clean:
            self.stdout.write(
                self.style.WARNING(
                    f'   Removed {before_dir_clean - after_dir_clean} rows with invalid DIR calculation'
                )
            )
        
        # Set default values for missing fields
        df['total_impressions'] = df['total_reserved_seats']
        df['total_seats'] = 0  # Not available in CSV
        df['cumulative_revenue'] = 0  # Will be calculated later
        df['cumulative_reserved'] = 0  # Will be calculated later
        
        # Calculate average price (if revenue and reserved are available)
        df['avg_price'] = df.apply(
            lambda row: (
                Decimal(str(row['total_revenue'])) / Decimal(str(row['total_reserved_seats']))
                if row['total_reserved_seats'] > 0 else None
            ),
            axis=1
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'   ✓ Cleaned data: {len(df)} rows remaining')
        )
        
        return df

    def calculate_cumulative_values(self, df):
        """Calculate cumulative revenue and reserved seats per movie"""
        self.stdout.write('📊 Calculating cumulative values...')
        
        # Sort by title, release_date, and DBR value (ascending: -45, -44, ..., -1, 0, 1, 2, ...)
        # This ensures we process from earliest presale day to release day and beyond
        df = df.sort_values(['Title', 'release_date_parsed', 'dbr_value'], na_position='last')
        
        # Group by title and release_date, then calculate cumulative sums
        df['cumulative_revenue'] = df.groupby(['Title', 'release_date_parsed'])['total_revenue'].cumsum()
        df['cumulative_reserved'] = df.groupby(['Title', 'release_date_parsed'])['total_reserved_seats'].cumsum()
        
        return df

    def calculate_dod_metrics(self, df):
        """Calculate day-over-day percentage changes"""
        self.stdout.write('📈 Calculating day-over-day metrics...')
        
        # Sort by title, release_date, and DBR value (ascending: -45, -44, ..., -1, 0, 1, 2, ...)
        # This ensures DoD calculations compare consecutive days in correct chronological order
        df = df.sort_values(['Title', 'release_date_parsed', 'dbr_value'], na_position='last')
        
        # Group by title and release_date
        grouped = df.groupby(['Title', 'release_date_parsed'])
        
        # Calculate DoD revenue change
        df['prev_revenue'] = grouped['total_revenue'].shift(1)
        df['dod_revenue_change'] = df.apply(
            lambda row: (
                ((row['total_revenue'] - row['prev_revenue']) / row['prev_revenue'] * 100)
                if pd.notna(row['prev_revenue']) and row['prev_revenue'] > 0
                else None
            ),
            axis=1
        )
        
        # Calculate DoD reserved change
        df['prev_reserved'] = grouped['total_reserved_seats'].shift(1)
        df['dod_reserved_change'] = df.apply(
            lambda row: (
                ((row['total_reserved_seats'] - row['prev_reserved']) / row['prev_reserved'] * 100)
                if pd.notna(row['prev_reserved']) and row['prev_reserved'] > 0
                else None
            ),
            axis=1
        )
        
        # Drop temporary columns
        df = df.drop(columns=['prev_revenue', 'prev_reserved'])
        
        return df

    def handle(self, *args, **options):
        csv_path = options['csv_path']
        chunk_size = options['chunk_size']
        skip_delete = options['skip_delete']
        
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting Daily Performance Data Import')
        )
        self.stdout.write(f'   CSV Path: {csv_path}')
        self.stdout.write(f'   Chunk Size: {chunk_size}')
        
        # Step 1: Delete existing data
        if not skip_delete:
            self.stdout.write('\n🗑️  Deleting existing MovieDailyPerformance data...')
            deleted_count = MovieDailyPerformance.objects.all().delete()[0]
            self.stdout.write(
                self.style.SUCCESS(f'   ✓ Deleted {deleted_count} existing records')
            )
        else:
            self.stdout.write(
                self.style.WARNING('⏭️  Skipping deletion (--skip-delete flag set)')
            )
        
        # Step 2: Read and process CSV file in chunks
        self.stdout.write(f'\n📖 Reading CSV file: {csv_path}')
        
        if not os.path.exists(csv_path):
            self.stdout.write(
                self.style.ERROR(f'   ✗ CSV file not found: {csv_path}')
            )
            return
        
        # First, get total row count for progress tracking
        total_rows = sum(1 for _ in open(csv_path, 'r')) - 1  # Subtract header
        self.stdout.write(f'   Total rows in CSV: {total_rows:,}')
        
        # Process CSV in chunks to handle large files efficiently
        all_cleaned_chunks = []
        chunk_number = 0
        total_processed = 0
        
        try:
            for chunk_df in pd.read_csv(csv_path, chunksize=chunk_size, low_memory=False):
                chunk_number += 1
                chunk_rows = len(chunk_df)
                total_processed += chunk_rows
                
                self.stdout.write(
                    f'\n   Processing chunk {chunk_number} ({chunk_rows:,} rows) - '
                    f'Progress: {total_processed:,}/{total_rows:,} ({100*total_processed/total_rows:.1f}%)'
                )
                
                # Clean this chunk
                cleaned_chunk = self.clean_dataframe(chunk_df)
                
                if len(cleaned_chunk) > 0:
                    all_cleaned_chunks.append(cleaned_chunk)
                
                # Show progress
                if chunk_number % 10 == 0:
                    self.stdout.write(f'   ✓ Processed {chunk_number} chunks')
            
            if len(all_cleaned_chunks) == 0:
                self.stdout.write(
                    self.style.ERROR('   ✗ No valid data remaining after cleaning')
                )
                return
            
            # Combine all cleaned chunks
            self.stdout.write(f'\n   Combining {len(all_cleaned_chunks)} cleaned chunks...')
            df = pd.concat(all_cleaned_chunks, ignore_index=True)
            self.stdout.write(
                self.style.SUCCESS(f'   ✓ Combined into {len(df):,} total valid rows')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'   ✗ Error reading CSV: {str(e)}')
            )
            import traceback
            self.stdout.write(traceback.format_exc())
            return
        
        # Step 3: Calculate cumulative values (requires full dataset)
        df = self.calculate_cumulative_values(df)
        
        # Step 4: Calculate DoD metrics (requires full dataset)
        df = self.calculate_dod_metrics(df)
        
        # Step 5: Prepare and insert data in batches
        self.stdout.write('\n💾 Preparing data for database import...')
        
        inserted_count = 0
        batch_size = 1000
        total_batches = (len(df) + batch_size - 1) // batch_size
        
        for batch_num in tqdm(range(0, len(df), batch_size), desc='Inserting batches', total=total_batches):
            batch_df = df.iloc[batch_num:batch_num + batch_size]
            performance_objects = []
            
            for _, row in batch_df.iterrows():
                try:
                    obj = MovieDailyPerformance(
                        title=str(row['Title'])[:255],  # Ensure max length
                        release_date=row['release_date_parsed'],
                        date_sh=row['date_sh_parsed'],
                        dir_value=int(row['dir_value']),
                        dbr_value=int(row['dbr_value']) if pd.notna(row['dbr_value']) else None,
                        total_reserved_seats=int(row['total_reserved_seats']),
                        total_impressions=int(row['total_impressions']),
                        total_revenue=Decimal(str(row['total_revenue'])),
                        total_seats=int(row['total_seats']),
                        dod_revenue_change=float(row['dod_revenue_change']) if pd.notna(row['dod_revenue_change']) else None,
                        dod_reserved_change=float(row['dod_reserved_change']) if pd.notna(row['dod_reserved_change']) else None,
                        cumulative_revenue=Decimal(str(row['cumulative_revenue'])),
                        cumulative_reserved=int(row['cumulative_reserved']),
                        avg_price=Decimal(str(row['avg_price'])) if pd.notna(row['avg_price']) else None,
                        occupancy_rate=None,  # Not available from CSV
                    )
                    performance_objects.append(obj)
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'   Skipping row due to error: {str(e)}')
                    )
                    continue
            
            # Insert this batch
            if performance_objects:
                try:
                    with transaction.atomic():
                        MovieDailyPerformance.objects.bulk_create(
                            performance_objects,
                            ignore_conflicts=True,  # Handle duplicates gracefully
                            batch_size=batch_size
                        )
                    inserted_count += len(performance_objects)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'   Error inserting batch {batch_num//batch_size + 1}: {str(e)}')
                    )
                    # Try inserting one by one to identify problematic records
                    for obj in performance_objects:
                        try:
                            obj.save()
                            inserted_count += 1
                        except Exception as e2:
                            self.stdout.write(
                                self.style.WARNING(f'   Skipping record: {str(e2)}')
                            )
                            continue
        
        # Final summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS(f'✅ Import Complete!')
        )
        self.stdout.write(f'   Total rows in CSV: {total_rows}')
        self.stdout.write(f'   Valid rows after cleaning: {len(df)}')
        self.stdout.write(f'   Records inserted: {inserted_count}')
        self.stdout.write('='*60)

