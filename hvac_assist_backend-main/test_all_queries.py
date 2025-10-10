"""
Comprehensive test script for Enhanced Query Handler
Tests all query types with real-world examples
"""

import os
import django
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from chat.enhanced_query_handler import EnhancedQueryHandler
from chat.rag_service import get_rag_service
import json

def print_response(query, response):
    """Pretty print query and response"""
    print("\n" + "="*80)
    print(f"🔍 QUERY: {query}")
    print("="*80)
    print(f"\n📊 TYPE: {response.get('type', 'unknown')}")
    print(f"\n💬 RESPONSE:\n{response.get('message', 'No message')}")
    
    if response.get('data'):
        print(f"\n📈 DATA:")
        print(json.dumps(response.get('data'), indent=2, default=str))
    
    if response.get('sources'):
        print(f"\n📚 SOURCES: {', '.join(response.get('sources'))}")
    
    print("\n" + "-"*80)

def run_tests():
    """Run all test cases"""
    
    # Initialize handler
    print("\n🚀 Initializing Enhanced Query Handler...")
    rag_service = get_rag_service()
    handler = EnhancedQueryHandler(rag_service)
    print("✅ Handler initialized successfully!\n")
    
    # Test Categories
    test_categories = {
        "COMPLEX ANALYTICAL QUERIES": [
            """Analyze AMC theaters in California and show me:
- Total number of screens
- Average seat capacity
- Percentage of premium format screens
- Average ticket prices
- Total reserved seats across all showings""",
            
            """For the movie 'Dune: Part Two', give me a statistical breakdown of:
- Total number of showings
- Average seats reserved per showing
- Most common screening formats
- Average ticket prices by format
- Top 5 theaters by attendance rate"""
        ],
        
        "INFORMATION QUERIES": [
            "Tell me about the movie 'Avatar 2' and its available formats.",
            "What are the amenities offered at AMC Empire 25 theater?",
            "What is the runtime and rating of 'Dune' playing at AMC?",
            "Give me details about the IMAX screen at Regal Union Square.",
            "What are the showtimes for movies at AMC Empire 25 tonight?"
        ],
        
        "ANALYTICAL COMPARISONS": [
            "What is the average ticket price for IMAX movies compared to standard format?",
            "How does seating availability compare between weekend and weekday shows?",
            "What are the most popular movie showtimes across all theaters?",
            "Compare the occupancy rates between AMC and Regal theaters.",
            "What's the price distribution for movies across different formats and times?"
        ],
        
        "SIMILARITY & COMPARISON QUERIES": [
            "Show me movies similar to 'Avatar 2' in terms of genre and format.",
            "Compare ticket prices between AMC Empire 25 and Regal Union Square.",
            "Find movies like 'Dune' playing in IMAX format.",
            "Which theaters near AMC Empire 25 have better seating capacity?",
            "Compare available showtimes for sci-fi movies across all theaters."
        ],
        
        "COMPLEX MULTI-CRITERIA QUERIES": [
            "Tell me about IMAX movies playing tonight with good seat availability and prices under $20.",
            "Which theater has the best combination of premium formats and reasonable prices for 'Avatar 2'?",
            "Find family-friendly movies with matinee shows and special child pricing options.",
            "Compare weekend IMAX showings across theaters with their occupancy rates and price ranges.",
            "What are the best value-for-money options for watching new releases this week?"
        ],
        
        "EDGE CASES & ERROR HANDLING": [
            "Are there any movies playing at non-existent theater XYZ?",
            "Tell me about upcoming movies that haven't been released yet.",
            "Compare prices for movies playing at 3 AM in the morning.",
            "What's the seating availability for movies playing last week?",
            "Show me movies with negative ticket prices or impossible showtimes."
        ],
        
        "SIMPLE COUNT & SUM QUERIES": [
            "How many horror movies are there?",
            "Total number of IMAX movies",
            "Sum of reserved seats for all movies",
            "Count of movies in New York",
            "How many PG-13 action movies?"
        ],
        
        "TOP N QUERIES": [
            "Top 10 most expensive movies",
            "Top 5 cheapest tickets",
            "Top 20 most popular movies by reservations",
            "Best rated movies",
            "Top 3 theaters with most showtimes"
        ]
    }
    
    # Run all tests
    total_tests = sum(len(queries) for queries in test_categories.values())
    current_test = 0
    
    for category, queries in test_categories.items():
        print(f"\n\n{'#'*80}")
        print(f"# {category}")
        print(f"{'#'*80}")
        
        for query in queries:
            current_test += 1
            print(f"\n[Test {current_test}/{total_tests}]")
            
            try:
                response = handler.process_query(query)
                print_response(query, response)
            except Exception as e:
                print(f"\n❌ ERROR: {str(e)}")
                import traceback
                traceback.print_exc()
    
    print(f"\n\n{'='*80}")
    print(f"✅ Completed {total_tests} test queries!")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    run_tests()

