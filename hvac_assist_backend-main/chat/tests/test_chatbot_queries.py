"""
Test script for comprehensive chatbot query testing
"""

import os
import django
import sys
import json
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from chat.query_handler import QueryHandler
from chat.rag_service import get_rag_service

class ChatbotQueryTests(TestCase):
    def setUp(self):
        # Create test user
        User = get_user_model()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Set up API client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Initialize query handler
        self.rag_service = get_rag_service()
        self.query_handler = QueryHandler(self.rag_service)

    def test_regular_queries(self):
        """Test regular informational queries"""
        regular_queries = [
            "Tell me about the movie 'Avatar 2' and its available formats.",
            "What are the amenities offered at AMC Empire 25 theater?",
            "What is the runtime and rating of 'Dune' playing at AMC?",
            "Give me details about the IMAX screen at Regal Union Square.",
            "What are the showtimes for movies at AMC Empire 25 tonight?"
        ]
        
        print("\nTesting Regular Queries:")
        for query in regular_queries:
            print(f"\nQuery: {query}")
            response = self.query_handler.process_query(query)
            print(f"Response Type: {response.get('type')}")
            print(f"Response: {response.get('message')}")
            self.assertIsNotNone(response.get('message'))

    def test_analytical_queries(self):
        """Test analytical queries"""
        analytical_queries = [
            "What is the average ticket price for IMAX movies compared to standard format?",
            "How does seating availability compare between weekend and weekday shows?",
            "What are the most popular movie showtimes across all theaters?",
            "Compare the occupancy rates between AMC and Regal theaters.",
            "What's the price distribution for movies across different formats and times?"
        ]
        
        print("\nTesting Analytical Queries:")
        for query in analytical_queries:
            print(f"\nQuery: {query}")
            response = self.query_handler.process_query(query)
            print(f"Response Type: {response.get('type')}")
            print(f"Response: {response.get('message')}")
            print(f"Data: {json.dumps(response.get('data'), indent=2) if response.get('data') else 'No data'}")
            self.assertEqual(response.get('type'), 'analytical')

    def test_comparison_queries(self):
        """Test comparison queries"""
        comparison_queries = [
            "Show me movies similar to 'Avatar 2' in terms of genre and format.",
            "Compare ticket prices between AMC Empire 25 and Regal Union Square.",
            "Find movies like 'Dune' playing in IMAX format.",
            "Which theaters near AMC Empire 25 have better seating capacity?",
            "Compare available showtimes for sci-fi movies across all theaters."
        ]
        
        print("\nTesting Comparison Queries:")
        for query in comparison_queries:
            print(f"\nQuery: {query}")
            response = self.query_handler.process_query(query)
            print(f"Response Type: {response.get('type')}")
            print(f"Response: {response.get('message')}")
            self.assertIsNotNone(response.get('message'))

    def test_complex_queries(self):
        """Test complex multi-aspect queries"""
        complex_queries = [
            "Tell me about IMAX movies playing tonight with good seat availability and prices under $20.",
            "Which theater has the best combination of premium formats and reasonable prices for 'Avatar 2'?",
            "Find family-friendly movies with matinee shows and special child pricing options.",
            "Compare weekend IMAX showings across theaters with their occupancy rates and price ranges.",
            "What are the best value-for-money options for watching new releases this week?"
        ]
        
        print("\nTesting Complex Queries:")
        for query in complex_queries:
            print(f"\nQuery: {query}")
            response = self.query_handler.process_query(query)
            print(f"Response Type: {response.get('type')}")
            print(f"Response: {response.get('message')}")
            self.assertIsNotNone(response.get('message'))

    def test_edge_cases(self):
        """Test edge case queries"""
        edge_case_queries = [
            "Are there any movies playing at non-existent theater XYZ?",
            "Tell me about upcoming movies that haven't been released yet.",
            "Compare prices for movies playing at 3 AM in the morning.",
            "What's the seating availability for movies playing last week?",
            "Show me movies with negative ticket prices or impossible showtimes."
        ]
        
        print("\nTesting Edge Cases:")
        for query in edge_case_queries:
            print(f"\nQuery: {query}")
            response = self.query_handler.process_query(query)
            print(f"Response Type: {response.get('type')}")
            print(f"Response: {response.get('message')}")
            self.assertIsNotNone(response.get('message'))

if __name__ == '__main__':
    # Set up Django environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
    django.setup()
    
    # Run the tests
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    test_runner.run_tests(['chat.tests.test_chatbot_queries'])
