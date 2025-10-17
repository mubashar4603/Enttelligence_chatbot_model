#!/usr/bin/env python3
"""
Simple Pinecone-Only Query Handler
No FAISS needed - Uses only Pinecone for 7.4M dataset
"""

import os
import django
from django.conf import settings
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
import numpy as np
import logging
from typing import Dict, List, Any
import json
from datetime import datetime

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimplePineconeQueryHandler:
    def __init__(self):
        """Initialize the simple Pinecone-only query handler"""
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
            logger.info("🚀 Initializing Simple Pinecone Query Handler")
            
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
    
    def search_pinecone(self, query: str, top_k: int = 10) -> List[Dict]:
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
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """Process a query and return comprehensive response"""
        try:
            # Initialize components if not already done
            if not self.model:
                self.initialize_components()
            
            # Search Pinecone
            matches = self.search_pinecone(query, top_k=20)
            
            if not matches:
                return {
                    'response': "I couldn't find any relevant data for this query.",
                    'sources': []
                }
            
            # Analyze results by chunk type
            chunk_types = {}
            for match in matches:
                chunk_type = match['metadata'].get('chunk_type', 'unknown')
                if chunk_type not in chunk_types:
                    chunk_types[chunk_type] = []
                chunk_types[chunk_type].append(match)
            
            # Generate response based on chunk types found
            response_parts = []
            
            # Film Performance Results
            if 'film_performance' in chunk_types:
                film_matches = chunk_types['film_performance'][:5]
                response_parts.append("**Film Performance Data:**")
                for i, match in enumerate(film_matches, 1):
                    metadata = match['metadata']
                    response_parts.append(f"{i}. **{metadata.get('title', 'Unknown')}**")
                    response_parts.append(f"   - Theater: {metadata.get('theater_name', 'Unknown')} in {metadata.get('theater_city', 'Unknown')}")
                    response_parts.append(f"   - Occupancy: {metadata.get('occupancy_rate', 0):.1f}%")
                    response_parts.append(f"   - Sales: ${metadata.get('sales_estimate', 0):,.2f}")
                    response_parts.append(f"   - Format: {metadata.get('screen_format', 'Unknown')}")
                    response_parts.append("")
            
            # Movie Summary Results
            if 'movie_summary' in chunk_types:
                summary_matches = chunk_types['movie_summary'][:3]
                response_parts.append("**Movie Summary Data:**")
                for i, match in enumerate(summary_matches, 1):
                    metadata = match['metadata']
                    response_parts.append(f"{i}. **{metadata.get('title', 'Unknown')}**")
                    response_parts.append(f"   - Genre: {metadata.get('genre', 'Unknown')} | Rating: {metadata.get('rating', 'Unknown')}")
                    response_parts.append(f"   - Overall Occupancy: {metadata.get('overall_occupancy', 0):.1f}%")
                    response_parts.append(f"   - Total Sales: ${metadata.get('total_sales', 0):,.2f}")
                    response_parts.append(f"   - Theaters: {metadata.get('theater_count', 0)}")
                    response_parts.append(f"   - Cities: {metadata.get('city_count', 0)}")
                    response_parts.append("")
            
            # Theater Performance Results
            if 'theater_performance' in chunk_types:
                theater_matches = chunk_types['theater_performance'][:3]
                response_parts.append("**Theater Performance Data:**")
                for i, match in enumerate(theater_matches, 1):
                    metadata = match['metadata']
                    response_parts.append(f"{i}. **{metadata.get('theater_name', 'Unknown')}**")
                    response_parts.append(f"   - Location: {metadata.get('theater_city', 'Unknown')}, {metadata.get('theater_state', 'Unknown')}")
                    response_parts.append(f"   - Circuit: {metadata.get('circuit_name', 'Unknown')}")
                    response_parts.append(f"   - Occupancy: {metadata.get('overall_occupancy', 0):.1f}%")
                    response_parts.append(f"   - Movies: {metadata.get('movie_count', 0)}")
                    response_parts.append("")
            
            # Combine response
            if response_parts:
                response = "\n".join(response_parts)
            else:
                response = "I found some data but couldn't format it properly."
            
            return {
                'response': response,
                'sources': matches[:10],
                'chunk_types_found': list(chunk_types.keys())
            }
            
        except Exception as e:
            logger.error(f"❌ Query processing failed: {e}")
            return {
                'response': f"I encountered an error processing your query: {str(e)}",
                'sources': []
            }

def main():
    """Test the query handler"""
    handler = SimplePineconeQueryHandler()
    
    # Test queries
    test_queries = [
        "What films are performing like JURASSIC WORLD REBIRTH?",
        "Where are my opportunities?",
        "How is WEAPONS performing?",
        "Show me theater performance data",
        "What movies are playing at AMC?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"{'='*60}")
        
        result = handler.process_query(query)
        print(f"Response: {result['response']}")
        print(f"Chunk Types Found: {result.get('chunk_types_found', [])}")

if __name__ == "__main__":
    main()
