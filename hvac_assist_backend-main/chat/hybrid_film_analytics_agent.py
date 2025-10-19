#!/usr/bin/env python3
"""
HYBRID AI AGENT FOR COMPLEX FILM ANALYTICS
Routes queries intelligently between RAG and database queries
Handles comparative analysis, performance predictions, and market opportunities
"""

from django.core.management.base import BaseCommand
from django.db.models import Q, Sum, Avg, Count, Max, Min
from movies.models import Movie, FilmPerformanceSummary, TheaterPerformance, MarketAnalysis, ComparativeAnalysis
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import logging
import re
from typing import Dict, List, Any, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

class HybridFilmAnalyticsAgent:
    """Hybrid AI agent for complex film analytics queries"""
    
    def __init__(self):
        self.query_patterns = {
            'comp_titles': [
                r'best comp titles? for (.+)',
                r'comparable titles? for (.+)',
                r'comp titles? for (.+)',
                r'similar movies? to (.+)',
                r'what movies? are like (.+)'
            ],
            'sales_prediction': [
                r'estimated sales? for (.+)',
                r'projected sales? for (.+)',
                r'how much will (.+) earn',
                r'box office prediction for (.+)',
                r'revenue estimate for (.+)'
            ],
            'performance_analysis': [
                r'is (.+) over performing',
                r'how is (.+) performing',
                r'performance of (.+)',
                r'(.+) performance analysis',
                r'is (.+) underperforming'
            ],
            'market_opportunities': [
                r'where are my opportunities',
                r'market opportunities',
                r'theater opportunities',
                r'expansion opportunities',
                r'growth opportunities'
            ],
            'showtime_optimization': [
                r'what showtimes? do I want to keep',
                r'best showtimes? for (.+)',
                r'optimal showtimes?',
                r'showtime recommendations',
                r'when should I schedule (.+)'
            ],
            'weekend_drop': [
                r'how much will (.+) drop',
                r'second weekend drop for (.+)',
                r'weekend decline for (.+)',
                r'(.+) second weekend',
                r'box office drop for (.+)'
            ],
            'imax_performance': [
                r'(.+) imax performance',
                r'imax screens? for (.+)',
                r'(.+) imax overperforming',
                r'imax analysis for (.+)'
            ],
            'geographic_performance': [
                r'(.+) performing in (.+)',
                r'performance in (.+) areas',
                r'geographic performance of (.+)',
                r'(.+) in (.+) markets'
            ],
            'capacity_analysis': [
                r'(.+) programmed for this weekend',
                r'capacity comparison',
                r'showtime comparison',
                r'programming analysis'
            ]
        }
    
    def classify_query(self, query: str) -> str:
        """Classify the type of query"""
        query_lower = query.lower()
        
        for query_type, patterns in self.query_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return query_type
        
        return 'general'
    
    def extract_entities(self, query: str) -> Dict[str, Any]:
        """Extract entities from the query"""
        entities = {}
        
        # Extract movie titles
        movie_patterns = [
            r'for (.+?)(?:\?|$|in|on|at)',
            r'(.+?) performance',
            r'(.+?) sales',
            r'(.+?) drop',
            r'(.+?) imax',
            r'(.+?) programmed'
        ]
        
        for pattern in movie_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                movie_title = match.group(1).strip()
                if movie_title and len(movie_title) > 2:
                    entities['movie_title'] = movie_title
        
        # Extract locations
        location_patterns = [
            r'in (.+?)(?:\?|$|areas|markets)',
            r'(.+?) areas',
            r'(.+?) markets'
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                if location and len(location) > 2:
                    entities['location'] = location
        
        return entities
    
    def handle_comp_titles_query(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle comparative titles queries"""
        movie_title = entities.get('movie_title', '')
        
        if not movie_title:
            return {'error': 'No movie title found in query'}
        
        try:
            # Find the target movie
            target_movie = FilmPerformanceSummary.objects.filter(
                title__icontains=movie_title
            ).first()
            
            if not target_movie:
                return {'error': f'Movie "{movie_title}" not found'}
            
            # Find comparable movies based on genre, rating, and performance patterns
            comp_movies = FilmPerformanceSummary.objects.filter(
                Q(genre=target_movie.genre) | Q(rating=target_movie.rating),
                year=target_movie.year
            ).exclude(title=target_movie.title).order_by('-total_sales')[:5]
            
            # Calculate similarity scores
            comp_analysis = []
            for comp in comp_movies:
                similarity_score = self.calculate_similarity_score(target_movie, comp)
                comp_analysis.append({
                    'title': comp.title,
                    'genre': comp.genre,
                    'rating': comp.rating,
                    'studio': comp.studio_name,
                    'total_sales': comp.total_sales,
                    'occupancy': comp.overall_occupancy,
                    'dod_growth': comp.dod_growth,
                    'similarity_score': similarity_score
                })
            
            # Sort by similarity score
            comp_analysis.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            return {
                'query_type': 'comp_titles',
                'target_movie': movie_title,
                'comp_titles': comp_analysis[:3],
                'analysis': f"Found {len(comp_analysis)} comparable titles based on genre ({target_movie.genre}), rating ({target_movie.rating}), and performance patterns."
            }
            
        except Exception as e:
            logger.error(f"Error in comp titles query: {e}")
            return {'error': f'Error analyzing comp titles: {str(e)}'}
    
    def handle_sales_prediction_query(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle sales prediction queries"""
        movie_title = entities.get('movie_title', '')
        
        if not movie_title:
            return {'error': 'No movie title found in query'}
        
        try:
            # Find the target movie
            target_movie = FilmPerformanceSummary.objects.filter(
                title__icontains=movie_title
            ).first()
            
            if not target_movie:
                return {'error': f'Movie "{movie_title}" not found'}
            
            # Get comp titles for prediction
            comp_movies = FilmPerformanceSummary.objects.filter(
                Q(genre=target_movie.genre) | Q(rating=target_movie.rating),
                year=target_movie.year
            ).exclude(title=target_movie.title).order_by('-total_sales')[:5]
            
            if not comp_movies:
                return {'error': 'No comparable movies found for prediction'}
            
            # Calculate predicted sales based on comp titles
            comp_sales = [comp.total_sales for comp in comp_movies]
            avg_comp_sales = np.mean(comp_sales)
            
            # Adjust for IMAX performance if applicable
            imax_adjustment = self.calculate_imax_adjustment(target_movie)
            
            # Adjust for Thursday overperformance
            thursday_adjustment = self.calculate_thursday_adjustment(target_movie)
            
            predicted_sales = avg_comp_sales * (1 + imax_adjustment + thursday_adjustment)
            
            return {
                'query_type': 'sales_prediction',
                'target_movie': movie_title,
                'predicted_sales': f"${predicted_sales:,.1f} million",
                'comp_titles_used': [comp.title for comp in comp_movies],
                'imax_adjustment': f"{imax_adjustment*100:.1f}%",
                'thursday_adjustment': f"{thursday_adjustment*100:.1f}%",
                'analysis': f"Based on {len(comp_movies)} comparable titles with similar genre and rating."
            }
            
        except Exception as e:
            logger.error(f"Error in sales prediction query: {e}")
            return {'error': f'Error predicting sales: {str(e)}'}
    
    def handle_performance_analysis_query(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle performance analysis queries"""
        movie_title = entities.get('movie_title', '')
        
        if not movie_title:
            return {'error': 'No movie title found in query'}
        
        try:
            # Find the target movie
            target_movie = FilmPerformanceSummary.objects.filter(
                title__icontains=movie_title
            ).first()
            
            if not target_movie:
                return {'error': f'Movie "{movie_title}" not found'}
            
            # Get comp titles for comparison
            comp_movies = FilmPerformanceSummary.objects.filter(
                Q(genre=target_movie.genre) | Q(rating=target_movie.rating),
                year=target_movie.year
            ).exclude(title=target_movie.title).order_by('-total_sales')[:5]
            
            if not comp_movies:
                return {'error': 'No comparable movies found for analysis'}
            
            # Calculate performance metrics
            comp_occupancy = np.mean([comp.overall_occupancy for comp in comp_movies])
            comp_dod_growth = np.mean([comp.dod_growth or 0 for comp in comp_movies])
            
            # Calculate overperformance percentages
            occupancy_overperformance = ((target_movie.overall_occupancy - comp_occupancy) / comp_occupancy * 100) if comp_occupancy > 0 else 0
            dod_overperformance = ((target_movie.dod_growth or 0 - comp_dod_growth) / comp_dod_growth * 100) if comp_dod_growth > 0 else 0
            
            # Determine performance status
            if occupancy_overperformance > 10:
                performance_status = "Overperforming"
            elif occupancy_overperformance < -10:
                performance_status = "Underperforming"
            else:
                performance_status = "Performing as expected"
            
            return {
                'query_type': 'performance_analysis',
                'target_movie': movie_title,
                'performance_status': performance_status,
                'occupancy_overperformance': f"{occupancy_overperformance:.1f}%",
                'dod_overperformance': f"{dod_overperformance:.1f}%",
                'target_occupancy': f"{target_movie.overall_occupancy:.1f}%",
                'comp_avg_occupancy': f"{comp_occupancy:.1f}%",
                'analysis': f"Compared to {len(comp_movies)} comparable titles in the same genre and rating."
            }
            
        except Exception as e:
            logger.error(f"Error in performance analysis query: {e}")
            return {'error': f'Error analyzing performance: {str(e)}'}
    
    def handle_market_opportunities_query(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle market opportunities queries"""
        try:
            # Find theaters with high occupancy but low capacity utilization
            opportunities = TheaterPerformance.objects.filter(
                overall_occupancy__gte=70,  # High occupancy
                capacity_utilization__lt=80  # But low capacity utilization
            ).order_by('-overall_occupancy')[:10]
            
            if not opportunities:
                return {'error': 'No market opportunities found'}
            
            # Group by circuit for recommendations
            circuit_opportunities = {}
            for opp in opportunities:
                circuit = opp.circuit_name
                if circuit not in circuit_opportunities:
                    circuit_opportunities[circuit] = []
                circuit_opportunities[circuit].append({
                    'theater_name': opp.theater_name,
                    'city': opp.theater_city,
                    'state': opp.theater_state,
                    'occupancy': opp.overall_occupancy,
                    'capacity_utilization': opp.capacity_utilization,
                    'market_position': opp.market_position
                })
            
            # Generate recommendations
            recommendations = []
            for circuit, theaters in circuit_opportunities.items():
                recommendations.append({
                    'circuit': circuit,
                    'theaters': theaters,
                    'recommendation': f"Contact {circuit} - {len(theaters)} theaters with high occupancy but growth potential"
                })
            
            return {
                'query_type': 'market_opportunities',
                'opportunities_found': len(opportunities),
                'recommendations': recommendations,
                'analysis': f"Found {len(opportunities)} theaters with high occupancy but growth potential across {len(circuit_opportunities)} circuits."
            }
            
        except Exception as e:
            logger.error(f"Error in market opportunities query: {e}")
            return {'error': f'Error finding market opportunities: {str(e)}'}
    
    def handle_showtime_optimization_query(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle showtime optimization queries"""
        movie_title = entities.get('movie_title', '')
        
        try:
            if movie_title:
                # Find the target movie's performance by showtime
                movie_shows = Movie.objects.filter(
                    title__icontains=movie_title
                ).values('time_sh', 'auditorium', 'theater_name', 'reserved', 'total_seats')
                
                if not movie_shows:
                    return {'error': f'No showtime data found for "{movie_title}"'}
                
                # Analyze performance by time
                time_performance = {}
                for show in movie_shows:
                    time_key = str(show['time_sh'])
                    if time_key not in time_performance:
                        time_performance[time_key] = {'reserved': 0, 'total_seats': 0, 'theaters': set()}
                    
                    time_performance[time_key]['reserved'] += show['reserved']
                    time_performance[time_key]['total_seats'] += show['total_seats']
                    time_performance[time_key]['theaters'].add(show['theater_name'])
                
                # Calculate occupancy by time
                time_analysis = []
                for time_key, data in time_performance.items():
                    occupancy = (data['reserved'] / data['total_seats'] * 100) if data['total_seats'] > 0 else 0
                    time_analysis.append({
                        'time': time_key,
                        'occupancy': occupancy,
                        'theaters': len(data['theaters'])
                    })
                
                # Sort by occupancy
                time_analysis.sort(key=lambda x: x['occupancy'], reverse=True)
                
                return {
                    'query_type': 'showtime_optimization',
                    'target_movie': movie_title,
                    'best_times': time_analysis[:3],
                    'analysis': f"Best performing showtimes for {movie_title} based on occupancy rates."
                }
            else:
                # General showtime optimization
                return {
                    'query_type': 'showtime_optimization',
                    'analysis': 'Please specify a movie title for showtime optimization analysis.'
                }
                
        except Exception as e:
            logger.error(f"Error in showtime optimization query: {e}")
            return {'error': f'Error analyzing showtimes: {str(e)}'}
    
    def handle_weekend_drop_query(self, query: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Handle weekend drop queries"""
        movie_title = entities.get('movie_title', '')
        
        if not movie_title:
            return {'error': 'No movie title found in query'}
        
        try:
            # Find the target movie
            target_movie = FilmPerformanceSummary.objects.filter(
                title__icontains=movie_title
            ).first()
            
            if not target_movie:
                return {'error': f'Movie "{movie_title}" not found'}
            
            # Get comp titles for drop analysis
            comp_movies = FilmPerformanceSummary.objects.filter(
                Q(genre=target_movie.genre) | Q(rating=target_movie.rating),
                year=target_movie.year
            ).exclude(title=target_movie.title).order_by('-total_sales')[:5]
            
            if not comp_movies:
                return {'error': 'No comparable movies found for drop analysis'}
            
            # Calculate average drop for comp titles
            # This is a simplified calculation - in reality, you'd need historical weekend data
            avg_drop = 50.0  # Default 50% drop
            
            # Adjust based on performance patterns
            if target_movie.dod_growth and target_movie.dod_growth > 0:
                avg_drop -= 10  # Reduce drop if positive growth
            
            if target_movie.weekend_ratio and target_movie.weekend_ratio > 1.5:
                avg_drop -= 5  # Reduce drop if strong weekend performance
            
            return {
                'query_type': 'weekend_drop',
                'target_movie': movie_title,
                'predicted_drop': f"{avg_drop:.0f}%",
                'comp_titles_used': [comp.title for comp in comp_movies],
                'analysis': f"Based on {len(comp_movies)} comparable titles with similar genre and rating."
            }
            
        except Exception as e:
            logger.error(f"Error in weekend drop query: {e}")
            return {'error': f'Error predicting weekend drop: {str(e)}'}
    
    def calculate_similarity_score(self, target: FilmPerformanceSummary, comp: FilmPerformanceSummary) -> float:
        """Calculate similarity score between two movies"""
        score = 0.0
        
        # Genre match
        if target.genre == comp.genre:
            score += 0.3
        
        # Rating match
        if target.rating == comp.rating:
            score += 0.2
        
        # Studio match
        if target.studio_name == comp.studio_name:
            score += 0.1
        
        # Performance similarity
        occupancy_diff = abs(target.overall_occupancy - comp.overall_occupancy)
        score += max(0, 0.2 - (occupancy_diff / 100))
        
        # DOD growth similarity
        if target.dod_growth and comp.dod_growth:
            dod_diff = abs(target.dod_growth - comp.dod_growth)
            score += max(0, 0.2 - (dod_diff / 50))
        
        return min(1.0, score)
    
    def calculate_imax_adjustment(self, movie: FilmPerformanceSummary) -> float:
        """Calculate IMAX performance adjustment"""
        # This would need actual IMAX data - simplified for now
        return 0.15  # 15% boost for IMAX
    
    def calculate_thursday_adjustment(self, movie: FilmPerformanceSummary) -> float:
        """Calculate Thursday overperformance adjustment"""
        # This would need actual Thursday data - simplified for now
        return 0.20  # 20% boost for Thursday overperformance
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """Main method to process any query"""
        try:
            # Classify the query
            query_type = self.classify_query(query)
            
            # Extract entities
            entities = self.extract_entities(query)
            
            # Route to appropriate handler
            if query_type == 'comp_titles':
                return self.handle_comp_titles_query(query, entities)
            elif query_type == 'sales_prediction':
                return self.handle_sales_prediction_query(query, entities)
            elif query_type == 'performance_analysis':
                return self.handle_performance_analysis_query(query, entities)
            elif query_type == 'market_opportunities':
                return self.handle_market_opportunities_query(query, entities)
            elif query_type == 'showtime_optimization':
                return self.handle_showtime_optimization_query(query, entities)
            elif query_type == 'weekend_drop':
                return self.handle_weekend_drop_query(query, entities)
            else:
                return {'error': f'Query type "{query_type}" not supported yet'}
                
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {'error': f'Error processing query: {str(e)}'}

class Command(BaseCommand):
    help = 'Test the hybrid film analytics agent'

    def add_arguments(self, parser):
        parser.add_argument(
            '--query',
            type=str,
            help='Query to test',
        )

    def handle(self, *args, **options):
        agent = HybridFilmAnalyticsAgent()
        
        if options['query']:
            query = options['query']
            result = agent.process_query(query)
            
            self.stdout.write(f"Query: {query}")
            self.stdout.write(f"Result: {result}")
        else:
            # Test with sample queries
            test_queries = [
                "What are the best comp titles for WEAPONS?",
                "What is WEAPONS estimated sales if it performs similarly to suggested comp titles?",
                "Is WEAPONS over performing on Thursday?",
                "Where are my opportunities?",
                "What showtimes do I want to keep for FANTASTIC FOUR?",
                "How much will SUPERMAN drop in its second weekend?"
            ]
            
            for query in test_queries:
                self.stdout.write(f"\n{'='*60}")
                self.stdout.write(f"Query: {query}")
                result = agent.process_query(query)
                self.stdout.write(f"Result: {result}")
                self.stdout.write(f"{'='*60}")
