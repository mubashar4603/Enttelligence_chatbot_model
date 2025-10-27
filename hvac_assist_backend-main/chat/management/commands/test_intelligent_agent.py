"""
Django management command to test the Intelligent Film Analytics Agent
Tests 25 diverse query types with real movie data from the database
"""

from django.core.management.base import BaseCommand
from chat.intelligent_film_analytics_agent import IntelligentFilmAnalyticsAgent
from movies.models import Movie
import json
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Test the Intelligent Film Analytics Agent with 25 diverse queries'

    def __init__(self):
        super().__init__()
        self.test_results = []
        self.passed_tests = 0
        self.failed_tests = 0

    def handle(self, *args, **options):
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS(
            "🎬 STARTING COMPREHENSIVE TEST SUITE FOR FILM ANALYTICS AGENT"
        ))
        self.stdout.write("="*80 + "\n")

        # Load test data
        self.load_test_data()

        # Get agent
        agent = IntelligentFilmAnalyticsAgent()

        # Test queries
        tests = self.get_test_queries()

        # Run all tests
        for i, (query, expected_type, description) in enumerate(tests, 1):
            self.run_test(agent, i, query, expected_type, description)

        # Print summary
        self.print_summary()

    def load_test_data(self):
        """Load test data from database"""
        self.movies = list(Movie.objects.values_list('title', flat=True).distinct()[:20])
        self.theater_ids = list(Movie.objects.values_list('theater_id', flat=True).distinct()[:20])
        self.cities = list(Movie.objects.values_list('theater_city', flat=True).distinct()[:20])
        self.studios = list(Movie.objects.values_list('studio_name', flat=True).distinct()[:20])
        self.genres = list(Movie.objects.values_list('genre', flat=True).distinct()[:10])
        self.circuits = list(Movie.objects.values_list('circuit_name', flat=True).distinct()[:10])

        self.stdout.write(f"📊 Loaded test data:")
        self.stdout.write(f"   • Movies: {len(self.movies)}")
        self.stdout.write(f"   • Theaters: {len(self.theater_ids)}")
        self.stdout.write(f"   • Cities: {len(self.cities)}")
        self.stdout.write(f"   • Studios: {len(self.studios)}")
        self.stdout.write(f"   • Genres: {len(self.genres)}")
        self.stdout.write(f"   • Circuits: {len(self.circuits)}\n")

    def get_test_queries(self):
        """Get list of test queries"""
        sample_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        return [
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

    def run_test(self, agent, test_num, query, expected_type, description):
        """Run a single test"""
        self.stdout.write("\n" + "="*80)
        self.stdout.write(f"TEST {test_num}: {description}")
        self.stdout.write("="*80)
        self.stdout.write(f"Query: {query}\n")

        try:
            # Process the query
            result = agent.process_intelligent_query(query)

            # Extract information
            query_type = result.get('query_type', 'unknown')
            message = result.get('message', '')
            data = result.get('data')
            accuracy = result.get('accuracy', 'unknown')

            # Check if query was understood correctly
            success = True
            if expected_type and query_type != expected_type:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  WARNING: Expected type '{expected_type}', got '{query_type}'"
                ))
                success = False

            # Check if we got a meaningful response
            if not message or len(message) < 50:
                self.stdout.write(self.style.WARNING(
                    "⚠️  WARNING: Response too short or empty"
                ))
                success = False

            # Check if it's a default/generic response
            if 'entelligence ai assistant' in message.lower() and 'more specific' in message.lower():
                self.stdout.write(self.style.ERROR(
                    "❌ FAILED: Got generic response asking for clarification"
                ))
                success = False

            # Display results
            if success:
                self.stdout.write(self.style.SUCCESS("✅ PASSED"))
                self.passed_tests += 1
            else:
                self.stdout.write(self.style.ERROR("❌ FAILED"))
                self.failed_tests += 1

            self.stdout.write(f"\nQuery Type: {query_type}")
            self.stdout.write(f"Accuracy: {accuracy}")
            self.stdout.write(f"\nResponse Preview:")
            self.stdout.write("─"*80)
            # Show first 300 chars of response
            preview = message[:300] + "..." if len(message) > 300 else message
            self.stdout.write(preview)
            self.stdout.write("─"*80 + "\n")

            # Store result
            self.test_results.append({
                'query_num': test_num,
                'query': query,
                'description': description,
                'success': success,
                'query_type': query_type,
                'expected_type': expected_type,
                'accuracy': accuracy,
                'response_preview': preview
            })

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ ERROR: {str(e)}"))
            self.failed_tests += 1
            self.test_results.append({
                'query_num': test_num,
                'query': query,
                'description': description,
                'success': False,
                'error': str(e)
            })

    def print_summary(self):
        """Print test summary"""
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS("📊 TEST SUMMARY"))
        self.stdout.write("="*80)
        self.stdout.write(f"Total Tests: {len(self.test_results)}")
        self.stdout.write(self.style.SUCCESS(f"✅ Passed: {self.passed_tests}"))
        self.stdout.write(self.style.ERROR(f"❌ Failed: {self.failed_tests}"))
        self.stdout.write(f"Success Rate: {(self.passed_tests / len(self.test_results) * 100):.1f}%")
        self.stdout.write("="*80 + "\n")

        # Show failed tests
        failed = [r for r in self.test_results if not r.get('success', False)]
        if failed:
            self.stdout.write("\n❌ FAILED TESTS:")
            for test in failed:
                self.stdout.write(f"\n  Test {test['query_num']}: {test.get('description', 'N/A')}")
                self.stdout.write(f"    Query: {test['query']}")
                if 'error' in test:
                    self.stdout.write(f"    Error: {test['error']}")

        # Save detailed results to file
        results_file = 'test_results.json'
        with open(results_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_tests': len(self.test_results),
                'passed': self.passed_tests,
                'failed': self.failed_tests,
                'success_rate': (self.passed_tests / len(self.test_results) * 100),
                'results': self.test_results
            }, f, indent=2)

        self.stdout.write(f"\n💾 Detailed results saved to {results_file}")

