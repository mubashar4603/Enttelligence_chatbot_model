#!/usr/bin/env python3
"""
Safe Database Reset and CSV Import Command
Handles Pinecone embeddings properly to avoid breaking RAG

SAFE STRATEGY:
1. Clear database tables (including performance cache)
2. Clear EmbeddingChunk table (database references)
3. Optionally clear/rebuild Pinecone (user choice - recommended for fresh start)
4. Import fresh CSV data
5. Optionally rebuild embeddings (if Pinecone was cleared)
"""

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from movies.models import (
    Movie, FilmPerformanceSummary, TheaterPerformance, MarketAnalysis,
    ComparativeAnalysis, MovieDailyPerformance, MoviePerformanceComparison,
    EmbeddingChunk
)
from movies.management.commands.import_csv_to_movies import Command as ImportCSVCommand
import logging
from pinecone import Pinecone
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Safely reset database and re-import CSV data with Pinecone embedding management'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-path',
            type=str,
            default='/home/ec2-user/Enttelligence_chatbot_model/Entelligence_7.4M_dataset.csv',
            help='Path to CSV file (default: Entelligence_7.4M_dataset.csv)',
        )
        parser.add_argument(
            '--rebuild-embeddings',
            action='store_true',
            help='Rebuild Pinecone embeddings after import (recommended if data changed)',
        )
        parser.add_argument(
            '--clear-pinecone',
            action='store_true',
            help='Clear Pinecone index before import (use with --rebuild-embeddings)',
        )
        parser.add_argument(
            '--keep-embeddings',
            action='store_true',
            help='Keep existing Pinecone embeddings (not recommended - vectors may reference old IDs)',
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=50000,
            help='CSV import chunk size (default: 50000)',
        )
        parser.add_argument(
            '--skip-import',
            action='store_true',
            help='Only clear tables, skip CSV import (useful for testing)',
        )

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🔄 SAFE DATABASE RESET AND IMPORT'))
        self.stdout.write('=' * 70)
        self.stdout.write('')
        
        # Validate options
        if options['clear_pinecone'] and options['keep_embeddings']:
            self.stdout.write(
                self.style.ERROR('❌ Cannot use --clear-pinecone and --keep-embeddings together')
            )
            return
        
        if options['keep_embeddings'] and not options['skip_import']:
            self.stdout.write(
                self.style.WARNING('⚠️  WARNING: Keeping embeddings with new data may break RAG!')
            )
            self.stdout.write('   Pinecone vectors may reference old Movie IDs that no longer exist.')
            self.stdout.write('   Recommended: Use --rebuild-embeddings instead')
            response = input('   Continue anyway? (yes/no): ')
            if response.lower() != 'yes':
                self.stdout.write('   Cancelled.')
                return
        
        try:
            # Step 1: Clear database tables
            self.stdout.write('')
            self.stdout.write('📋 Step 1: Clearing database tables...')
            self.clear_database_tables()
            
            # Step 2: Handle Pinecone embeddings
            self.stdout.write('')
            self.stdout.write('📋 Step 2: Managing Pinecone embeddings...')
            if options['clear_pinecone']:
                self.clear_pinecone_index()
            elif options['keep_embeddings']:
                self.stdout.write('   ℹ️  Keeping existing Pinecone embeddings')
            else:
                self.stdout.write('   ℹ️  Keeping Pinecone index intact (use --rebuild-embeddings after import)')
            
            # Step 3: Import CSV data
            if not options['skip_import']:
                self.stdout.write('')
                self.stdout.write('📋 Step 3: Importing CSV data...')
                self.import_csv_data(options['csv_path'], options['chunk_size'])
            else:
                self.stdout.write('')
                self.stdout.write('⏭️  Skipping CSV import (--skip-import)')
            
            # Step 4: Rebuild embeddings if requested
            if options['rebuild_embeddings']:
                self.stdout.write('')
                self.stdout.write('📋 Step 4: Rebuilding Pinecone embeddings...')
                self.rebuild_embeddings()
            
            self.stdout.write('')
            self.stdout.write('=' * 70)
            self.stdout.write(self.style.SUCCESS('✅ Database reset and import completed successfully!'))
            self.stdout.write('=' * 70)
            
            # Summary
            self.stdout.write('')
            self.stdout.write('📊 Summary:')
            movie_count = Movie.objects.count()
            self.stdout.write(f'   • Movies in database: {movie_count:,}')
            
            if not options['keep_embeddings'] and not options['rebuild_embeddings']:
                self.stdout.write('   ⚠️  IMPORTANT: Pinecone embeddings may be out of sync!')
                self.stdout.write('   Run: python manage.py run_entelligence_pipeline to rebuild embeddings')
            
        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ Error during reset/import: {e}'))
            logger.exception("Database reset/import failed")
            raise

    def clear_database_tables(self):
        """Clear all database tables safely using fast TRUNCATE"""
        try:
            self.stdout.write('   🗑️  Clearing all database tables (FAST TRUNCATE)...')
            start_time = time.time()
            
            with connection.cursor() as cursor:
                # Use TRUNCATE for fast deletion (instant for any table size)
                # CASCADE automatically handles foreign key dependencies
                # RESTART IDENTITY resets auto-increment sequences
                
                # Get counts before deletion for reporting
                cursor.execute("SELECT COUNT(*) FROM movies;")
                movie_count = cursor.fetchone()[0]
                
                self.stdout.write(f'      📊 Found {movie_count:,} Movie records to delete')
                self.stdout.write('      ⚡ Using TRUNCATE (instant deletion)...')
                
                # TRUNCATE in dependency order (child tables first, parent last)
                tables_to_truncate = [
                    'embedding_chunks',           # References movies
                    'movie_daily_performance',     # References movies  
                    'movie_performance_comparison', # References movies
                    'movies_filmperformancesummary',
                    'movies_theaterperformance',
                    'movies_marketanalysis',
                    'movies_comparativeanalysis',
                    'movies',                      # Parent table (last)
                ]
                
                # Disable foreign key checks temporarily for faster truncate
                cursor.execute("SET session_replication_role = 'replica';")
                
                for table in tables_to_truncate:
                    try:
                        # TRUNCATE with CASCADE to handle all dependencies
                        # RESTART IDENTITY resets auto-increment sequences
                        cursor.execute(f'TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;')
                        self.stdout.write(f'      ✅ {table} cleared')
                    except Exception as table_error:
                        # Table might not exist, continue
                        if 'does not exist' not in str(table_error).lower():
                            self.stdout.write(f'      ⚠️  {table}: {table_error}')
                
                # Re-enable foreign key checks
                cursor.execute("SET session_replication_role = 'origin';")
            
            elapsed = time.time() - start_time
            self.stdout.write(f'      ✅ All tables cleared in {elapsed:.2f} seconds!')
            self.stdout.write(f'      📊 Deleted {movie_count:,} Movie records + related tables')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Error clearing tables: {e}'))
            # Fallback to Django ORM delete if TRUNCATE fails
            self.stdout.write('   🔄 Falling back to Django ORM delete...')
            try:
                Movie.objects.all().delete()
                MovieDailyPerformance.objects.all().delete()
                MoviePerformanceComparison.objects.all().delete()
                FilmPerformanceSummary.objects.all().delete()
                TheaterPerformance.objects.all().delete()
                MarketAnalysis.objects.all().delete()
                ComparativeAnalysis.objects.all().delete()
                EmbeddingChunk.objects.all().delete()
                self.stdout.write('      ✅ Tables cleared (fallback method)')
            except Exception as fallback_error:
                self.stdout.write(self.style.ERROR(f'   ❌ Fallback also failed: {fallback_error}'))
                raise

    def clear_pinecone_index(self):
        """Clear Pinecone index completely"""
        try:
            self.stdout.write('   🗑️  Clearing Pinecone index...')
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            index_name = "customer-database-vectors"
            index = pc.Index(index_name)
            
            # Get stats before deletion
            stats = index.describe_index_stats()
            vector_count = stats.get('total_vector_count', 0)
            self.stdout.write(f'      📊 Current vectors in Pinecone: {vector_count:,}')
            
            # Delete all vectors (delete_all deletes everything in the index)
            index.delete(delete_all=True)
            
            # Verify deletion
            new_stats = index.describe_index_stats()
            new_vector_count = new_stats.get('total_vector_count', 0)
            
            if new_vector_count == 0:
                self.stdout.write(f'      ✅ Pinecone index cleared successfully')
            else:
                self.stdout.write(
                    self.style.WARNING(f'      ⚠️  Warning: {new_vector_count:,} vectors still remain')
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Error clearing Pinecone: {e}'))
            raise

    def import_csv_data(self, csv_path, chunk_size):
        """Import CSV data using existing import command"""
        try:
            self.stdout.write(f'   📂 CSV file: {csv_path}')
            self.stdout.write(f'   📊 Chunk size: {chunk_size:,}')
            
            # Use existing import command (without reset flag since we already cleared)
            import_command = ImportCSVCommand()
            
            # Run import with options
            from io import StringIO
            import sys
            
            # Capture output
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            
            try:
                import_command.handle(
                    csv_path=csv_path,
                    chunk_size=chunk_size,
                    reset=False,  # Already cleared
                    checkpoint_interval=2
                )
            finally:
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                # Print import output
                if output:
                    for line in output.strip().split('\n'):
                        if line.strip():
                            self.stdout.write(f'      {line}')
            
            movie_count = Movie.objects.count()
            self.stdout.write(f'   ✅ Import completed: {movie_count:,} records')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Error importing CSV: {e}'))
            raise

    def rebuild_embeddings(self):
        """Rebuild Pinecone embeddings from fresh data"""
        try:
            self.stdout.write('   🔄 Starting embedding pipeline...')
            self.stdout.write('   ⏳ This may take a while...')
            
            # Run the embedding pipeline
            from django.core.management import call_command
            
            call_command(
                'run_entelligence_pipeline',
                parallel=True,
                chunk_size=50000
            )
            
            # Verify embeddings
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            index = pc.Index("customer-database-vectors")
            stats = index.describe_index_stats()
            vector_count = stats.get('total_vector_count', 0)
            
            self.stdout.write(f'   ✅ Embeddings rebuilt: {vector_count:,} vectors in Pinecone')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Error rebuilding embeddings: {e}'))
            self.stdout.write('   💡 You can rebuild manually later with:')
            self.stdout.write('      python manage.py run_entelligence_pipeline')
            # Don't raise - import was successful, embeddings can be rebuilt later

