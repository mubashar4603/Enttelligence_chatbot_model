#!/usr/bin/env python3
"""
Script to clear analytics tables before re-importing data
"""
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append('/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main')

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')

try:
    django.setup()
    
    from movies.models import FilmPerformanceSummary, TheaterPerformance, MarketAnalysis, ComparativeAnalysis
    
    print('🗑️ Clearing analytics tables...')
    
    # Get current counts
    film_count = FilmPerformanceSummary.objects.count()
    theater_count = TheaterPerformance.objects.count()
    market_count = MarketAnalysis.objects.count()
    comparative_count = ComparativeAnalysis.objects.count()
    
    print(f'Before clearing:')
    print(f'  FilmPerformanceSummary: {film_count:,} records')
    print(f'  TheaterPerformance: {theater_count:,} records')
    print(f'  MarketAnalysis: {market_count:,} records')
    print(f'  ComparativeAnalysis: {comparative_count:,} records')
    
    # Delete all records
    print('\nDeleting all analytics records...')
    FilmPerformanceSummary.objects.all().delete()
    TheaterPerformance.objects.all().delete()
    MarketAnalysis.objects.all().delete()
    ComparativeAnalysis.objects.all().delete()
    
    # Verify deletion
    print('\nAfter clearing:')
    print(f'  FilmPerformanceSummary: {FilmPerformanceSummary.objects.count()} records')
    print(f'  TheaterPerformance: {TheaterPerformance.objects.count()} records')
    print(f'  MarketAnalysis: {MarketAnalysis.objects.count()} records')
    print(f'  ComparativeAnalysis: {ComparativeAnalysis.objects.count()} records')
    
    print('\n✅ All analytics tables cleared successfully!')
    
except Exception as e:
    print(f'❌ Error clearing analytics tables: {e}')
    sys.exit(1)
