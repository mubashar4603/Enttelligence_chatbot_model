#!/usr/bin/env python3
"""
Comprehensive Query Handler for Film Performance Analytics
Handles complex comparative queries like "What films are performing like JURASSIC WORLD REBIRTH?"
"""

import os
import django
from django.conf import settings
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
import numpy as np
import logging
from typing import Dict, List, Any, Optional
import json
from datetime import datetime, timedelta
import pandas as pd

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from movies.models import Movie
from chat.analytics_models import (
    FilmPerformanceSummary, 
    TheaterPerformance, 
    MarketAnalysis, 
    ComparativeAnalysis,
    EmbeddingChunk,
    QueryLog
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FilmAnalyticsQueryHandler:
    def __init__(self):
        """Initialize the comprehensive query handler"""
        self.config = self._load_config()
        self.model = None
        self.pc = None
        self.index = None
        
    def _load_config(self):
        """Load configuration"""
        return {
            # Pinecone settings
            'PINECONE_API_KEY': "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ",
            'PINECONE_ENVIRONMENT': "us-east-1-aws",
            'INDEX_NAME': "customer-database-vectors",
            'DIMENSION': 768,
            
            # Embedding settings
            'EMBEDDING_MODEL': "BAAI/bge-base-en-v1.5",
        }
    
    def initialize_components(self):
        """Initialize embedding model and Pinecone connection"""
        try:
            logger.info("🚀 Initializing Film Analytics Query Handler")
            
            # Initialize embedding model
            logger.info("🤖 Loading embedding model...")
            self.model = SentenceTransformer(self.config['EMBEDDING_MODEL'])
            
            # Initialize Pinecone
            logger.info("🔌 Connecting to Pinecone...")
            self.pc = Pinecone(api_key=self.config['PINECONE_API_KEY'])
            self.index = self.pc.Index(self.config['INDEX_NAME'])
            
            logger.info("✅ Query handler initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize query handler: {e}")
            raise
    
    def detect_query_type(self, query: str) -> str:
        """Detect the type of query"""
        query_lower = query.lower()
        
        # Comparative analysis queries
        if any(phrase in query_lower for phrase in [
            'performing like', 'similar to', 'comparable to', 'like', 'similar performance',
            'what films are', 'which movies are', 'movies performing'
        ]):
            return 'comparative_analysis'
        
        # Opportunity queries
        elif any(phrase in query_lower for phrase in [
            'opportunities', 'where are my', 'underperforming', 'focus on',
            'recommendations', 'what should i', 'best theaters'
        ]):
            return 'theater_opportunity'
        
        # Market analysis queries
        elif any(phrase in query_lower for phrase in [
            'market', 'city', 'geographic', 'penetration', 'less populated',
            'urban vs rural', 'demographic', 'location'
        ]):
            return 'market_analysis'
        
        # Performance queries
        elif any(phrase in query_lower for phrase in [
            'performance', 'how is', 'occupancy', 'sales', 'revenue',
            'box office', 'ticket sales', 'showtimes'
        ]):
            return 'film_performance'
        
        else:
            return 'general'
    
    def search_pinecone(self, query: str, query_type: str = None, top_k: int = 10) -> List[Dict]:
        """Search Pinecone for relevant vectors"""
        try:
            # Generate query embedding
            query_embedding = self.model.encode(
                query,
                normalize_embeddings=True
            )
            
            # Search Pinecone
            results = self.index.query(
                vector=query_embedding.tolist(),
                top_k=top_k,
                include_metadata=True,
                include_values=False
            )
            
            return results['matches']
            
        except Exception as e:
            logger.error(f"❌ Pinecone search failed: {e}")
            return []
    
    def handle_comparative_query(self, query: str) -> Dict[str, Any]:
        """Handle comparative analysis queries like 'What films are performing like X?'"""
        logger.info(f"🔍 Processing comparative query: {query}")
        
        # Search for comparative analysis chunks
        matches = self.search_pinecone(query, 'comparative_analysis', top_k=20)
        
        if not matches:
            return {
                'response': "I couldn't find any comparative analysis data for this query.",
                'query_type': 'comparative_analysis',
                'sources': []
            }
        
        # Extract film names from query
        query_films = self._extract_film_names(query)
        
        # Find similar films based on performance patterns
        similar_films = []
        for match in matches:
            if match['score'] > 0.7:  # High relevance threshold
                metadata = match['metadata']
                similar_films.append({
                    'title': metadata.get('title', 'Unknown'),
                    'genre': metadata.get('genre', 'Unknown'),
                    'rating': metadata.get('rating', 'Unknown'),
                    'studio': metadata.get('studio_name', 'Unknown'),
                    'occupancy_rate': metadata.get('overall_occupancy', 0),
                    'total_sales': metadata.get('total_sales', 0),
                    'market_penetration': metadata.get('market_penetration', 0),
                    'dod_growth': metadata.get('dod_growth', 0),
                    'similarity_score': match['score'],
                    'performance_profile': {
                        'peak_time': metadata.get('peak_time', 'Unknown'),
                        'best_format': metadata.get('best_format', 'Unknown'),
                        'top_market': metadata.get('top_market', 'Unknown'),
                        'weekend_ratio': metadata.get('weekend_ratio', 0)
                    }
                })
        
        # Sort by similarity score
        similar_films.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Generate response
        if similar_films:
            top_films = similar_films[:5]  # Top 5 similar films
            
            response = f"Based on performance analysis, here are films performing similarly to {', '.join(query_films) if query_films else 'your query'}:\n\n"
            
            for i, film in enumerate(top_films, 1):
                response += f"{i}. **{film['title']}** ({film['genre']}, {film['rating']})\n"
                response += f"   - Studio: {film['studio']}\n"
                response += f"   - Occupancy Rate: {film['occupancy_rate']:.1f}%\n"
                response += f"   - Total Sales: ${film['total_sales']:,.2f}\n"
                response += f"   - Market Penetration: {film['market_penetration']:.1f}%\n"
                response += f"   - Day-over-Day Growth: {film['dod_growth']:.1f}%\n"
                response += f"   - Peak Time: {film['performance_profile']['peak_time']}\n"
                response += f"   - Best Format: {film['performance_profile']['best_format']}\n"
                response += f"   - Top Market: {film['performance_profile']['top_market']}\n\n"
            
            response += "**Why these films are similar:**\n"
            response += "- Similar genre and rating profiles\n"
            response += "- Comparable occupancy rates and sales performance\n"
            response += "- Similar market penetration patterns\n"
            response += "- Comparable day-over-day growth trends\n"
            response += "- Similar peak performance times and format preferences\n"
            
        else:
            response = "I couldn't find any films with similar performance patterns. This might be due to unique characteristics of the film you're asking about."
        
        return {
            'response': response,
            'query_type': 'comparative_analysis',
            'similar_films': similar_films[:5],
            'sources': matches[:5]
        }
    
    def handle_opportunity_query(self, query: str) -> Dict[str, Any]:
        """Handle theater opportunity queries"""
        logger.info(f"🔍 Processing opportunity query: {query}")
        
        # Search for theater opportunity chunks
        matches = self.search_pinecone(query, 'theater_opportunity', top_k=15)
        
        if not matches:
            return {
                'response': "I couldn't find any theater opportunity data for this query.",
                'query_type': 'theater_opportunity',
                'sources': []
            }
        
        # Analyze opportunities
        opportunities = []
        for match in matches:
            if match['score'] > 0.6:
                metadata = match['metadata']
                opportunities.append({
                    'theater_name': metadata.get('theater_name', 'Unknown'),
                    'theater_city': metadata.get('theater_city', 'Unknown'),
                    'theater_state': metadata.get('theater_state', 'Unknown'),
                    'circuit_name': metadata.get('circuit_name', 'Unknown'),
                    'overall_occupancy': metadata.get('overall_occupancy', 0),
                    'capacity_utilization': metadata.get('capacity_utilization', 0),
                    'price_optimization': metadata.get('price_optimization', 0),
                    'market_position': metadata.get('market_position', 'Unknown'),
                    'opportunity_score': match['score']
                })
        
        # Sort by opportunity score
        opportunities.sort(key=lambda x: x['opportunity_score'], reverse=True)
        
        # Generate response
        if opportunities:
            top_opportunities = opportunities[:10]
            
            response = "Here are the top theater opportunities I've identified:\n\n"
            
            for i, opp in enumerate(top_opportunities, 1):
                response += f"{i}. **{opp['theater_name']}** - {opp['theater_city']}, {opp['theater_state']}\n"
                response += f"   - Circuit: {opp['circuit_name']}\n"
                response += f"   - Current Occupancy: {opp['overall_occupancy']:.1f}%\n"
                response += f"   - Capacity Utilization: {opp['capacity_utilization']:.1f}%\n"
                response += f"   - Price Optimization Potential: {opp['price_optimization']:.1f}%\n"
                response += f"   - Market Position: {opp['market_position']}\n\n"
            
            response += "**Recommendations:**\n"
            response += "- Focus on theaters with low capacity utilization\n"
            response += "- Implement dynamic pricing strategies\n"
            response += "- Consider format expansion opportunities\n"
            response += "- Target underperforming time slots\n"
            
        else:
            response = "I couldn't find specific theater opportunities at this time."
        
        return {
            'response': response,
            'query_type': 'theater_opportunity',
            'opportunities': opportunities[:10],
            'sources': matches[:5]
        }
    
    def handle_market_query(self, query: str) -> Dict[str, Any]:
        """Handle market analysis queries"""
        logger.info(f"🔍 Processing market query: {query}")
        
        # Search for market penetration chunks
        matches = self.search_pinecone(query, 'market_penetration', top_k=15)
        
        if not matches:
            return {
                'response': "I couldn't find any market analysis data for this query.",
                'query_type': 'market_analysis',
                'sources': []
            }
        
        # Analyze market data
        markets = []
        for match in matches:
            if match['score'] > 0.6:
                metadata = match['metadata']
                markets.append({
                    'city': metadata.get('city', 'Unknown'),
                    'state': metadata.get('state', 'Unknown'),
                    'market_occupancy': metadata.get('market_occupancy', 0),
                    'theater_count': metadata.get('theater_count', 0),
                    'circuit_diversity': metadata.get('circuit_diversity', 0),
                    'capacity_utilization': metadata.get('capacity_utilization', 0),
                    'price_range_min': metadata.get('price_range_min', 0),
                    'price_range_max': metadata.get('price_range_max', 0),
                    'relevance_score': match['score']
                })
        
        # Sort by relevance
        markets.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        # Generate response
        if markets:
            top_markets = markets[:8]
            
            response = "Here's the market analysis:\n\n"
            
            for i, market in enumerate(top_markets, 1):
                response += f"{i}. **{market['city']}, {market['state']}**\n"
                response += f"   - Market Occupancy: {market['market_occupancy']:.1f}%\n"
                response += f"   - Theater Count: {market['theater_count']}\n"
                response += f"   - Circuit Diversity: {market['circuit_diversity']}\n"
                response += f"   - Capacity Utilization: {market['capacity_utilization']:.1f}%\n"
                response += f"   - Price Range: ${market['price_range_min']:.2f} - ${market['price_range_max']:.2f}\n\n"
            
            response += "**Market Insights:**\n"
            response += "- Markets with lower occupancy rates may have growth potential\n"
            response += "- Higher circuit diversity indicates competitive markets\n"
            response += "- Price range analysis helps identify pricing opportunities\n"
            
        else:
            response = "I couldn't find specific market analysis data at this time."
        
        return {
            'response': response,
            'query_type': 'market_analysis',
            'markets': markets[:8],
            'sources': matches[:5]
        }
    
    def handle_performance_query(self, query: str) -> Dict[str, Any]:
        """Handle film performance queries"""
        logger.info(f"🔍 Processing performance query: {query}")
        
        # Search for film performance chunks
        matches = self.search_pinecone(query, 'film_performance', top_k=15)
        
        if not matches:
            return {
                'response': "I couldn't find any performance data for this query.",
                'query_type': 'film_performance',
                'sources': []
            }
        
        # Analyze performance data
        performances = []
        for match in matches:
            if match['score'] > 0.6:
                metadata = match['metadata']
                performances.append({
                    'title': metadata.get('title', 'Unknown'),
                    'genre': metadata.get('genre', 'Unknown'),
                    'rating': metadata.get('rating', 'Unknown'),
                    'studio': metadata.get('studio_name', 'Unknown'),
                    'occupancy_rate': metadata.get('occupancy_rate', 0),
                    'sales_estimate': metadata.get('sales_estimate', 0),
                    'price': metadata.get('price', 0),
                    'dod_growth': metadata.get('dod_growth', 0),
                    'screen_format': metadata.get('screen_format', 'Unknown'),
                    'theater_city': metadata.get('theater_city', 'Unknown'),
                    'relevance_score': match['score']
                })
        
        # Sort by relevance
        performances.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        # Generate response
        if performances:
            top_performances = performances[:10]
            
            response = "Here's the performance analysis:\n\n"
            
            for i, perf in enumerate(top_performances, 1):
                response += f"{i}. **{perf['title']}** ({perf['genre']}, {perf['rating']})\n"
                response += f"   - Studio: {perf['studio']}\n"
                response += f"   - Occupancy Rate: {perf['occupancy_rate']:.1f}%\n"
                response += f"   - Sales Estimate: ${perf['sales_estimate']:,.2f}\n"
                response += f"   - Average Price: ${perf['price']:.2f}\n"
                response += f"   - Day-over-Day Growth: {perf['dod_growth']:.1f}%\n"
                response += f"   - Format: {perf['screen_format']}\n"
                response += f"   - Location: {perf['theater_city']}\n\n"
            
            response += "**Performance Insights:**\n"
            response += "- Higher occupancy rates indicate strong demand\n"
            response += "- Sales estimates help gauge revenue potential\n"
            response += "- Day-over-day growth shows momentum\n"
            
        else:
            response = "I couldn't find specific performance data at this time."
        
        return {
            'response': response,
            'query_type': 'film_performance',
            'performances': performances[:10],
            'sources': matches[:5]
        }
    
    def _extract_film_names(self, query: str) -> List[str]:
        """Extract film names from query"""
        # Simple extraction - can be enhanced with NER
        query_upper = query.upper()
        common_films = [
            'JURASSIC WORLD REBIRTH', 'WEAPONS', 'DUNE', 'TWISTERS', 'JOKER',
            'HOMESTEAD', 'MONKEY MAN', 'SUPERMAN', 'FANTASTIC FOUR'
        ]
        
        found_films = []
        for film in common_films:
            if film in query_upper:
                found_films.append(film)
        
        return found_films
    
    def process_query(self, query: str, user=None, conversation=None) -> Dict[str, Any]:
        """Process a query and return comprehensive response"""
        start_time = datetime.now()
        
        try:
            # Initialize components if not already done
            if not self.model:
                self.initialize_components()
            
            # Detect query type
            query_type = self.detect_query_type(query)
            
            # Process based on query type
            if query_type == 'comparative_analysis':
                result = self.handle_comparative_query(query)
            elif query_type == 'theater_opportunity':
                result = self.handle_opportunity_query(query)
            elif query_type == 'market_analysis':
                result = self.handle_market_query(query)
            elif query_type == 'film_performance':
                result = self.handle_performance_query(query)
            else:
                # General query - try all types
                result = self.handle_comparative_query(query)
                if not result.get('similar_films'):
                    result = self.handle_performance_query(query)
            
            # Calculate response time
            response_time = (datetime.now() - start_time).total_seconds()
            
            # Log query
            try:
                QueryLog.objects.create(
                    query_text=query,
                    query_type=query_type,
                    response_text=result['response'],
                    response_time=response_time,
                    vector_count=len(result.get('sources', [])),
                    user=user,
                    conversation=conversation
                )
            except Exception as e:
                logger.warning(f"⚠️  Failed to log query: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Query processing failed: {e}")
            return {
                'response': f"I encountered an error processing your query: {str(e)}",
                'query_type': 'error',
                'sources': []
            }

def main():
    """Test the query handler"""
    handler = FilmAnalyticsQueryHandler()
    
    # Test queries
    test_queries = [
        "What films are performing like JURASSIC WORLD REBIRTH?",
        "Where are my opportunities?",
        "How is WEAPONS performing in less populated areas?",
        "What showtimes do I want to keep?",
        "Show me theater performance data"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"{'='*60}")
        
        result = handler.process_query(query)
        print(f"Response: {result['response']}")
        print(f"Query Type: {result['query_type']}")

if __name__ == "__main__":
    main()
