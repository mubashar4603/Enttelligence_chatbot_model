"""
Tests for the QueryHandler class functionality.
Tests both analytical queries and RAG-based responses.
"""
from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta
from chat.query_handler import QueryHandler
from movies.models import Movie
import json

class MockRAGService:
    """Mock RAG service for testing"""
    def query(self, user_query, top_k=None, return_sources=False):
        if "unavailable" in user_query.lower():
            return None
        return {
            'answer': f'Mock RAG response for: {user_query}',
            'sources': ['source1', 'source2']
        }

class QueryHandlerTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.rag_service = MockRAGService()
        self.query_handler = QueryHandler(rag_service=self.rag_service)
        
        # Create test movies with different formats and times
        current_time = timezone.now()
        release_date = current_time.date()
        
        # IMAX Movies
        for i in range(3):
            Movie.objects.create(
                title=f'IMAX Movie {i+1}',
                movie_format='IMAX',
                price=15.99,
                child=12.99,  # Adding child price
                senior=13.99,  # Adding senior price
                total_seats=100,
                reserved=30,
                available=70,
                date_sh=current_time.date(),
                time_sh=current_time.replace(hour=14+i).time(),
                theater_name='AMC Theater',
                release_date=release_date,  # Adding required field
                screen_format='IMAX',
                # Adding remaining required fields
                theater_id=f'AMC{i+1}',
                circuit_name='AMC',
                theater_address='234 W 42nd St',
                theater_city='New York',
                theater_state='NY',
                theater_zip='10036',
                country='USA',
                studio_name='20th Century Studios',
                genre='Action',
                rating='PG-13',
                auditorium=str(i+1),
                language_format='English',
                checkered=0,
                actual_total_seats=100,
                actual_available=70,
                actual_reserved=30,
                actual_checkered=0,
                before_reserved=25,
                on_reserved=5,
                after_reserved=0,
                seating_type='Standard',
                amenities='',
                ticket_availability=True,
                is_ticketing=True,
                source_flag='',
                last_updates=current_time,
                running_date=current_time.date()
            )
        
        # Standard Movies
        for i in range(3):
            Movie.objects.create(
                title=f'Standard Movie {i+1}',
                movie_format='Standard',
                price=10.99,
                child=8.99,  # Adding child price
                senior=9.99,  # Adding senior price
                total_seats=80,
                reserved=20,
                available=60,
                date_sh=current_time.date(),
                time_sh=current_time.replace(hour=13+i).time(),
                theater_name='Regal Cinema',
                release_date=release_date,  # Adding required field
                screen_format='2D',
                # Adding remaining required fields
                theater_id=f'RGL{i+1}',
                circuit_name='Regal',
                theater_address='100 E Main St',
                theater_city='Los Angeles',
                theater_state='CA',
                theater_zip='90012',
                country='USA',
                studio_name='Universal Pictures',
                genre='Comedy',
                rating='PG',
                auditorium=str(i+1),
                language_format='English',
                checkered=0,
                actual_total_seats=80,
                actual_available=60,
                actual_reserved=20,
                actual_checkered=0,
                before_reserved=15,
                on_reserved=5,
                after_reserved=0,
                seating_type='Standard',
                amenities='',
                ticket_availability=True,
                is_ticketing=True,
                source_flag='',
                last_updates=current_time,
                running_date=current_time.date()
            )

    def test_showtime_analysis(self):
        """Test popular showtimes analysis"""
        query = "What are the most popular movie showtimes across all theaters?"
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertEqual(response['type'], 'analytical')
        self.assertIn('message', response)
        self.assertIn('data', response)
        self.assertIn('showtime_analysis', response['data'])
        self.assertIn('hourly_distribution', response['data']['showtime_analysis'])
        self.assertIn('popular_theaters', response['data']['showtime_analysis'])
        self.assertIn('total_shows', response['data']['showtime_analysis'])

    def test_price_comparison(self):
        """Test IMAX vs Standard price comparison"""
        query = "What's the price difference between IMAX and Standard formats?"
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertEqual(response['type'], 'analytical')
        self.assertIn('message', response)
        self.assertIn('data', response)
        self.assertIn('price_comparison', response['data'])
        
        # Verify IMAX is more expensive than Standard
        price_data = response['data']['price_comparison']
        for day_type in ['weekday', 'weekend']:
            if price_data[day_type]['IMAX'] and price_data[day_type]['Standard']:
                self.assertGreater(
                    price_data[day_type]['IMAX'],
                    price_data[day_type]['Standard']
                )

    def test_seating_analysis(self):
        """Test seating capacity analysis"""
        query = "What's the average seating capacity and occupancy rate?"
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertEqual(response['type'], 'analytical')
        self.assertIn('message', response)
        self.assertIn('data', response)
        self.assertIn('seating_analysis', response['data'])
        
        # Verify seat numbers are integers
        seating_data = response['data']['seating_analysis']
        self.assertIn('avg_total_seats', seating_data)
        self.assertIn('avg_reserved', seating_data)
        self.assertIn('avg_available', seating_data)
        self.assertIsInstance(seating_data['avg_total_seats'], (int, float))
        self.assertIsInstance(seating_data['avg_reserved'], (int, float))
            
    def test_rag_query_success(self):
        """Test successful RAG query"""
        query = "Tell me about the movie experience"
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertEqual(response['type'], 'rag')
        self.assertIn('message', response)
        self.assertIn('Mock RAG response', response['message'])
        self.assertIn('sources', response)
        self.assertEqual(response['sources'], ['source1', 'source2'])
        
    def test_rag_query_no_results(self):
        """Test RAG query with no results"""
        query = "Tell me about unavailable information"
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertEqual(response['type'], 'error')
        self.assertIn('error', response)
        self.assertIn('message', response)
        self.assertIn('rephrase', response['message'].lower())

    def test_empty_query(self):
        """Test handling of empty query"""
        query = ""
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertIn('message', response)
        self.assertIn('type', response)

    def test_error_handling(self):
        """Test error handling with invalid data"""
        # Testing empty query
        response = self.query_handler.process_query("")
        self.assertEqual(response['type'], 'error')
        self.assertIn('error', response)
        self.assertIn('message', response)
        
        # Testing query with special characters
        response = self.query_handler.process_query("$%^&*")
        self.assertEqual(response['type'], 'error')
        self.assertIn('error', response)
        self.assertIn('message', response)
        
        # Testing with no movies
        Movie.objects.all().delete()
        query = "Compare prices between formats"
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertIn('message', response)
        self.assertIn('type', response)
        self.assertEqual(response['type'], 'error')
        self.assertIn('error', response)
        
    def test_non_analytical_query(self):
        """Test fallback to RAG for non-analytical queries"""
        query = "Tell me about the plot of Avatar"
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertEqual(response['type'], 'rag')
        self.assertIn('message', response)
        self.assertIn('Mock RAG response', response['message'])
        
    def test_invalid_analytical_query(self):
        """Test handling of invalid analytical queries"""
        query = "What's the quantum analysis of movie prices?"
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertEqual(response['type'], 'error')
        self.assertIn('error', response)
        self.assertIn('supported_analyses', response)
        
    def test_edge_cases(self):
        """Test edge cases and error handling"""
        # Empty query
        response = self.query_handler.process_query("")
        self.assertEqual(response['type'], 'error')
        self.assertIn('error', response)
        self.assertIn('message', response)
        
        # Query with special characters
        response = self.query_handler.process_query("What's the price of $%^&* movies?")
        self.assertEqual(response['type'], 'error')
        self.assertIn('error', response)
        self.assertIn('message', response)
        
        # Delete all movies and test with no data
        Movie.objects.all().delete()
        query = "What are the most popular showtimes?"
        response = self.query_handler.process_query(query)
        self.assertEqual(response['type'], 'error')
        self.assertIn('error', response)
        self.assertIn('message', response)
        self.assertTrue(
            'no movie data' in response['message'].lower() or
            'no data available' in response['message'].lower()
        )
        
    def test_complex_query(self):
        """Test complex analytical query combining multiple aspects"""
        query = "Compare IMAX vs Standard formats in terms of price, occupancy, and popular times"
        response = self.query_handler.process_query(query)
        
        self.assertIsNotNone(response)
        self.assertEqual(response['type'], 'analytical')
        self.assertIn('message', response)
        self.assertIn('data', response)
        
        # Verify presence of required data
        data = response['data']
        if 'price_comparison' in data:
            self.assertIn('weekday', data['price_comparison'])
            self.assertIn('weekend', data['price_comparison'])
            for day_type in ['weekday', 'weekend']:
                self.assertIn('IMAX', data['price_comparison'][day_type])
                self.assertIn('Standard', data['price_comparison'][day_type])
            
        if 'showtime_analysis' in data:
            self.assertIn('hourly_distribution', data['showtime_analysis'])
            self.assertIn('total_shows', data['showtime_analysis'])
            
        # Verify presence of key terms in message
        message = response['message']
        self.assertTrue(
            'IMAX' in message or 
            'price' in message.lower() or 
            'showtime' in message.lower() or
            'seating' in message.lower()
        )
