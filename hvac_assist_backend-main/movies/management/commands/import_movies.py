from django.core.management.base import BaseCommand
import pandas as pd
import numpy as np
from movies.models import Movie
from django.db import transaction
from datetime import datetime
import sys
from django.db import connection
import psycopg2
import csv
from tqdm import tqdm

class Command(BaseCommand):
    help = 'Import movie data from CSV in chunks'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=30000,
            help='Number of records to process in each chunk'
        )
        parser.add_argument(
            '--skip-rows',
            type=int,
            default=0,
            help='Number of rows to skip (resume from last position)'
        )

    def clean_data(self, chunk_df):
        """Clean and prepare data for import"""
        # Convert date columns
        date_columns = ['date_sh', 'release_date', 'running_date']
        for col in date_columns:
            chunk_df[col] = pd.to_datetime(chunk_df[col]).dt.date

        # Convert datetime columns
        datetime_columns = ['last_updates', 'dsr_date_sh', 'dsr_last_updates']
        for col in datetime_columns:
            chunk_df[col] = pd.to_datetime(chunk_df[col])

        # Convert time column
        chunk_df['time_sh'] = pd.to_datetime(chunk_df['time_sh']).dt.time

        # Convert boolean columns
        chunk_df['ticket_availability'] = chunk_df['ticket_availability'].astype(bool)
        chunk_df['is_ticketing'] = chunk_df['is_ticketing'].astype(bool)

        # Convert numeric columns
        numeric_columns = ['price', 'child', 'senior', 'total_seats', 'available', 
                         'reserved', 'checkered', 'actual_total_seats', 'actual_available',
                         'actual_reserved', 'actual_checkered', 'before_reserved',
                         'on_reserved', 'after_reserved']
        
        for col in numeric_columns:
            chunk_df[col] = pd.to_numeric(chunk_df[col], errors='coerce')

        return chunk_df

    def bulk_insert_using_copy(self, cursor, table_name, df):
        """Use PostgreSQL COPY command for fast bulk insert"""
        # Replace empty strings and None with NaN
        df = df.replace(['', 'None', None], np.nan)
        
        # Convert and fill integer columns
        integer_columns = ['total_seats', 'available', 'reserved', 'checkered',
                       'actual_total_seats', 'actual_available', 'actual_reserved',
                       'actual_checkered', 'before_reserved', 'on_reserved',
                       'after_reserved', 'runtime']
        for col in integer_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            
        # Convert and fill decimal columns
        decimal_columns = ['price', 'child', 'senior']
        for col in decimal_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(float)
        
        # Fill boolean columns with False
        boolean_columns = ['ticket_availability', 'is_ticketing']
        df[boolean_columns] = df[boolean_columns].fillna(False)
        
        # Fill string columns with empty string
        string_columns = ['theater_id', 'mm_id', 'circuit_name', 'theater_name',
                         'theater_address', 'theater_city', 'theater_state', 'theater_zip',
                         'country', 'dma', 'title', 'studio_name', 'genre', 'rating',
                         'auditorium', 'screen_format', 'movie_format', 'language_format',
                         'seating_type', 'amenities', 'source_flag']
        df[string_columns] = df[string_columns].fillna('')

        # Create a string buffer
        from io import StringIO
        buffer = StringIO()
        
        # Write the dataframe to the buffer
        df.to_csv(buffer, index=False, header=False, na_rep='\\N')
        buffer.seek(0)
        
        # Generate column names string
        columns = ','.join(['"{}"'.format(c) for c in df.columns])
        
        try:
            cursor.copy_expert(
                f"COPY {table_name} ({columns}) FROM STDIN WITH CSV NULL '\\N'",
                buffer
            )
        except Exception as e:
            print(f"Error during COPY: {str(e)}")
            raise

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        chunk_size = options['chunk_size']
        skip_rows = options['skip_rows']

        # Get total number of rows
        with open(csv_file, 'r') as f:
            total_rows = sum(1 for line in f) - 1  # subtract header row

        self.stdout.write(f"Total rows to process: {total_rows:,}")
        self.stdout.write(f"Processing in chunks of {chunk_size:,}")
        
        # Create a progress bar
        progress = tqdm(total=total_rows, initial=skip_rows, 
                       desc="Importing data", unit="records")

        try:
            # Get database connection details from Django
            db_settings = connection.settings_dict
            conn = psycopg2.connect(
                dbname=db_settings['NAME'],
                user=db_settings['USER'],
                password=db_settings['PASSWORD'],
                host=db_settings['HOST'],
                port=db_settings['PORT']
            )
            
            # Use connection context
            with conn:
                with conn.cursor() as cursor:
                    # Process the CSV in chunks
                    for chunk_df in pd.read_csv(
                        csv_file, 
                        chunksize=chunk_size,
                        skiprows=range(1, skip_rows + 1) if skip_rows else None
                    ):
                        try:
                            # Clean the data
                            chunk_df = self.clean_data(chunk_df)
                            
                            # Bulk insert using COPY
                            self.bulk_insert_using_copy(cursor, 'movies', chunk_df)
                            
                            # Update progress
                            progress.update(len(chunk_df))
                            
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(f"Error processing chunk: {str(e)}")
                            )
                            # Log the last processed position
                            self.stdout.write(
                                f"Last processed position: {progress.n:,}"
                            )
                            raise

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to import data: {str(e)}")
            )
            raise

        finally:
            progress.close()

        self.stdout.write(
            self.style.SUCCESS(f"Successfully imported {progress.n:,} records")
        )
