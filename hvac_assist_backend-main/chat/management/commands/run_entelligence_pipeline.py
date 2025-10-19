#!/usr/bin/env python3
"""
Django management command to run the Entelligence film analytics embedding pipeline
"""

from django.core.management.base import BaseCommand
from chat.precision_entelligence_system import PrecisionEntelligenceSystem
from chat.thread_parallel_pipeline import ThreadBasedParallelSystem
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run the Entelligence film analytics embedding pipeline'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset the Pinecone index before running',
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=50000,
            help='Chunk size for processing (default: 25000)',
        )
        parser.add_argument(
            '--parallel',
            action='store_true',
            help='Use high-performance thread-based parallel pipeline (recommended for G4dn instances)',
        )
        parser.add_argument(
            '--threads',
            type=int,
            default=8,
            help='Number of parallel threads (parallel mode only, default: 8)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=512,
            help='Embedding batch size (parallel mode only, default: 512)',
        )

    def handle(self, *args, **options):
        if options['parallel']:
            self.stdout.write(
                self.style.SUCCESS('🚀 Starting High-Performance Thread-Based Parallel Pipeline')
            )
            self.stdout.write(
                self.style.SUCCESS('⚡ FIXED VERSION - NO PICKLE ISSUES')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('🚀 Starting Precision Entelligence Pipeline')
            )
            self.stdout.write(
                self.style.SUCCESS('💾 Periodic Checkpoints Every 2 Chunks')
            )
        
        try:
            if options['parallel']:
                # Initialize thread-based parallel pipeline
                pipeline = ThreadBasedParallelSystem()
                
                # Update configuration based on arguments
                if options['chunk_size']:
                    pipeline.config['CHUNK_SIZE'] = options['chunk_size']
                if options['threads']:
                    pipeline.config['NUM_THREADS'] = options['threads']
                if options['batch_size']:
                    pipeline.config['BATCH_SIZE'] = options['batch_size']
                    pipeline.config['GPU_BATCH_SIZE'] = options['batch_size'] * 2
                
                # Show configuration
                self.stdout.write(f"📦 Chunk size: {pipeline.config['CHUNK_SIZE']:,}")
                self.stdout.write(f"🧵 Threads: {pipeline.config['NUM_THREADS']}")
                self.stdout.write(f"📊 Batch size: {pipeline.config['BATCH_SIZE']}")
                
                # Run thread-based parallel pipeline
                pipeline.run_thread_parallel_pipeline()
                
                self.stdout.write(
                    self.style.SUCCESS('✅ High-performance thread-based parallel pipeline completed successfully!')
                )
            else:
                # Initialize precision pipeline
                pipeline = PrecisionEntelligenceSystem()
                
                # Update chunk size if provided
                if options['chunk_size']:
                    pipeline.config['CHUNK_SIZE'] = options['chunk_size']
                
                # Run precision pipeline
                pipeline.run_precision_pipeline()
                
                self.stdout.write(
                    self.style.SUCCESS('✅ Pipeline completed successfully!')
                )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Pipeline failed: {e}')
            )
            raise
