import os
import django
import sys
import json
import uuid
from django.test import TestCase
from accounts.models import CustomUser
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework import exceptions
from rest_framework.request import Request
from chat.models import Conversation, Message
from chat.views import MessageViewSet
from movies.models import Movie
from datetime import datetime, timezone

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)

class MessageViewSetTests(TestCase):
    def setUp(self):
        # Create test user
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Set up the viewset
        self.factory = APIRequestFactory()
        self.viewset = MessageViewSet()
        
        # Create test movie data
        current_time = datetime.now(timezone.utc)
        
        # IMAX movies
        Movie.objects.create(
            title="Avatar 2",
            screen_format="IMAX",
            price=18.99,
            child=14.99,
            senior=16.99,
            date_sh=current_time.date(),
            time_sh=current_time.time(),
            release_date=current_time.date(),
            theater_id="T001",
            circuit_name="AMC",
            theater_name="AMC Empire 25",
            theater_address="234 W 42nd St",
            theater_city="New York",
            theater_state="NY",
            theater_zip="10036",
            country="USA",
            studio_name="20th Century Studios",
            genre="Action",
            rating="PG-13",
            auditorium="1",
            movie_format="Digital",
            language_format="English",
            total_seats=200,
            available=100,
            reserved=100,
            checkered=0,
            actual_total_seats=200,
            actual_available=100,
            actual_reserved=100,
            actual_checkered=0,
            before_reserved=90,
            on_reserved=10,
            after_reserved=0,
            seating_type="Standard",
            amenities="",
            ticket_availability=True,
            is_ticketing=True,
            source_flag="",
            last_updates=current_time,
            running_date=current_time.date()
            theater_name="AMC Empire 25",
            theater_address="234 W 42nd St",
            theater_city="New York",
            theater_state="NY",
            theater_zip="10036",
            country="USA",
            studio_name="20th Century Studios",
            genre="Action",
            rating="PG-13",
            auditorium="1",
            movie_format="Digital",
            language_format="English",
            total_seats=200,
            available=100,
            reserved=100,
            checkered=0,
            actual_total_seats=200,
            actual_available=100,
            actual_reserved=100,
            actual_checkered=0,
            before_reserved=90,
            on_reserved=10
        )
        Movie.objects.create(
            title="Dune",
            screen_format="IMAX",
            price=19.99,
            child=15.99,
            senior=17.99,
            date_sh=current_time.date(),
            time_sh=current_time.time(),
            release_date=current_time.date(),
            theater_id="T002",
            circuit_name="AMC",
            theater_name="AMC Empire 25",
            theater_address="234 W 42nd St",
            theater_city="New York",
            theater_state="NY",
            theater_zip="10036",
            country="USA",
            studio_name="Warner Bros",
            genre="Sci-Fi",
            rating="PG-13",
            auditorium="2",
            movie_format="Digital",
            language_format="English",
            total_seats=200,
            available=120,
            reserved=80,
            checkered=0,
            actual_total_seats=200,
            actual_available=120,
            actual_reserved=80,
            actual_checkered=0,
            before_reserved=70,
            on_reserved=10,
            after_reserved=0,
            seating_type="Standard",
            amenities="",
            ticket_availability=True,
            is_ticketing=True,
            source_flag="",
            last_updates=current_time,
            running_date=current_time.date()
            circuit_name="AMC",
            theater_name="AMC Empire 25",
            theater_address="234 W 42nd St",
            theater_city="New York",
            theater_state="NY",
            theater_zip="10036",
            country="USA",
            studio_name="Warner Bros",
            genre="Sci-Fi",
            rating="PG-13",
            auditorium="2",
            movie_format="Digital",
            language_format="English",
            total_seats=200,
            available=120,
            reserved=80,
            checkered=0,
            actual_total_seats=200,
            actual_available=120,
            actual_reserved=80,
            actual_checkered=0,
            before_reserved=70,
            on_reserved=10
        )
            
        # Standard format movies
        Movie.objects.create(
            title="The Matrix",
            screen_format="Standard",
            price=12.99,
            child=9.99,
            senior=10.99,
            date_sh=datetime.now(timezone.utc),
            time_sh=datetime.now(timezone.utc).time(),
            release_date=datetime.now(timezone.utc).date(),
            theater_id="T003",
            circuit_name="Regal",
            theater_name="Regal Union Square",
            theater_address="850 Broadway",
            theater_city="New York",
            theater_state="NY",
            theater_zip="10003",
            country="USA",
            studio_name="Warner Bros",
            genre="Sci-Fi",
            rating="R",
            auditorium="3",
            movie_format="Digital",
            language_format="English",
            total_seats=150,
            available=90,
            reserved=60,
            checkered=0,
            actual_total_seats=150,
            actual_available=90,
            actual_reserved=60,
            actual_checkered=0,
            before_reserved=50,
            on_reserved=10
        )
        
        Movie.objects.create(
            title="Inception",
            screen_format="Standard",
            price=13.99,
            child=10.99,
            senior=11.99,
            date_sh=datetime.now(timezone.utc),
            time_sh=datetime.now(timezone.utc).time(),
            release_date=datetime.now(timezone.utc).date(),
            theater_id="T004",
            circuit_name="Regal",
            theater_name="Regal Union Square",
            theater_address="850 Broadway",
            theater_city="New York",
            theater_state="NY",
            theater_zip="10003",
            country="USA",
            studio_name="Warner Bros",
            genre="Sci-Fi",
            rating="PG-13",
            auditorium="4",
            movie_format="Digital",
            language_format="English",
            total_seats=150,
            available=85,
            reserved=65,
            checkered=0,
            actual_total_seats=150,
            actual_available=85,
            actual_reserved=65,
            actual_checkered=0,
            before_reserved=55,
            on_reserved=10
        )

    def make_request(self, message_content):
        """Helper method to create and process a request"""
        from rest_framework.parsers import JSONParser
        from django.http import QueryDict
        from io import BytesIO
        
        request_data = {
            'content': message_content,
            'sender': 'user'
        }
        
        # Create request with proper content type
        request = self.factory.post(
            '/api/messages/',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        request.user = self.user
        
        # Create proper DRF request with parser
        drf_request = Request(request)
        drf_request.user = self.user
        drf_request._full_data = request_data  # Set parsed data directly
        
        # Set up viewset
        self.viewset.request = drf_request
        self.viewset.format_kwarg = None
        
        # Process request
        return self.viewset.create(drf_request)

    def test_analytical_query(self):
        """Test handling of an analytical query"""
        print("\nTesting analytical query...")
        try:
            response = self.make_request("What is the average price of IMAX movies compared to standard format?")
            print(f"Status Code: {response.status_code}")
            print(f"Response Data: {json.dumps(response.data, indent=2, cls=UUIDEncoder)}")
            self.assertEqual(response.status_code, 201)
        except Exception as e:
            print(f"Error in analytical query test: {str(e)}")
            raise

    def test_regular_query(self):
        """Test handling of a regular conversational query"""
        print("\nTesting regular query...")
        try:
            response = self.make_request("Tell me about the movie Avatar")
            print(f"Status Code: {response.status_code}")
            print(f"Response Data: {json.dumps(response.data, indent=2, cls=UUIDEncoder)}")
            self.assertEqual(response.status_code, 201)
        except Exception as e:
            print(f"Error in regular query test: {str(e)}")
            raise

    def test_error_handling(self):
        """Test error handling with an empty message"""
        print("\nTesting error handling...")
        try:
            response = self.make_request("")
            print(f"Status Code: {response.status_code}")
            print(f"Response Data: {json.dumps(response.data, indent=2, cls=UUIDEncoder)}")
        except Exception as e:
            print(f"Error in error handling test: {str(e)}")
            if isinstance(e, exceptions.ValidationError):
                print("Validation error as expected for empty message")
                return
            raise

if __name__ == '__main__':
    # Set up Django environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
    django.setup()
    
    # Run the tests
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=1)
    test_runner.run_tests(['chat.tests.test_message_viewset'])
