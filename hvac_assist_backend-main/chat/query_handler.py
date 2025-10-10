"""
Query handler for processing both RAG and database queries.
Integrates with Django ORM for analytical queries.
"""

from typing import Dict, Any, Union, List
import re
import json
import uuid
import logging
from django.db.models import (
    Avg, Count, Q, F, FloatField, CharField,
    Case, When, Value, ExpressionWrapper
)
from django.db.models.functions import ExtractHour, ExtractWeekDay, Abs

logger = logging.getLogger(__name__)
from django.db.models.expressions import Window
from django.db.models.functions.window import PercentRank
from movies.models import Movie
from .rag_service import get_rag_service

class QueryHandler:
    """Handler for processing both RAG and database queries."""
    
    def _format_analytical_response(self, data: Dict, format_type: str = None) -> str:
        """Format analytical data into natural language response"""
        if not data:
            return "No analytical data available"

        response_parts = []
        
        # Price comparison analysis
        if 'price_comparison' in data:
            price_data = data['price_comparison']
            response_parts.append("\nPrice Analysis:")
            for day_type in ['weekday', 'weekend']:
                response_parts.append(f"\n{day_type.title()}:")
                if price_data[day_type].get('IMAX') and price_data[day_type].get('Standard'):
                    response_parts.append(f"- IMAX: ${price_data[day_type]['IMAX']:.2f}")
                    response_parts.append(f"- Standard: ${price_data[day_type]['Standard']:.2f}")
                    diff = price_data[day_type]['difference']
                    response_parts.append(f"- Difference: ${abs(diff):.2f} {'more' if diff > 0 else 'less'} for IMAX")
                
            if 'overall_difference' in price_data:
                overall_diff = price_data['overall_difference']
                response_parts.append(f"\nOverall: IMAX costs ${abs(overall_diff):.2f} {'more' if overall_diff > 0 else 'less'} than Standard")
            
        # Seating analysis
        if 'seating_analysis' in data:
            seat_data = data['seating_analysis']
            if response_parts:
                response_parts.append("\n")
            response_parts.append("Seating Analysis:")
            response_parts.append(f"- Average total seats: {seat_data['avg_total_seats']:.0f}")
            response_parts.append(f"- Average reserved seats: {seat_data['avg_reserved']:.0f}")
            response_parts.append(f"- Average available seats: {seat_data['avg_available']:.0f}")
            
        # Showtime analysis
        if 'showtime_analysis' in data:
            show_data = data['showtime_analysis']
            if response_parts:
                response_parts.append("\n")
            response_parts.append("Showtime Analysis:")
            
            if 'hourly_distribution' in show_data:
                peak_times = sorted(show_data['hourly_distribution'], 
                                 key=lambda x: (x['show_count'], x['avg_occupancy']), 
                                 reverse=True)[:3]
                response_parts.append("\nPeak showtimes:")
                for slot in peak_times:
                    response_parts.append(f"- {slot['time']}: {slot['show_count']} shows ({slot['avg_occupancy']:.1f}% avg occupancy)")
                    
            if 'popular_theaters' in show_data:
                response_parts.append("\nMost active theaters:")
                for theater in show_data['popular_theaters'][:3]:
                    response_parts.append(f"- {theater['theater']}: Peak at {theater['peak_hour']} ({theater['total_shows']} shows)")
                    
        # Add sample size information
        if 'sample_size' in data:
            response_parts.append(f"\nAnalysis based on {data['sample_size']['total_shows']} total shows.")
            
        return '\n'.join(response_parts) if response_parts else "No analytical data available."
        
        # Price comparison analysis
        if 'price_comparison' in data:
            price_data = data['price_comparison']
            response_parts.append("\nPrice Analysis:")
            for day_type in ['weekday', 'weekend']:
                response_parts.append(f"\n{day_type.title()}:")
                response_parts.append(f"- IMAX: ${price_data[day_type]['IMAX']:.2f}")
                response_parts.append(f"- Standard: ${price_data[day_type]['Standard']:.2f}")
                diff = price_data[day_type]['difference']
                response_parts.append(f"- Difference: ${abs(diff):.2f} {'more' if diff > 0 else 'less'} for IMAX")
                
            overall_diff = price_data['overall_difference']
            response_parts.append(f"\nOverall: IMAX costs ${abs(overall_diff):.2f} {'more' if overall_diff > 0 else 'less'} than Standard")
            
        # Seating analysis
        if 'seating_analysis' in data:
            seat_data = data['seating_analysis']
            if response_parts:
                response_parts.append("\n")
            response_parts.append("Seating Analysis:")
            response_parts.append(f"- Average total seats: {seat_data['avg_total_seats']:.0f}")
            response_parts.append(f"- Average reserved seats: {seat_data['avg_reserved']:.0f}")
            response_parts.append(f"- Average available seats: {seat_data['avg_available']:.0f}")
            
        # Showtime analysis
        if 'showtime_analysis' in data:
            show_data = data['showtime_analysis']
            if response_parts:
                response_parts.append("\n")
            response_parts.append("Showtime Analysis:")
            
            if 'hourly_distribution' in show_data:
                peak_times = sorted(show_data['hourly_distribution'], 
                                 key=lambda x: (x['show_count'], x['avg_occupancy']), 
                                 reverse=True)[:3]
                response_parts.append("\nPeak showtimes:")
                for slot in peak_times:
                    response_parts.append(f"- {slot['time']}: {slot['show_count']} shows ({slot['avg_occupancy']:.1f}% avg occupancy)")
                    
            if 'popular_theaters' in show_data:
                response_parts.append("\nMost active theaters:")
                for theater in show_data['popular_theaters'][:3]:
                    response_parts.append(f"- {theater['theater']}: Peak at {theater['peak_hour']} ({theater['total_shows']} shows)")
                    
        # Add sample size information
        if 'sample_size' in data:
            response_parts.append(f"\nAnalysis based on {data['sample_size']['total_shows']} total shows.")
            
        return '\n'.join(response_parts) if response_parts else "No analytical data available."

class UUIDJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)

class QueryHandler:
    def __init__(self, rag_service=None):
        self.rag_service = rag_service or get_rag_service()
        # Patterns to identify analytical queries
        self.analytical_patterns = {
            'price': [
                r'price\s+(?:comparison|difference|analysis)',
                r'how\s+much\s+(?:does|do|are)\s+(?:it|they|tickets?)\s+cost',
                r'(?:compare|comparing)\s+(?:prices?|formats?)',
                r'cheaper|expensive|cost\s+difference',
                r'ticket\s+prices?',
                r'IMAX.*Standard|Standard.*IMAX'  # Added for format comparison
            ],
            'seating': [
                r'seating\s+(?:capacity|availability|analysis)',
                r'how\s+(?:many|much)\s+seats?',
                r'(?:average|typical)\s+occupancy',
                r'seat(?:ing)?\s+availability',
                r'(?:capacity|occupancy)\s+rate'
            ],
            'showtime': [
                r'(?:popular|common|typical)\s+(?:show\s*times?|time\s*slots?)',
                r'when\s+(?:do|are|is)\s+(?:movies?|shows?)\s+(?:playing|shown)',
                r'(?:busiest|peak)\s+(?:times?|hours?)',
                r'showtime\s+(?:analysis|pattern|distribution)',
                r'movie\s+schedule',
                r'most\s+popular\s+(?:movie\s+)?showtimes?'  # Added for test case
            ]
        }

    def _is_analytical_query(self, query: str) -> bool:
        """Determine if the query requires analytical processing"""
        query = query.lower()
        # Edge cases
        if not query:
            return False
        if re.search(r'[\$%\^&\*]', query):
            return False
            
        # Skip queries that are clearly not analytical
        non_analytical = ['plot', 'story', 'tell me about', 'what is', 'who is']
        if any(term in query for term in non_analytical):
            return False
            
        # Check analytical patterns
        for category, patterns in self.analytical_patterns.items():
            if any(re.search(pattern, query) for pattern in patterns):
                return True
                
        # Check if query looks like it's asking for analysis
        analysis_terms = ['analysis', 'compare', 'percentage', 'average', 'statistics', 'metrics', 'rate', 'trends']
        if any(term in query for term in analysis_terms):
            return True
            
        return False

    def _handle_analytical_query(self, query: str) -> Dict[str, Any]:
        """Handle queries that require database analysis"""
        query = query.lower()
        
        # Check if we have any movie data
        if not Movie.objects.exists():
            return {
                'type': 'error',
                'error': 'No movie data available',
                'message': 'There is currently no movie data available for analysis.'
            }
        
        response = {'type': 'analytical'}
        combined_analysis = []
        data = {}
        
        try:
            # Price analysis
            if any(re.search(pattern, query) for pattern in self.analytical_patterns['price']):
                price_data = self.handle_price_comparison()
                if price_data.get('error'):
                    return {
                        'type': 'error',
                        'error': price_data['error'],
                        'message': 'Error analyzing price data'
                    }
                combined_analysis.append('Price Analysis')
                data['price_comparison'] = price_data['price_comparison']
                data['sample_size'] = price_data['sample_size']
            
            # Seating analysis
            if any(re.search(pattern, query) for pattern in self.analytical_patterns['seating']):
                seating_data = self.handle_seating_analysis()
                if seating_data.get('error'):
                    return {
                        'type': 'error',
                        'error': seating_data['error'],
                        'message': 'Error analyzing seating data'
                    }
                combined_analysis.append('Seating Analysis')
                data['seating_analysis'] = seating_data
            
            # Showtime analysis
            if any(re.search(pattern, query) for pattern in self.analytical_patterns['showtime']):
                showtime_data = self.handle_showtime_analysis()
                if showtime_data.get('error'):
                    return {
                        'type': 'error',
                        'error': showtime_data['error'],
                        'message': 'Error analyzing showtime data'
                    }
                combined_analysis.append('Showtime Analysis')
                data['showtime_analysis'] = showtime_data
                
            if not combined_analysis:
                # First check if there's any data
                if not Movie.objects.exists():
                    return {
                        'type': 'error',
                        'error': 'No movie data available',
                        'message': 'There is currently no movie data available for analysis.'
                    }
                # Then check if query is invalid
                return {
                    'type': 'error',
                    'error': 'Invalid analytical query',
                    'message': 'Could not determine specific analysis type required. Please try a query focused on prices, seating, or showtimes.',
                    'supported_analyses': [
                        'Popular showtimes and peak hours',
                        'Seating capacity and occupancy',
                        'IMAX vs Standard price comparison',
                        'Average pricing analysis'
                    ]
                }
                
            # Valid analysis
            response['analysis'] = ' & '.join(combined_analysis)
            response['data'] = data
            response['message'] = self._format_analytical_response(data, 'combined')
            
            return response
            
        except Exception as e:
            logger.error(f"Error in analytical query handling: {str(e)}")
            return {
                'type': 'error',
                'error': str(e),
                'message': 'An error occurred while analyzing the data'
            }
        
    def handle_price_comparison(self):
        """Compare prices between IMAX and Standard formats"""
        try:
            weekday_weekend = Case(
                When(Q(day_of_week__in=[1, 7]), then=Value('weekend')),
                default=Value('weekday'),
                output_field=CharField(),
            )
            
            price_data = Movie.objects.annotate(
                day_of_week=ExtractWeekDay('date_sh'),
                day_type=weekday_weekend
            ).values('movie_format', 'day_type').annotate(
                avg_price=Avg('price'),
                count=Count('id')
            ).filter(
                movie_format__in=['IMAX', 'Standard']
            ).order_by('movie_format', 'day_type')

            if not price_data:
                return {
                    'error': 'No price data available for IMAX and Standard formats',
                    'message': 'There is no price data available for comparison between IMAX and Standard formats.'
                }

            formatted_data = {
                'weekday': {'IMAX': 0, 'Standard': 0, 'difference': 0},
                'weekend': {'IMAX': 0, 'Standard': 0, 'difference': 0},
                'overall_difference': 0
            }

            for item in price_data:
                format_type = item['movie_format']
                day_type = item['day_type']
                avg_price = round(float(item['avg_price']), 2)
                formatted_data[day_type][format_type] = avg_price

            # Calculate differences
            for day_type in ['weekday', 'weekend']:
                if formatted_data[day_type]['IMAX'] and formatted_data[day_type]['Standard']:
                    formatted_data[day_type]['difference'] = round(
                        formatted_data[day_type]['IMAX'] - formatted_data[day_type]['Standard'], 
                        2
                    )

            # Calculate overall difference
            imax_avg = sum(data['IMAX'] for data in formatted_data.values() if isinstance(data, dict)) / 2
            standard_avg = sum(data['Standard'] for data in formatted_data.values() if isinstance(data, dict)) / 2
            formatted_data['overall_difference'] = round(imax_avg - standard_avg, 2)

            result = {
                'price_comparison': formatted_data,
                'sample_size': {
                    'total_shows': Movie.objects.filter(
                        movie_format__in=['IMAX', 'Standard']
                    ).count()
                }
            }

            message = []
            message.append("Price Analysis:")
            for day_type in ['weekday', 'weekend']:
                message.append(f"\n{day_type.title()}:")
                message.append(f"- IMAX: ${formatted_data[day_type]['IMAX']:.2f}")
                message.append(f"- Standard: ${formatted_data[day_type]['Standard']:.2f}")
                message.append(f"- Difference: ${abs(formatted_data[day_type]['difference']):.2f} more for IMAX")

            message.append(f"\nOverall: IMAX costs ${abs(formatted_data['overall_difference']):.2f} more than Standard")
            message.append(f"\nAnalysis based on {result['sample_size']['total_shows']} total shows.")

            result['message'] = '\n'.join(message)
            return result

        except Exception as e:
            logger.error(f"Error in price comparison analysis: {e}")
            return {
                'error': str(e),
                'message': 'An error occurred while analyzing price data'
            }

        except Exception as e:
            logger.error(f"Error in price comparison analysis: {e}")
            return {
                'error': str(e),
                'price_comparison': {}
            }
        self.comparison_patterns = [
            r'like|similar to|compared to|comparable to',
            r'other films|other movies|other shows',
            r'performed like|performing like',
            r'same genre|same category|same type',
            r'also watched|also liked|also enjoyed'
        ]

    def is_comparison_query(self, query: str) -> bool:
        """Detect if the query is asking for movie comparisons"""
        return (
            any(re.search(pattern, query.lower()) for pattern in self.comparison_patterns) and
            re.search(r'"([^"]+)"', query)  # Has a movie title in quotes
        )

    def find_similar_movies(self, reference_movie: Movie, limit: int = 5) -> List[Dict]:
        """Find movies similar to the reference movie based on multiple criteria"""
        if not reference_movie:
            return []

        # Get base queryset excluding the reference movie
        similar_movies = Movie.objects.exclude(id=reference_movie.id)

        # Calculate similarity scores based on multiple factors
        similar_movies = similar_movies.annotate(
            # Price similarity (closer to 1 means more similar)
            price_similarity=1 / (1 + Abs(F('price') - reference_movie.price)),
            
            # Seating similarity if available
            seating_similarity=Case(
                When(
                    Q(total_seats__isnull=False) & Q(reserved__isnull=False),
                    then=1 / (1 + Abs(
                        F('reserved') / F('total_seats') - 
                        reference_movie.reserved / reference_movie.total_seats
                    ))
                ),
                default=0,
                output_field=FloatField(),
            )
        ).annotate(
            # Combined similarity score
            similarity_score=(
                F('price_similarity') * 0.4 +  # 40% weight for price
                F('seating_similarity') * 0.3 + # 30% weight for seating patterns
                Case(  # 30% weight for same format
                    When(screen_format=reference_movie.screen_format, then=0.3),
                    default=0,
                    output_field=FloatField(),
                )
            )
        ).order_by('-similarity_score')[:limit]

        return [
            {
                'title': movie.title,
                'format': movie.screen_format,
                'price': movie.price,
                'similarity_score': movie.similarity_score
            }
            for movie in similar_movies
        ]

    def format_comparison_response(self, reference_title: str, similar_movies: List[Dict]) -> str:
        """Format comparison results into natural language"""
        if not similar_movies:
            return f'No similar movies found for "{reference_title}".'

        response_parts = [f'Here are movies that have performed similarly to "{reference_title}":']
        
        for movie in similar_movies:
            similarity = movie['similarity_score'] * 100
            response_parts.append(
                f"- {movie['title']} ({movie['format']} format, ${movie['price']:.2f}) - "
                f"{similarity:.0f}% similar in terms of pricing and performance"
            )

        return "\n".join(response_parts)

    def is_analytical_query(self, query: str) -> bool:
        """Detect if the query requires statistical analysis"""
        analytical_patterns = [
            # Price related patterns
            r'price|cost|pricing|ticket',
            r'expensive|cheap|affordable',
            r'imax.*standard|standard.*imax',
            r'format.*(?:price|cost)',
            r'weekday.*weekend|weekend.*weekday',
            
            # Seating related patterns
            r'seats?|seating|capacity',
            r'occupancy|availability|full|empty',
            r'reserved|booked|taken',
            r'crowded|busy|quiet',
            
            # Time related patterns
            r'showtime|screening|show',
            r'popular.*time|busy.*time|peak.*time',
            r'hour|schedule|timing',
            r'morning|afternoon|evening',
            
            # Statistical terms
            r'average|mean|median',
            r'total|sum|count',
            r'compare|comparison|versus|vs',
            r'statistics|statistical|stats',
            r'percentage|ratio|proportion',
            r'distribution|breakdown|pattern',
            r'analysis|analyze|study',
            r'how many|how much|what percentage',
            r'\d+%|\$\d+|\d+ dollars',
            r'most|least|highest|lowest',
            r'trend|pattern|tendency',
            
            # Theater specific
            r'theater.*performance',
            r'location.*analysis',
            r'venue.*comparison'
        ]
        
        # Add word boundaries to make matches more precise
        patterns_with_boundaries = [rf'\b{p}\b' for p in analytical_patterns]
        combined_pattern = '|'.join(patterns_with_boundaries)
        
        # Look for matches and require at least two different types of patterns
        matches = set(re.findall(combined_pattern, query.lower()))
        return len(matches) >= 2  # Require at least two different analytical terms

    def handle_price_analysis(self, format_type=None, day_type=None):
        """Handle price-related queries with specific filters"""
        query = Movie.objects.all()
        
        if format_type:
            query = query.filter(screen_format=format_type)
        if day_type:
            if day_type == 'weekend':
                query = query.annotate(
                    weekday=ExtractWeekDay('date_sh')
                ).filter(weekday__in=[1, 7])  # Sunday=1, Saturday=7
            elif day_type == 'weekday':
                query = query.annotate(
                    weekday=ExtractWeekDay('date_sh')
                ).filter(weekday__in=[2, 3, 4, 5, 6])

        results = query.aggregate(
            avg_price=Avg('price'),
            avg_child_price=Avg('child_price'),  # Fixed field name
            avg_senior_price=Avg('senior_price'),  # Fixed field name
            count=Count('id')
        )
        
        # Add sample size information
        results['sample_size'] = results.pop('count')
        return results

    def handle_seating_analysis(self, format_type=None):
        """Analyze seating patterns"""
        try:
            query = Movie.objects.all()
            
            if format_type:
                query = query.filter(screen_format=format_type)

            # Use ExpressionWrapper to ensure integer rounding in the database
            seating_data = query.aggregate(
                avg_total_seats=ExpressionWrapper(
                    Avg('total_seats'),
                    output_field=FloatField()
                ),
                avg_reserved=ExpressionWrapper(
                    Avg('reserved'),
                    output_field=FloatField()
                ),
                avg_available=ExpressionWrapper(
                    Avg('available'),
                    output_field=FloatField()
                )
            )
            
            return {
                'seating_analysis': {
                    'avg_total_seats': seating_data['avg_total_seats'] or 0.0,
                    'avg_reserved': seating_data['avg_reserved'] or 0.0,
                    'avg_available': seating_data['avg_available'] or 0.0
                }
            }
            
        except Exception as e:
            logger.error(f"Error in seating analysis: {e}")
            return {
                'error': str(e),
                'message': 'Error analyzing seating data',
                'seating_analysis': {
                    'avg_total_seats': 0,
                    'avg_reserved': 0,
                    'avg_available': 0
                }
            }

    def _handle_analytical_query(self, query: str) -> Dict[str, Any]:
        """Route analytical queries to specific handlers"""
        query = query.lower()
        
        # Showtime related queries
        if any(word in query for word in ['popular', 'busy', 'peak']):
            if 'time' in query or 'hour' in query or 'showtime' in query:
                result = self.handle_showtime_analysis()
                if result and not result.get('error'):
                    return {
                        'analysis': 'Showtime Distribution',
                        'data': result,
                        'summary': self._format_showtime_summary(result)
                    }
                return result
        
        # Seating related queries
        if 'seat' in query or 'capacity' in query or 'occupancy' in query:
            result = self.handle_seating_analysis()
            if result and not result.get('error'):
                return {
                    'analysis': 'Seating Analysis',
                    'data': result,
                    'summary': self._format_seating_summary(result)
                }
            return result
        
        # Price comparison queries
        if 'price' in query or 'cost' in query:
            if ('imax' in query and 'standard' in query) or ('format' in query and 'difference' in query):
                result = self.handle_price_comparison()
                if result and not result.get('error'):
                    return {
                        'analysis': 'Price Comparison',
                        'data': result,
                        'summary': self._format_price_comparison_summary(result)
                    }
                return result
            elif 'average' in query or 'avg' in query:
                return self.handle_price_analysis()
        
        return {
            'type': 'error',
            'error': 'Could not determine appropriate analysis for query. Please try rephrasing with more specific terms.',
            'message': 'Please try a more specific query focused on showtimes, seating, or pricing.',
            'supported_analyses': [
                'Popular showtimes and peak hours',
                'Seating capacity and occupancy',
                'IMAX vs Standard price comparison',
                'Average pricing analysis'
            ]
        }
        
    def _format_showtime_summary(self, data: Dict) -> str:
        """Format showtime analysis for human readability"""
        if not data or 'hourly_distribution' not in data:
            return 'No showtime data available'
            
        peak_slots = sorted(
            data['hourly_distribution'],
            key=lambda x: x['show_count'],
            reverse=True
        )[:3]
        
        summary = [
            f"Analysis of {data['total_shows']} total shows:",
            "\nPeak showtimes:",
        ]
        
        for slot in peak_slots:
            summary.append(
                f"- {slot['time']}: {slot['show_count']} shows "
                f"({slot['avg_occupancy']}% avg occupancy)"
            )
            
        if data.get('popular_theaters'):
            summary.append("\nMost active theaters:")
            for theater in data['popular_theaters'][:3]:
                summary.append(
                    f"- {theater['theater']}: Peak at {theater['peak_hour']} "
                    f"({theater['total_shows']} shows)"
                )
                
        return '\n'.join(summary)
        
    def _format_seating_summary(self, data: Dict) -> str:
        """Format seating analysis for human readability"""
        if not isinstance(data, dict):
            return 'No seating data available'
            
        total_seats = data.get('avg_total_seats', 0)
        reserved = data.get('avg_reserved', 0)
        available = data.get('avg_available', 0)
        
        if not total_seats:
            return 'No seating data available'
            
        occupancy = (reserved/total_seats*100) if total_seats > 0 else 0
            
        return (
            f"Seating Analysis:\n"
            f"- Average total seats: {int(round(total_seats))}\n"
            f"- Average reserved seats: {int(round(reserved))}\n"
            f"- Average available seats: {int(round(available))}\n"
            f"- Current occupancy rate: {occupancy:.1f}%"
        )
        
    def _format_price_comparison_summary(self, data: Dict) -> str:
        """Format price comparison for human readability"""
        if not data or 'price_comparison' not in data:
            return 'No price comparison data available'
            
        comp = data['price_comparison']
        summary = ["Price Comparison Analysis (IMAX vs Standard):"]
        
        for day_type in ['weekday', 'weekend']:
            if comp[day_type]['IMAX'] and comp[day_type]['Standard']:
                summary.append(f"\n{day_type.title()}:")
                summary.append(f"- IMAX: ${comp[day_type]['IMAX']:.2f}")
                summary.append(f"- Standard: ${comp[day_type]['Standard']:.2f}")
                summary.append(
                    f"- Price difference: ${abs(comp[day_type]['difference']):.2f} "
                    f"({'higher' if comp[day_type]['difference'] > 0 else 'lower'} "
                    f"for IMAX)"
                )
        
        if 'overall_difference' in comp:
            summary.append(
                f"\nOverall average price difference: "
                f"${abs(comp['overall_difference']):.2f} "
                f"({'higher' if comp['overall_difference'] > 0 else 'lower'} for IMAX)"
            )
            
        if 'sample_size' in data:
            summary.append(
                f"\nAnalysis based on {data['sample_size']['total_shows']} shows"
            )
            
        return '\n'.join(summary)

    def handle_showtime_analysis(self):
        """Analyze showtime patterns"""
        try:
            # Get showtime distribution
            showtime_data = Movie.objects.annotate(
                show_hour=ExtractHour('time_sh')
            ).values('show_hour').annotate(
                count=Count('id'),
                avg_occupancy=Avg(
                    ExpressionWrapper(
                        F('reserved') * 100.0 / F('total_seats'),
                        output_field=FloatField()
                    )
                )
            ).order_by('show_hour')

            # Get theater data
            theater_data = Movie.objects.values(
                'theater_name'
            ).annotate(
                total_shows=Count('id'),
                peak_hour=ExtractHour('time_sh')
            ).order_by('-total_shows')

            # Convert QuerySet to list of dictionaries with formatted data
            hourly_distribution = []
            for item in showtime_data:
                hour_str = f"{item['show_hour']:02d}:00"
                hourly_distribution.append({
                    'time': hour_str,
                    'show_count': item['count'],
                    'avg_occupancy': round(item['avg_occupancy'] if item['avg_occupancy'] else 0, 2)
                })
            
            # Format theater data
            popular_theaters = [{
                'theater': t['theater_name'],
                'peak_hour': f"{t['peak_hour']:02d}:00",
                'total_shows': t['total_shows']
            } for t in theater_data]
            
            total_shows = sum(item['show_count'] for item in hourly_distribution)
            response = {
                'showtime_analysis': {
                    'hourly_distribution': hourly_distribution,
                    'popular_theaters': popular_theaters,
                    'total_shows': total_shows
                }
            }
            
            return response

        except Exception as e:
            logger.error(f"Error in showtime analysis: {e}")
            return {
                'error': str(e),
                'message': 'Error analyzing showtime data',
                'showtime_analysis': {
                    'hourly_distribution': [],
                    'popular_theaters': [],
                    'total_shows': 0
                }
            }

    def format_analytical_response(self, data: Dict, query_type: str, format_type: str = None) -> str:
        """Format analytical data into natural language response"""
        if query_type == 'pricing':
            prices = data.get('pricing', {})
            response_parts = []
            
            if format_type:
                response_parts.append(f"For {format_type} format movies:")
            
            if prices.get('avg_price'):
                response_parts.append(f"- Average ticket price: ${prices['avg_price']:.2f}")
            if prices.get('avg_child_price'):
                response_parts.append(f"- Average child ticket price: ${prices['avg_child_price']:.2f}")
            if prices.get('avg_senior_price'):
                response_parts.append(f"- Average senior ticket price: ${prices['avg_senior_price']:.2f}")
            
            return "\n".join(response_parts)

        elif query_type == 'seating':
            seating = data.get('seating', {})
            response_parts = []
            
            if format_type:
                response_parts.append(f"Seating analysis for {format_type} format:")
            else:
                response_parts.append("Overall seating analysis:")
            
            if seating.get('avg_total_seats'):
                response_parts.append(f"- Average total seats: {seating['avg_total_seats']:.2f}")
            if seating.get('avg_reserved'):
                response_parts.append(f"- Average reserved seats: {seating['avg_reserved']:.2f}")
            if seating.get('avg_available'):
                response_parts.append(f"- Average available seats: {seating['avg_available']:.2f}")
            
            return "\n".join(response_parts)

        elif query_type == 'showtimes':
            showtimes = data.get('showtimes', [])
            if not showtimes:
                return "No showtime data available."
            
            response_parts = ["Showtime distribution:"]
            for time_slot in showtimes:
                response_parts.append(f"- {time_slot['hour']}:00 - {time_slot['count']} shows")
            
            return "\n".join(response_parts)
        
        return "No analytical data available."

    def process_query(self, query: str) -> Dict[str, Any]:
        """Process incoming query and route to appropriate handler"""
        try:
            # Handle empty query
            if not query or not query.strip():
                return {
                    'type': 'error',
                    'error': 'Empty query',
                    'message': 'Please provide a question.'
                }

            # Check for invalid characters early
            if re.search(r'[\$%\^&\*]', query):
                return {
                    'type': 'error',
                    'error': 'Invalid characters',
                    'message': 'Please avoid using special characters in your query.'
                }

            # First try RAG query
            if not any(pattern in query.lower() for pattern in [
                'price', 'cost', 'seating', 'capacity', 'showtime', 'schedule', 'IMAX',
                'occupied', 'available', 'compare', 'analysis', 'trend', 'pattern'
            ]):
                try:
                    rag_response = self.rag_service.query(query)
                    if rag_response and rag_response.get('answer'):
                        return {
                            'type': 'rag',
                            'message': rag_response['answer'],
                            'response': rag_response['answer'],
                            'sources': rag_response.get('sources', [])
                        }
                except Exception:
                    pass  # Fall through to analytical query if RAG fails

            # Handle as analytical query
            result = self._handle_analytical_query(query)
            
            # Add type if missing
            if 'type' not in result:
                result['type'] = 'error' if result.get('error') else 'analytical'
            
            # Ensure message field exists
            if 'message' not in result:
                if result.get('error'):
                    result['message'] = 'Please try rephrasing your question with more specific terms.'
                else:
                    result['message'] = result.get('summary', 'Analysis complete')
                
            return result
            
        except Exception as e:
            logger.error(f"Error in query processing: {e}")
            return {
                'type': 'error',
                'error': str(e),
                'message': 'An unexpected error occurred. Please try rephrasing your question.'
            }
            
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return {
                'type': 'error',
                'error': str(e),
                'message': 'An error occurred while processing your query.'
            }
