"""
Simple demonstration of enhanced query capabilities with realistic queries
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from chat.enhanced_query_handler import EnhancedQueryHandler
from chat.rag_service import get_rag_service
from movies.models import Movie

def print_response(query, response):
    """Pretty print query and response"""
    print("\n" + "="*80)
    print(f"🔍 QUERY: {query}")
    print("="*80)
    print(f"TYPE: {response.get('type', 'unknown')}")
    print("\n" + response.get('message', 'No message'))
    print("-"*80)

def main():
    print("\n🎬 MOVIE DATABASE ENHANCED QUERY HANDLER DEMO")
    print("="*80)
    
    # First, let's see what's in the database
    total_movies = Movie.objects.count()
    genres = Movie.objects.values_list('genre', flat=True).distinct()[:10]
    theaters = Movie.objects.values_list('theater_name', flat=True).distinct()[:5]
    sample_movies = Movie.objects.values_list('title', flat=True).distinct()[:5]
    
    print(f"\n📊 DATABASE STATS:")
    print(f"   • Total showtimes: {total_movies:,}")
    print(f"   • Sample genres: {', '.join(list(genres))}")
    print(f"   • Sample theaters: {', '.join(list(theaters))}")
    print(f"   • Sample movies: {', '.join(list(sample_movies))}")
    
    # Initialize handler
    rag_service = get_rag_service()
    handler = EnhancedQueryHandler(rag_service)
    
    # Demonstration queries that work with real data
    demo_queries = [
        # Count queries
        "How many horror movies are there?",
        "Total number of drama movies",
        "Count of movies rated R",
        
        # Top queries
        "Top 5 movies with most reserved seats",
        "Show me the top 10 most popular movies by showtimes",
        
        # Average queries
        "What's the average seating capacity across all theaters?",
        "Average number of reserved seats per showing",
        
        # Sum queries
        "Total reserved seats for all movies",
        "Sum of total seats across all showtimes",
        
        # Filtered queries
        "How many R-rated movies are there?",
        "List all horror movies",
        "Show me drama movies",
        
        # Complex analytical
        "Show me all unique movie titles",
        "What genres are available?",
    ]
    
    print("\n\n🚀 RUNNING DEMONSTRATION QUERIES")
    print("="*80)
    
    for i, query in enumerate(demo_queries, 1):
        print(f"\n[Query {i}/{len(demo_queries)}]")
        try:
            response = handler.process_query(query)
            print_response(query, response)
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n\n✅ DEMONSTRATION COMPLETE!")
    print("="*80)

if __name__ == '__main__':
    main()

