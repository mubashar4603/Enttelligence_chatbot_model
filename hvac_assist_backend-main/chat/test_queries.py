"""
Test Suite for Intelligent Film Analytics Agent
Tests 25 diverse query types with real movie data from the database
"""

import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')

import django
django.setup()

from chat.intelligent_film_analytics_agent import IntelligentFilmAnalyticsAgent
from movies.models import Movie
import json
from datetime import datetime, timedelta

class QueryTester:
    """Test suite for the intelligent film analytics agent"""
    
    def __init__(self):
        self.agent = IntelligentFilmAnalyticsAgent()
        self.test_results = []
        self.passed_tests = 0
        self.failed_tests = 0
        
        # Get real data from database
        self.movies = list(Movie.objects.values_list('title', flat=True).distinct()[:20])
        self.theater_ids = list(Movie.objects.values_list('theater_id', flat=True).distinct()[:20])
        self.cities = list(Movie.objects.values_list('theater_city', flat=True).distinct()[:20])
        self.studios = list(Movie.objects.values_list('studio_name', flat=True).distinct()[:20])
        self.genres = list(Movie.objects.values_list('genre', flat=True).distinct()[:10])
        self.circuits = list(Movie.objects.values_list('circuit_name', flat=True).distinct()[:10])
        
        print(f"📊 Loaded test data:")
        print(f"   • Movies: {len(self.movies)}")
        print(f"   • Theaters: {len(self.theater_ids)}")
        print(f"   • Cities: {len(self.cities)}")
        print(f"   • Studios: {len(self.studios)}")
        print(f"   • Genres: {len(self.genres)}")
        print(f"   • Circuits: {len(self.circuits)}\n")
    
    def test_query(self, query_num, query, expected_type=None, description=""):
        """Test a single query"""
        print(f"{'='*80}")
        print(f"TEST {query_num}: {description}")
        print(f"{'='*80}")
        print(f"Query: {query}\n")
        
        try:
            # Process the query
            result = self.agent.process_intelligent_query(query)
            
            # Extract information
            query_type = result.get('query_type', 'unknown')
            message = result.get('message', '')
            data = result.get('data')
            accuracy = result.get('accuracy', 'unknown')
            
            # Check if query was understood correctly
            success = True
            if expected_type and query_type != expected_type:
                print(f"⚠️  WARNING: Expected type '{expected_type}', got '{query_type}'")
                success = False
            
            # Check if we got a meaningful response
            if not message or len(message) < 50:
                print(f"⚠️  WARNING: Response too short or empty")
                success = False
            
            # Check if it's a default/generic response
            if 'entelligence ai assistant' in message.lower() and 'more specific' in message.lower():
                print(f"❌ FAILED: Got generic response asking for clarification")
                success = False
            
            # Display results
            if success:
                print(f"✅ PASSED")
                self.passed_tests += 1
            else:
                print(f"❌ FAILED")
                self.failed_tests += 1
            
            print(f"\nQuery Type: {query_type}")
            print(f"Accuracy: {accuracy}")
            print(f"\nResponse Preview:")
            print(f"{'─'*80}")
            # Show first 300 chars of response
            preview = message[:300] + "..." if len(message) > 300 else message
            print(preview)
            print(f"{'─'*80}\n")
            
            # Store result
            self.test_results.append({
                'query_num': query_num,
                'query': query,
                'description': description,
                'success': success,
                'query_type': query_type,
                'expected_type': expected_type,
                'accuracy': accuracy,
                'response_preview': preview
            })
            
            return success
            
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            self.failed_tests += 1
            self.test_results.append({
                'query_num': query_num,
                'query': query,
                'description': description,
                'success': False,
                'error': str(e)
            })
            return False
    
    def run_all_tests(self):
        """Run all test queries"""
        print("\n" + "="*80)
        print("🎬 STARTING COMPREHENSIVE TEST SUITE FOR FILM ANALYTICS AGENT")
        print("="*80 + "\n")
        
        # Get some sample dates
        sample_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # Test queries
        tests = [
            # 1. Movie Listing
            ("list me all the movie titles", "movie_listing", "Movie listing query"),
            
            # 2. Theater Listing  
            ("list me all the unique theaters", "theater_listing", "Theater listing query"),
            
            # 3. Comp Titles
            (f"what are the best comp titles for {self.movies[0]}", "comp_titles", "Comp titles query"),
            
            # 4. Sales Prediction (generic)
            (f"estimated sales for {self.movies[1]}", "sales_prediction", "Sales prediction query"),
            
            # 5. Performance Analysis
            (f"how is {self.movies[2]} performing", "performance_analysis", "Performance analysis query"),
            
            # 6. Occupancy Rate Analysis
            (f"what is the average seat occupancy rate across all theaters for {self.movies[3]} Movie", "occupancy_rate_analysis", "Occupancy rate analysis"),
            
            # 7. Peak Hours Analysis
            ("identify peak showtime hours based on reservations", "peak_hours_analysis", "Peak hours analysis"),
            
            # 8. Theater Update
            (f"when was the last update for theater {self.theater_ids[0]}", "theater_update", "Theater update query"),
            
            # 9. Date-based Movies
            (f"what movies are showing in theaters for {sample_date}", "date_movies", "Date-based movie listing"),
            
            # 10. Runtime Filter
            ("which movies have a runtime longer than 150 minutes", "runtime_filter", "Runtime filter query"),
            
            # 11. International Screenings
            ("list all international non-US movie screenings", "international_screenings", "International screenings"),
            
            # 12. IMAX Theater Count
            ("count theaters offering IMAX", "imax_theater_count", "IMAX theater count"),
            
            # 13. Auditorium Analysis
            ("what is the average number of auditoriums per theater", "auditorium_analysis", "Auditorium analysis"),
            
            # 14. Studio/Genre Query
            (f"which studios have movies releasing on {sample_date}", "studio_genre", "Studio release query"),
            
            # 15. Circuit Comparison
            (f"which circuit has more theaters: {self.circuits[0]} or {self.circuits[1]}", "circuit_comparison", "Circuit comparison"),
            
            # 16. Theater Location
            (f"list all theaters in {self.cities[0]}", "theater_location", "Theater location query"),
            
            # 17. Amenities/Format
            (f"what amenities are available at theater ID {self.theater_ids[1]}", "amenities_format", "Amenities query"),
            
            # 18. Pricing/Seats
            ("show me all movies with ticket prices under $15", "pricing_seats", "Pricing query"),
            
            # 19. Movie Performance (generic)
            (f"what is the performance of {self.movies[4]}", "movie_performance", "Generic movie performance"),
            
            # 20. Showtime Analysis
            ("what are the most popular showtimes", "showtime_analysis", "Showtime analysis"),
            
            # 21. Seating Analysis
            ("show me seating availability", "seating_analysis", "Seating analysis"),
            
            # 22. Price Analysis
            ("what is the price difference between weekend and weekday shows", "price_analysis", "Price analysis"),
            
            # 23. Theater Comparison
            (f"compare theaters {self.theater_ids[2]} and {self.theater_ids[3]}", "theater_comparison", "Theater comparison"),
            
            # 24. Movie Information
            (f"tell me about {self.movies[5]}", "movie_information", "Movie information"),
            
            # 25. Format Analysis
            ("what are the advantages of watching in IMAX", "format_analysis", "Format analysis"),
        ]
        
        # Run all tests
        for i, (query, expected_type, description) in enumerate(tests, 1):
            self.test_query(i, query, expected_type, description)
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("📊 TEST SUMMARY")
        print("="*80)
        print(f"Total Tests: {len(self.test_results)}")
        print(f"✅ Passed: {self.passed_tests}")
        print(f"❌ Failed: {self.failed_tests}")
        print(f"Success Rate: {(self.passed_tests / len(self.test_results) * 100):.1f}%")
        print("="*80 + "\n")
        
        # Show failed tests
        failed = [r for r in self.test_results if not r.get('success', False)]
        if failed:
            print("\n❌ FAILED TESTS:")
            for test in failed:
                print(f"\n  Test {test['query_num']}: {test.get('description', 'N/A')}")
                print(f"    Query: {test['query']}")
                if 'error' in test:
                    print(f"    Error: {test['error']}")
        
        # Save detailed results to file
        with open('test_results.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_tests': len(self.test_results),
                'passed': self.passed_tests,
                'failed': self.failed_tests,
                'success_rate': (self.passed_tests / len(self.test_results) * 100),
                'results': self.test_results
            }, f, indent=2)
        
        print("\n💾 Detailed results saved to test_results.json")

if __name__ == '__main__':
    tester = QueryTester()
    tester.run_all_tests()

