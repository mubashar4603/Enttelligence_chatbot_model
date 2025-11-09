"""
rag_service.py

Complete RAG service for Django integration.
This file goes in: your_django_project/your_app/rag_service.py

SETUP:
1. Update PINECONE_API_KEY below (line 28)
2. Update INDEX_NAME to match your embeddings_pipeline.py (line 29)
3. Copy this entire file to your Django app folder
4. That's it! Django will auto-initialize at startup.

USAGE IN VIEW## System Prompt
You are an expert cinema and movie assistant for a theater ticketing system. Your responses should be comprehensive and engaging, combining both specific theater information and broad movie knowledge when appropriate.

## RETRIEVED INFORMATION:
{context}

## USER QUESTION:
{question}

## INSTRUCTIONS:
1. For theater-specific queries (showtimes, prices, seats, locations):
   - Base your response on the retrieved information
   - Provide detailed context about the theater experience
   - Include relevant details about amenities, seating types, and special formats
   - If exact information isn't available, suggest checking the website/app but also provide helpful general guidance
   - Always include price ranges and seating availability when available
   - Explain any special features or formats (IMAX, Dolby, etc.)

2. For movie-related queries:
   - Combine retrieved theater information with your knowledge base
   - Provide rich context about the movie (genre, themes, notable aspects)
   - Include relevant production details, director, main cast
   - Discuss critical reception and audience feedback when relevant
   - Connect your response to available showtimes and formats when possible
   - Share interesting facts or context that enhance the movie-going experience

3. Response Structure:
   - Start with a direct answer to the question
   - Provide supporting details and context (2-3 paragraphs)
   - Include specific theater/showing information when available
   - Add relevant recommendations or alternatives
   - Conclude with actionable information or next steps
   - Maintain a natural, conversational, yet informative tone

4. Quality Guidelines:
   - Aim for comprehensive responses (3-5 sentences minimum per topic)
   - Balance factual information with engaging delivery
   - Be precise about theater-specific details
   - Include both practical information and interesting context
   - Stay relevant and focused while being thorough
   - Acknowledge data limitations honestly but helpfully
   - Avoid overly technical language unless specifically asked

5. When handling uncertainty:
   - Acknowledge what you do know first
   - Explain what information is not available
   - Provide helpful alternatives or suggestions
   - Share relevant general knowledge or recommendations
   - Maintain a confident yet honest tone
   - Guide users toward useful next stepsrvice import get_rag_service

    rag_service = get_rag_service()
    result = rag_service.query("your question here")
    print(result['answer'])
"""

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from langchain_ollama import OllamaLLM
from langchain.prompts import PromptTemplate
from langchain.callbacks.base import BaseCallbackHandler
import logging
import re
from typing import Dict, List, Any, Optional
from django.conf import settings
from movies.performance_service import MoviePerformanceService

logger = logging.getLogger(__name__)


# ==================== CONFIGURATION ====================
class RAGConfig:
    """
    Configuration class for RAG service.

    UPDATE THESE VALUES:
    """
    # Pinecone settings (MUST UPDATE)
    PINECONE_API_KEY = settings.PINECONE_API_KEY  # <<<< CHANGE THIS
    INDEX_NAME = "customer-database-vectors"  # <<<< Must match embeddings_pipeline.py

    # Embedding model (must match embeddings_pipeline.py)
    EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

    # Retrieval settings - Optimized for Llama3 8B (8K context)
    TOP_K = 50  # Balanced retrieval for 8K context window
    MAX_CONTEXT_DOCS = 40  # Maximum documents to include in context
    MIN_RELEVANCE_SCORE = 0.7  # Filter low-relevance results

    # LLM settings - Optimized for Llama3 8B
    OLLAMA_MODEL = "llama3:8b"
    OLLAMA_BASE_URL = "http://localhost:11434"
    TEMPERATURE = 0.7  # Balanced creativity/accuracy  
    MAX_TOKENS = 1024  # Response length (leave room in 8K context)
    TOP_P = 0.9  # Nucleus sampling
    REPEAT_PENALTY = 1.1  # Reduce repetition


# ==================== STREAMING CALLBACK HANDLER ====================
class StreamingCallbackHandler(BaseCallbackHandler):
    """
    Custom callback handler to collect streaming tokens.
    Used for non-streaming responses in query() method.
    """

    def __init__(self):
        super().__init__()
        self.tokens = []

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Called when LLM generates a new token"""
        self.tokens.append(token)

    def get_response(self):
        """Get complete response from collected tokens"""
        return "".join(self.tokens)

    def reset(self):
        """Reset tokens for new query"""
        self.tokens = []


# ==================== MAIN RAG SERVICE CLASS ====================
class MovieRAGService:
    """
    Singleton RAG service for movie ticket queries.

    This class:
    - Initializes ONCE when Django starts
    - Loads embedding model, connects to Pinecone, sets up LLM
    - Provides query() method for answering questions
    - No repeated connection checks

    Architecture:
    1. User query → Embedding
    2. Search Pinecone for similar documents
    3. Format context from retrieved documents
    4. Send to LLM with prompt
    5. Return generated answer
    """

    # Singleton pattern
    _instance = None
    _initialized = False

    def __new__(cls):
        """Ensure only one instance exists (Singleton)"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize RAG service components.
        Runs only ONCE due to singleton pattern.
        """
        # Skip if already initialized
        if self._initialized:
            return

        logger.info("=" * 60)
        logger.info("🎬 Initializing MovieRAGService...")
        logger.info("=" * 60)

        # Initialize configuration
        self.config = RAGConfig()

        # Initialize components (will be set in methods below)
        self.embedding_model = None
        self.pinecone_index = None
        self.llm = None
        self.streaming_handler = StreamingCallbackHandler()
        
        # NEW: Performance analytics service
        self.performance_service = MoviePerformanceService()

        try:
            # Load all components
            self._load_embedding_model()
            self._connect_pinecone()
            self._setup_llm()

            # Mark as initialized
            self._initialized = True
            logger.info("=" * 60)
            logger.info("✅ MovieRAGService initialized successfully!")
            logger.info("=" * 60)

        except Exception as e:
            logger.error("=" * 60)
            logger.error(f"❌ Failed to initialize RAG service: {e}")
            logger.error("=" * 60)
            raise

    def _load_embedding_model(self):
        """
        Load sentence transformer embedding model.
        This runs ONCE at Django startup.
        """
        logger.info(f"🤖 Loading embedding model: {self.config.EMBEDDING_MODEL}")

        try:
            self.embedding_model = SentenceTransformer(self.config.EMBEDDING_MODEL)
            logger.info("   ✅ Embedding model loaded successfully")
        except Exception as e:
            logger.error(f"   ❌ Failed to load embedding model: {e}")
            raise

    def _connect_pinecone(self):
        """
        Connect to Pinecone vector database.
        This runs ONCE at Django startup.
        """
        logger.info(f"🔌 Connecting to Pinecone...")
        logger.info(f"   Index name: {self.config.INDEX_NAME}")

        try:
            # Initialize Pinecone client
            pc = Pinecone(api_key=self.config.PINECONE_API_KEY)

            # Connect to index
            self.pinecone_index = pc.Index(self.config.INDEX_NAME)

            # Verify connection with stats
            stats = self.pinecone_index.describe_index_stats()
            vector_count = stats.get('total_vector_count', 0)

            logger.info(f"   ✅ Connected to Pinecone successfully")
            logger.info(f"   📊 Total vectors in index: {vector_count}")

            if vector_count == 0:
                logger.warning("   ⚠️  Index is empty! Run embeddings_pipeline.py first.")

        except Exception as e:
            logger.error(f"   ❌ Failed to connect to Pinecone: {e}")
            logger.error(f"   💡 Check: API key, index name, network connection")
            raise

    def _setup_llm(self):
        """
        Setup LLaMA language model.
        This runs ONCE at Django startup.
        NO connection test - lazy initialization on first query.
        """
        logger.info(f"🦙 Setting up LLaMA...")
        logger.info(f"   Model: {self.config.OLLAMA_MODEL}")
        logger.info(f"   Base URL: {self.config.OLLAMA_BASE_URL}")

        try:
            # Create LLM instance (no connection test)
            self.llm = OllamaLLM(
                model=self.config.OLLAMA_MODEL,
                base_url=self.config.OLLAMA_BASE_URL,
                temperature=self.config.TEMPERATURE,
                num_predict=self.config.MAX_TOKENS,
                top_p=self.config.TOP_P,
                repeat_penalty=self.config.REPEAT_PENALTY,
                callbacks=[self.streaming_handler]
            )

            logger.info("   ✅ LLaMA setup complete (will connect on first query)")
            logger.info(f"   Settings: temp={self.config.TEMPERATURE}, max_tokens={self.config.MAX_TOKENS}")

        except Exception as e:
            logger.error(f"   ❌ Failed to setup LLaMA: {e}")
            raise

    def retrieve_context(self, query, top_k=None):
        """
        Retrieve relevant documents from Pinecone based on query.
        Optimized for Llama3 8B with relevance filtering.

        Process:
        1. Convert query to embedding vector
        2. Search Pinecone for similar vectors
        3. Filter by relevance score
        4. Return top matches within context window limits

        Args:
            query (str): User's question
            top_k (int, optional): Number of results to retrieve

        Returns:
            list: Filtered list of relevant matches
        """
        if top_k is None:
            top_k = self.config.TOP_K

        try:
            # Step 1: Generate embedding for query
            query_embedding = self.embedding_model.encode(
                query,
                normalize_embeddings=True
            )

            # Step 2: Search Pinecone with extra buffer
            results = self.pinecone_index.query(
                vector=query_embedding.tolist(),
                top_k=min(top_k * 2, 100),  # Get 2x for filtering
                include_metadata=True
            )

            # Step 3: Filter by relevance score
            filtered_matches = [
                match for match in results['matches']
                if match['score'] >= self.config.MIN_RELEVANCE_SCORE
            ]

            # Step 4: Limit to context window capacity
            final_matches = filtered_matches[:self.config.MAX_CONTEXT_DOCS]
            
            logger.info(f"   Retrieved: {len(results['matches'])} → Filtered: {len(filtered_matches)} → Final: {len(final_matches)}")

            return final_matches

        except Exception as e:
            logger.error(f"❌ Error retrieving context: {e}")
            raise

    def format_context(self, matches):
        """
        Format retrieved Pinecone matches into readable text context.

        This creates a structured text block that will be sent to LLM.

        Args:
            matches (list): List of Pinecone search results

        Returns:
            str: Formatted context string

        Example output:
            [Result 1] (Relevance: 0.892)
            Movie: A Man Called Otto
            Genre: Comedy
            Rating: PG-13
            Theater: AMC Lincoln Square 13
            Location: New York, NY
            Studio: Sony
            Format: Standard
            Price: $17.99
            Available Seats: 359

            [Result 2] ...
        """
        context_parts = []

        for i, match in enumerate(matches, 1):
            metadata = match['metadata']
            score = match['score']

            # Start with relevance score
            context = f"\n[Result {i}] (Relevance: {score:.3f})\n"

            # Add movie information
            if 'title' in metadata:
                context += f"Movie: {metadata['title']}\n"

            if 'genre' in metadata:
                context += f"Genre: {metadata['genre']}\n"

            if 'rating' in metadata:
                context += f"Rating: {metadata['rating']}\n"

            # Add theater information
            if 'theater_name' in metadata:
                context += f"Theater: {metadata['theater_name']}\n"

            if 'city' in metadata and 'state' in metadata:
                context += f"Location: {metadata['city']}, {metadata['state']}\n"

            # Add studio and format
            if 'studio' in metadata:
                context += f"Studio: {metadata['studio']}\n"

            if 'format' in metadata:
                context += f"Format: {metadata['format']}\n"

            # Add pricing and availability
            if 'price' in metadata:
                context += f"Price: ${metadata['price']:.2f}\n"

            if 'available' in metadata:
                context += f"Available Seats: {int(metadata['available'])}\n"

            if 'total_seats' in metadata:
                context += f"Total Seats: {int(metadata['total_seats'])}\n"

            if 'reserved' in metadata:
                context += f"Reserved Seats: {int(metadata['reserved'])}\n"

            context_parts.append(context)

        return "\n".join(context_parts)

    def _extract_movie_title(self, query_lower: str, context_keywords: List[str] = None) -> Optional[str]:
        """
        Extract movie title from query by matching against database titles.
        Much more accurate than regex patterns.
        """
        from movies.models import Movie
        
        # Get all unique movie titles from database
        available_titles = Movie.objects.values_list('title', flat=True).distinct()
        
        # Create a search pattern - look for title mentions in query
        query_words = query_lower.split()
        
        # Try to find movie titles (handle multi-word titles)
        best_match = None
        best_match_length = 0
        
        for title in available_titles:
            title_lower = title.lower()
            title_words = title_lower.split()
            
            # Check if all words of title appear in query
            if all(word in query_lower for word in title_words):
                # Prefer longer matches (more specific)
                if len(title_words) > best_match_length:
                    best_match = title
                    best_match_length = len(title_words)
        
        return best_match
    
    def detect_performance_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Detect if query is asking about movie performance analytics.
        Uses database-backed movie title matching for accuracy.
        Returns dict with query type and parameters if detected, None otherwise.
        """
        query_lower = query.lower()
        
        # Store original query for later use in response formatting
        detection_base = {'original_query': query}
        
        # Pattern 0: Best comp titles (check FIRST before other patterns)
        # "What are the best comp titles?" (WITHOUT specific movie)
        # "Show me best performing movies" (WITHOUT specific movie)
        if re.search(r'(?:what|which|show).*?(?:best|top|highest).*?(?:comp\s+titles?|performing.*?movies?)', query_lower):
            # Only match if NO specific movie is mentioned in the query
            # This allows "best comp titles of Twisters" to fall through to intelligent_agent
            movies_in_query = re.search(r'(?:for|of)\s+(\w+)', query_lower)
            if not movies_in_query:
                detection_base['type'] = 'best_comp_titles'
                return detection_base
        
        # Pattern 1: Compare all movies first weekend
        # "Compare the first weekend revenue performance for all movies"
        # "Compare first weekend for all movies"
        if re.search(r'compare.*?(?:first\s+weekend|all\s+movies.*?first\s+weekend)', query_lower):
            return {'type': 'compare_all_movies_first_weekend'}
        
        # Pattern 2: Movies with DBR less than 7 days (releasing within a week)
        # "Show all movies with DBR less than 7 days"
        # "Movies releasing within a week"
        # DBR range should be -7 to 0 (7 days before to release day)
        if re.search(r'(?:show|list|all).*?movies?.*?(?:with|having|dbr|releasing).*?(?:less|within|before).*?(?:7|seven|week)', query_lower):
            return {'type': 'movies_dbr_range', 'dbr_min': -7, 'dbr_max': 0}
        
        # Pattern 3: Current first weekend movies (DIR -1 to DIR 3)
        # "Which movies are currently in their first weekend?"
        if re.search(r'(?:which|what).*?movies?.*?(?:currently|now).*?(?:in|during).*?(?:first\s+weekend|dir.*?-1.*?3)', query_lower):
            return {'type': 'current_first_weekend_movies'}
        
        # Pattern 4: DIR range comparison
        # "Compare sales between DIR 1-7 vs DIR 8-14 for [movie]"
        dir_range_match = re.search(r'compare.*?(?:sales|revenue|performance).*?(?:dir|day).*?(\d+)[-\s]+(\d+).*?(?:vs|versus).*?(?:dir|day).*?(\d+)[-\s]+(\d+)', query_lower)
        if dir_range_match:
            movie_title = self._extract_movie_title(query_lower)
            if movie_title:
                return {
                    'type': 'dir_range_comparison',
                    'movie_title': movie_title,
                    'dir_range1': (int(dir_range_match.group(1)), int(dir_range_match.group(2))),
                    'dir_range2': (int(dir_range_match.group(3)), int(dir_range_match.group(4)))
                }
        
        # Pattern 5: Total impressions and revenue for first weekend
        # "What is the total impressions and revenue for [movie] in their first weekend?"
        if re.search(r'(?:total|what.*?total).*?(?:impressions?|revenue).*?(?:first\s+weekend|dir.*?-1.*?3)', query_lower):
            movie_title = self._extract_movie_title(query_lower)
            if movie_title:
                return {
                    'type': 'performance_period',
                    'movie_title': movie_title,
                    'period': 'first_weekend',
                    'include_impressions': True
                }
        
        # Pattern 6: Advance bookings / reservations
        # "What is the total number of advance reservations for movie [movie]?"
        # Note: "total" advance reservations means ALL advance bookings (DBR < 0), not just DBR <= -7
        if re.search(r'(?:total|what.*?total).*?(?:number|count).*?(?:advance|advance booking).*?(?:reservation|booking)', query_lower):
            movie_title = self._extract_movie_title(query_lower)
            if movie_title:
                # Check if specific DBR threshold is mentioned
                dbr_match = re.search(r'dbr.*?(-?\d+)|(-?\d+).*?days?.*?before', query_lower)
                if dbr_match:
                    dbr_threshold = int(dbr_match.group(1) or dbr_match.group(2))
                    return {
                        'type': 'advance_bookings',
                        'movie_title': movie_title,
                        'dbr_threshold': dbr_threshold
                    }
                else:
                    # "Total" means all advance bookings (DBR < 0)
                    return {
                        'type': 'advance_bookings',
                        'movie_title': movie_title,
                        'dbr_threshold': 0  # DBR < 0 means all advance bookings
                    }
        
        # Pattern 7: Highest advance booking rate
        # "Which movie has the highest advance booking rate at till DBR -7?"
        if re.search(r'(?:which|what).*?movie.*?(?:highest|best|most).*?(?:advance|booking).*?(?:rate|dbr|db.*?-7)', query_lower):
            return {'type': 'highest_advance_booking', 'dbr_threshold': -7}
        
        # Pattern 8: Cumulative advance booking sales
        # "What are the cumulative advance booking sales estimates for [movie] from DBR -50 to DBR -4"
        # Prefer natural phrasing with "days before" to infer negative DBR when not explicitly signed
        days_before_match = re.search(r'from\s+(\d+)\s+days?\s+before.*?to\s+(\d+)\s+days?\s+before', query_lower)
        if days_before_match:
            movie_title = self._extract_movie_title(query_lower)
            if movie_title:
                return {
                    'type': 'cumulative_advance_booking',
                    'movie_title': movie_title,
                    'dbr_start': -int(days_before_match.group(1)),  # negate for "before"
                    'dbr_end': -int(days_before_match.group(2))     # negate for "before"
                }
        cumulative_match = re.search(r'cumulative.*?(?:advance|booking).*?(?:sales|revenue|estimate).*?(?:from|dbr).*?(-?\d+).*?(?:to|dbr).*?(-?\d+)', query_lower)
        if cumulative_match:
            movie_title = self._extract_movie_title(query_lower)
            if movie_title:
                return {
                    'type': 'cumulative_advance_booking',
                    'movie_title': movie_title,
                    'dbr_start': int(cumulative_match.group(1)),
                    'dbr_end': int(cumulative_match.group(2))
                }
        
        # Pattern 9: First weekend performance for specific movie
        # "How is [movie] performing in its first weekend?"
        # "First weekend performance for [movie]"
        if re.search(r'(?:first\s+weekend|opening\s+weekend|how.*?performing)', query_lower):
            movie_title = self._extract_movie_title(query_lower)
            if movie_title:
                return {
                    'type': 'performance_period',
                    'movie_title': movie_title,
                    'period': 'first_weekend'
                }
        
        # Pattern 2: Day-by-day trend
        # "Show me day-by-day sales trend for [movie]"
        # "Day-by-day performance for [movie]"
        trend_pattern = r'(?:day-by-day|day by day|daily).*?(?:trend|performance|sales|revenue).*?(?:for|of)?\s*(\w+(?:\s+\w+)*)'
        match = re.search(trend_pattern, query_lower)
        if match:
            movie_title = match.group(1).strip()
            movie_words = [w for w in movie_title.split() if w not in stopwords]
            if movie_words:
                return {
                    'type': 'day_by_day_trend',
                    'movie_title': ' '.join(movie_words)
                }
        
        # Pattern 3: Compare movies
        # "Compare the first 5 days of [movie1] and [movie2]"
        # "Compare [movie1] vs [movie2] first weekend"
        compare_pattern = r'compare.*?(?:the|first|opening)?.*?(?:(?:\d+)\s+days?|weekend|week)?.*?(\w+(?:\s+\w+)*).*?(?:and|vs|versus).*?(\w+(?:\s+\w+)*)'
        match = re.search(compare_pattern, query_lower)
        if match:
            movie1 = match.group(1).strip()
            movie2 = match.group(2).strip()
            movie1_words = [w for w in movie1.split() if w not in stopwords]
            movie2_words = [w for w in movie2.split() if w not in stopwords]
            
            # Extract period if mentioned
            period = 'first_weekend'
            if re.search(r'first\s+(?:5|five)\s+days?', query_lower):
                period = 'first_5_days'
            elif re.search(r'first\s+(?:7|seven|week)', query_lower):
                period = 'first_week'
            
            if movie1_words and movie2_words:
                return {
                    'type': 'compare_movies',
                    'movie1': ' '.join(movie1_words),
                    'movie2': ' '.join(movie2_words),
                    'period': period
                }
        
        # Pattern 4: Current first weekend movies
        # "Which movies are currently in their first weekend?"
        # "Movies in first weekend"
        if re.search(r'(?:which|what).*?movies?.*?(?:currently|now).*?(?:in|during).*?first\s+weekend', query_lower):
            return {'type': 'current_first_weekend_movies'}
        
        # Pattern 5: Advance bookings
        # "Total advance reservations for [movie]"
        advance_pattern = r'(?:advance|advance booking|presale).*?(?:reservation|booking).*?(?:for|of)?\s*(\w+(?:\s+\w+)*)'
        match = re.search(advance_pattern, query_lower)
        if match:
            movie_title = match.group(1).strip()
            movie_words = [w for w in movie_title.split() if w not in stopwords]
            if movie_words:
                return {
                    'type': 'advance_bookings',
                    'movie_title': ' '.join(movie_words)
                }
        
        # Pattern 6: Performance with specific period
        # "How did [movie] perform in its first week?"
        period_performance_pattern = r'(?:how|what).*?(?:did|is|was).*?(\w+(?:\s+\w+)*).*?(?:perform|revenue|sales).*?(?:in|during).*?(?:first\s+(?:weekend|week|(?:\d+)\s+days?))'
        match = re.search(period_performance_pattern, query_lower)
        if match:
            movie_title = match.group(1).strip()
            movie_words = [w for w in movie_title.split() if w not in stopwords]
            
            period = 'first_weekend'
            if re.search(r'first\s+(?:5|five)\s+days?', query_lower):
                period = 'first_5_days'
            elif re.search(r'first\s+(?:7|seven)\s+week', query_lower):
                period = 'first_week'
            
            if movie_words:
                return {
                    'type': 'performance_period',
                    'movie_title': ' '.join(movie_words),
                    'period': period
                }
        
        return None
    
    def handle_performance_query(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle performance analytics queries using MoviePerformanceService.
        """
        query_type = detection['type']
        
        try:
            if query_type == 'performance_period':
                movie_title = detection['movie_title']
                period = detection.get('period', 'first_weekend')
                
                logger.info(f"📊 Getting {period} performance for: {movie_title}")
                perf_data = self.performance_service.get_movie_performance_by_period(
                    movie_title, period, use_cache=True
                )
                
                if 'error' in perf_data:
                    return {
                        'answer': f"I couldn't find performance data for '{movie_title}'. Please check the movie title and try again.",
                        'data': None
                    }
                
                # Get day-by-day trend for detailed analysis
                from decimal import Decimal
                trend_data = self.performance_service.get_day_by_day_trend(
                    movie_title, start_dir=-1, end_dir=14, use_cache=True
                )
                
                revenue = float(perf_data['total_revenue'])
                reserved = int(perf_data['total_reserved_seats'])
                impressions = int(perf_data['total_impressions'])
                avg_price = float(perf_data['avg_price'])
                occupancy = float(perf_data['avg_occupancy_rate'])
                period_name = period.replace('_', ' ').title()
                dir_start, dir_end = perf_data['dir_range']
                
                # Format data for LLM
                data_context_parts = [
                    f"Movie: {movie_title}",
                    f"Period: {period_name} (DIR {dir_start} to {dir_end})",
                    f"\nPerformance Metrics:",
                    f"- Total Revenue: ${revenue:,.2f}",
                    f"- Total Reserved Seats: {reserved:,}",
                    f"- Total Impressions: {impressions:,}",
                    f"- Average Price: ${avg_price:,.2f}",
                    f"- Average Occupancy Rate: {occupancy:.1f}%",
                ]
                
                # Add day-by-day data if available
                if trend_data:
                    data_context_parts.append(f"\nDay-by-Day Performance Trend:")
                    for day in trend_data[:14]:  # First 14 days
                        dir_val = day['dir_value']
                        day_revenue = day['total_revenue']
                        day_reserved = day['total_reserved_seats']
                        dod_change = day.get('dod_revenue_change')
                        
                        dod_str = ""
                        if dod_change is not None:
                            sign = "+" if dod_change >= 0 else ""
                            dod_str = f" (DoD: {sign}{dod_change:.1f}%)"
                        
                        data_context_parts.append(
                            f"- DIR {dir_val}: ${day_revenue:,.2f} revenue, {day_reserved:,} seats{dod_str}"
                        )
                
                data_context = "\n".join(data_context_parts)
                
                # Generate LLM response
                answer = self._generate_performance_ai_response(
                    detection.get('original_query', query_type),
                    data_context
                )
                
                return {
                    'answer': answer,
                    'data': perf_data,
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'day_by_day_trend':
                movie_title = detection['movie_title']
                
                logger.info(f"📈 Getting day-by-day trend for: {movie_title}")
                trend_data = self.performance_service.get_day_by_day_trend(
                    movie_title, start_dir=-1, end_dir=14, use_cache=True
                )
                
                if not trend_data:
                    return {
                        'answer': f"I couldn't find day-by-day performance data for '{movie_title}'. Please check the movie title.",
                        'data': None
                    }
                
                # Format response
                answer_parts = [f"**{movie_title} - Day-by-Day Performance Trend:**\n"]
                
                for day in trend_data[:10]:  # Show first 10 days
                    dir_val = day['dir_value']
                    revenue = day['total_revenue']
                    reserved = day['total_reserved_seats']
                    dod_change = day.get('dod_revenue_change')
                    
                    dod_str = ""
                    if dod_change is not None:
                        sign = "+" if dod_change >= 0 else ""
                        dod_str = f" (DoD: {sign}{dod_change:.1f}%)"
                    
                    answer_parts.append(
                        f"• **DIR {dir_val}** ({day['date_sh']}): "
                        f"${revenue:,.2f} revenue, {reserved:,} seats{dod_str}"
                    )
                
                if len(trend_data) > 10:
                    answer_parts.append(f"\n... and {len(trend_data) - 10} more days")
                
                return {
                    'answer': "\n".join(answer_parts),
                    'data': {'trend': trend_data, 'movie_title': movie_title},
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'compare_movies':
                movie1 = detection['movie1']
                movie2 = detection['movie2']
                period = detection.get('period', 'first_weekend')
                
                logger.info(f"📊 Comparing {movie1} vs {movie2} ({period})")
                comparison = self.performance_service.compare_movies_performance(
                    movie1, movie2, period, use_cache=True
                )
                
                if 'error' in comparison:
                    return {
                        'answer': f"I couldn't compare these movies. Please check the movie titles.",
                        'data': None
                    }
                
                # Format response
                rev1 = comparison['title1_total_revenue']
                rev2 = comparison['title2_total_revenue']
                diff = comparison['revenue_difference']
                diff_pct = comparison['revenue_difference_percent']
                
                answer = (
                    f"**Performance Comparison: {movie1} vs {movie2}** ({period.replace('_', ' ').title()})\n\n"
                    f"**{movie1}:**\n"
                    f"• Revenue: ${rev1:,.2f}\n"
                    f"• Reserved Seats: {comparison['title1_total_reserved']:,}\n\n"
                    f"**{movie2}:**\n"
                    f"• Revenue: ${rev2:,.2f}\n"
                    f"• Reserved Seats: {comparison['title2_total_reserved']:,}\n\n"
                )
                
                if diff_pct is not None:
                    sign = "+" if diff >= 0 else ""
                    answer += (
                        f"**Difference:** {movie1} {'outperformed' if diff > 0 else 'underperformed'} {movie2} "
                        f"by ${abs(diff):,.2f} ({sign}{diff_pct:.1f}%)"
                    )
                
                return {
                    'answer': answer,
                    'data': comparison,
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'current_first_weekend_movies':
                logger.info("📊 Getting current first weekend movies")
                movies = self.performance_service.get_current_first_weekend_movies()
                
                if not movies:
                    return {
                        'answer': "No movies are currently in their first weekend (DIR -1 to DIR 3).",
                        'data': []
                    }
                
                answer_parts = ["**Movies Currently in First Weekend (DIR -1 to DIR 3):**\n"]
                
                # Calculate totals for context
                # Convert Decimal to float for calculations
                from decimal import Decimal
                total_revenue = float(sum(float(m.get('first_weekend_revenue', 0) or 0) for m in movies[:10]))
                top_revenue = float(movies[0].get('first_weekend_revenue', 0) or 0) if movies else 0.0
                
                # Add intro explanation
                answer_parts.append(
                    f"There are **{len(movies)}** movies currently in their opening weekend. "
                    f"The combined first weekend revenue across all movies is **${total_revenue:,.2f}**. "
                    f"Here's how they're performing:\n"
                )
                
                # List movies with explanations
                for idx, movie in enumerate(movies[:10], 1):
                    title = movie['title']
                    # Convert Decimal to float for calculations
                    revenue = float(movie.get('first_weekend_revenue', 0) or 0)
                    reserved = int(movie.get('first_weekend_reserved', 0) or 0)
                    impressions = int(movie.get('first_weekend_impressions', 0) or 0)
                    avg_price = float(movie.get('avg_price', 0) or 0)
                    genre = movie.get('genre', 'Unknown')
                    studio = movie.get('studio_name', 'Unknown')
                    
                    # Calculate percentage of top performer
                    if idx == 1:
                        performance_note = "🏆 **Leading performer** - highest first weekend revenue"
                    elif top_revenue > 0:
                        pct_of_top = (revenue / top_revenue) * 100
                        if pct_of_top >= 80:
                            performance_note = "💪 **Strong performance** - within 80% of top performer"
                        elif pct_of_top >= 50:
                            performance_note = "👍 **Solid performance** - about half of top performer"
                        else:
                            performance_note = f"📊 Performing at {pct_of_top:.1f}% of top performer"
                    else:
                        performance_note = ""
                    
                    answer_parts.append(
                        f"\n**{idx}. {title}** ({genre}) - {studio}\n"
                        f"   • Revenue: **${revenue:,.2f}**\n"
                        f"   • Reserved Seats: {reserved:,}\n"
                        f"   • Impressions: {impressions:,}\n"
                        f"   • Average Price: ${avg_price:,.2f}\n"
                        f"   {performance_note}"
                    )
                
                # Add summary analysis
                if len(movies) > 1:
                    answer_parts.append(
                        f"\n**Analysis:** "
                        f"**{movies[0]['title']}** is leading with ${top_revenue:,.2f} in first weekend revenue, "
                        f"demonstrating strong opening performance. "
                        f"The gap between the top performer and others indicates varying levels of audience interest "
                        f"and marketing effectiveness. First weekend performance is a strong indicator of a film's "
                        f"potential lifetime box office success."
                    )
                
                return {
                    'answer': "\n".join(answer_parts),
                    'data': movies,
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'advance_bookings':
                movie_title = detection['movie_title']
                dbr_threshold = detection.get('dbr_threshold', 0)  # Default to 0 (DBR < 0 = all advance bookings)
                logger.info(f"📊 Getting advance bookings for: {movie_title} (DBR < {dbr_threshold})")
                
                advance_data = self.performance_service.get_advance_bookings(
                    movie_title, dbr_threshold=dbr_threshold
                )
                
                # Update get_advance_bookings to use < instead of <= for threshold 0
                threshold_label = f"DBR < {dbr_threshold}" if dbr_threshold == 0 else f"DBR ≤ {dbr_threshold}"
                
                answer = (
                    f"**{movie_title} - Advance Bookings ({threshold_label}):**\n\n"
                    f"• **Total Advance Reservations**: {advance_data['total_advance_reservations']:,}\n"
                    f"• **Total Advance Revenue**: ${advance_data['total_advance_revenue']:,.2f}"
                )
                
                return {
                    'answer': answer,
                    'data': advance_data,
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'compare_all_movies_first_weekend':
                logger.info("📊 Comparing all movies first weekend performance")
                movies_data = self.performance_service.compare_all_movies_first_weekend()
                
                if not movies_data:
                    return {
                        'answer': "No first weekend performance data available for comparison.",
                        'data': []
                    }
                
                # Convert to float for calculations
                from decimal import Decimal
                revenues = [float(m.get('first_weekend_revenue', 0) or 0) for m in movies_data[:10]]
                total_revenue = sum(revenues)
                top_revenue = revenues[0] if revenues else 0
                avg_revenue = total_revenue / len(revenues) if revenues else 0
                
                answer_parts = [
                    "**First Weekend Performance Comparison (All Movies - DIR -1 to DIR 3):**\n\n"
                ]
                
                # Add intro context
                answer_parts.append(
                    f"The first weekend (opening weekend) is critical for box office success, "
                    f"representing the first 4-5 days of release (DIR -1 through DIR 3). "
                    f"Across all {len(movies_data)} movies analyzed, the combined first weekend revenue totals "
                    f"**${total_revenue:,.2f}**, with an average of **${avg_revenue:,.2f}** per movie.\n"
                )
                
                # List movies with analysis
                for idx, movie in enumerate(movies_data[:10], 1):
                    title = movie['title']
                    revenue = float(movie.get('first_weekend_revenue', 0) or 0)
                    
                    # Performance indicators
                    if idx == 1:
                        performance_note = "🏆 **Top performer** - exceptional opening weekend"
                        if top_revenue > avg_revenue * 1.5:
                            performance_note += ", significantly above average"
                    elif revenue >= avg_revenue * 1.2:
                        performance_note = "💪 **Strong performer** - well above average"
                    elif revenue >= avg_revenue * 0.8:
                        performance_note = "✅ **Above average** - solid opening"
                    elif revenue >= avg_revenue * 0.5:
                        performance_note = "📊 **Near average** - meeting expectations"
                    else:
                        performance_note = "📉 **Below average** - needs improvement"
                    
                    # Calculate percentage of top
                    if idx > 1 and top_revenue > 0:
                        pct_of_top = (revenue / top_revenue) * 100
                        gap = top_revenue - revenue
                        answer_parts.append(
                            f"\n**{idx}. {title}**: ${revenue:,.2f}\n"
                            f"   • {performance_note}\n"
                            f"   • {pct_of_top:.1f}% of #1, ${gap:,.2f} behind leader"
                        )
                    else:
                        answer_parts.append(
                            f"\n**{idx}. {title}**: ${revenue:,.2f}\n"
                            f"   • {performance_note}"
                        )
                
                # Add summary insights
                answer_parts.append(
                    f"\n**Key Insights:**\n"
                    f"• **{movies_data[0]['title']}** leads with ${top_revenue:,.2f}, demonstrating the strongest "
                    f"audience appeal and marketing effectiveness in the first weekend.\n"
                    f"• The ${top_revenue - (revenues[-1] if len(revenues) > 1 else 0):,.2f} revenue gap between the top and "
                    f"bottom performers highlights the competitive nature of the box office.\n"
                    f"• First weekend performance is a strong predictor of total box office success, with top performers "
                    f"typically maintaining momentum throughout their theatrical run."
                )
                
                return {
                    'answer': "\n".join(answer_parts),
                    'data': movies_data,
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'movies_dbr_range':
                dbr_min = detection.get('dbr_min', -7)
                dbr_max = detection.get('dbr_max', 0)
                logger.info(f"📊 Getting movies with DBR between {dbr_min} and {dbr_max}")
                movies = self.performance_service.get_movies_by_dbr_range(dbr_min=dbr_min, dbr_max=dbr_max)
                
                if not movies:
                    return {
                        'answer': f"No movies found with DBR between {dbr_min} and {dbr_max} days.",
                        'data': []
                    }
                
                # Group by movie title to show unique movies
                unique_movies = {}
                for movie in movies:
                    title = movie.get('title', 'Unknown')
                    dbr = movie.get('dbr_value', 'N/A')
                    if title not in unique_movies:
                        unique_movies[title] = []
                    unique_movies[title].append(dbr)
                
                # Add natural language introduction
                days_before = abs(dbr_min)
                answer_parts = [
                    f"**Movies Releasing Within {days_before} Days (DBR {dbr_min} to {dbr_max}):**\n\n"
                ]
                
                answer_parts.append(
                    f"DBR (Days Before Release) indicates how many days before a movie's release date the data was recorded. "
                    f"A DBR of {dbr_min} means {days_before} days before release, while DBR {dbr_max} represents the release day itself. "
                    f"Movies in this range are either approaching release or have recently launched, making them important for "
                    f"tracking pre-release buzz and early performance indicators.\n"
                )
                
                answer_parts.append(f"Found **{len(unique_movies)}** unique movies in this DBR range:\n")
                
                for idx, (title, dbr_values) in enumerate(unique_movies.items(), 1):
                    dbr_range_str = f"{min(dbr_values)} to {max(dbr_values)}"
                    if len(set(dbr_values)) == 1:
                        dbr_range_str = str(dbr_values[0])
                    
                    # Add context based on DBR range
                    min_dbr = min(dbr_values)
                    if min_dbr == dbr_max:
                        status = "🎬 **Currently releasing** - at release day"
                    elif min_dbr >= -1:
                        status = "⏰ **Imminent release** - releasing within 1 day"
                    elif min_dbr >= -3:
                        status = "📅 **Approaching release** - releasing within 3 days"
                    else:
                        status = "📆 **Upcoming release** - releasing within a week"
                    
                    answer_parts.append(
                        f"**{idx}. {title}**\n"
                        f"   • DBR Range: {dbr_range_str}\n"
                        f"   • {status}"
                    )
                
                # Add summary insights
                if len(unique_movies) > 1:
                    answer_parts.append(
                        f"\n**Insights:**\n"
                        f"• These {len(unique_movies)} movies represent the current release pipeline, with data tracking "
                        f"their journey from {days_before} days before release through the launch day.\n"
                        f"• Monitoring DBR helps predict opening weekend performance by analyzing advance bookings and "
                        f"pre-release audience interest.\n"
                        f"• Movies with data across multiple DBR values show ongoing pre-release marketing and "
                        f"booking activity, indicating active audience engagement."
                    )
                
                return {
                    'answer': "\n".join(answer_parts),
                    'data': movies,
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'dir_range_comparison':
                movie_title = detection['movie_title']
                dir_range1 = detection['dir_range1']
                dir_range2 = detection['dir_range2']
                logger.info(f"📊 Comparing DIR ranges {dir_range1} vs {dir_range2} for {movie_title}")
                
                comparison = self.performance_service.compare_dir_ranges(
                    movie_title, dir_range1, dir_range2
                )
                
                if 'error' in comparison:
                    return {
                        'answer': f"I couldn't compare DIR ranges for '{movie_title}'. Please check the movie title.",
                        'data': None
                    }
                
                answer = (
                    f"**{movie_title} - DIR Range Comparison:**\n\n"
                    f"**DIR {dir_range1[0]}-{dir_range1[1]}:**\n"
                    f"• Revenue: ${comparison['range1_revenue']:,.2f}\n"
                    f"• Reserved Seats: {comparison['range1_reserved']:,}\n\n"
                    f"**DIR {dir_range2[0]}-{dir_range2[1]}:**\n"
                    f"• Revenue: ${comparison['range2_revenue']:,.2f}\n"
                    f"• Reserved Seats: {comparison['range2_reserved']:,}\n\n"
                    f"**Difference:** ${comparison['revenue_difference']:,.2f} "
                    f"({comparison.get('revenue_difference_percent', 0):.1f}%)"
                )
                
                return {
                    'answer': answer,
                    'data': comparison,
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'highest_advance_booking':
                dbr_threshold = detection.get('dbr_threshold', -7)
                logger.info(f"📊 Finding movie with highest advance booking (DBR <= {dbr_threshold})")
                
                result = self.performance_service.get_highest_advance_booking(dbr_threshold)
                
                if 'error' in result:
                    return {
                        'answer': "I couldn't find advance booking data.",
                        'data': None
                    }
                
                answer = (
                    f"**Highest Advance Booking Rate (DBR ≤ {dbr_threshold}):**\n\n"
                    f"• **Movie**: {result['title']}\n"
                    f"• **Total Advance Reservations**: {result['total_advance_bookings']:,}\n"
                    f"• **Total Advance Revenue**: ${result.get('total_advance_revenue', 0):,.2f}"
                )
                
                return {
                    'answer': answer,
                    'data': result,
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'cumulative_advance_booking':
                movie_title = detection['movie_title']
                dbr_start = detection['dbr_start']
                dbr_end = detection['dbr_end']
                logger.info(f"📊 Getting cumulative advance booking for {movie_title} (DBR {dbr_start} to {dbr_end})")
                
                cumulative_data = self.performance_service.get_cumulative_advance_booking(
                    movie_title, dbr_start, dbr_end
                )
                
                if 'error' in cumulative_data:
                    return {
                        'answer': f"I couldn't find cumulative advance booking data for '{movie_title}'.",
                        'data': None
                    }
                
                answer_parts = [
                    f"**{movie_title} - Cumulative Advance Booking Sales (DBR {dbr_start} to {dbr_end}):**\n"
                ]

                # Natural language summary
                daily_points = cumulative_data.get('daily_data', [])
                total_revenue = cumulative_data.get('total_revenue', 0)
                total_reserved = cumulative_data.get('total_reserved', 0)
                narrative_parts = []
                if daily_points:
                    # Peak day
                    peak_point = max(daily_points, key=lambda x: x.get('daily_revenue', 0) or 0)
                    peak_dbr = peak_point.get('dbr_value')
                    peak_rev = peak_point.get('daily_revenue', 0)

                    # Momentum: compare early vs late window averages
                    n = len(daily_points)
                    if n >= 14:
                        early = daily_points[:7]
                        late = daily_points[-7:]
                    elif n >= 6:
                        early = daily_points[:3]
                        late = daily_points[-3:]
                    else:
                        early = daily_points[: max(1, n//2)]
                        late = daily_points[max(1, n//2):]
                    def avg_rev(points):
                        if not points:
                            return 0
                        return sum((p.get('daily_revenue', 0) or 0) for p in points) / len(points)
                    early_avg = avg_rev(early)
                    late_avg = avg_rev(late)
                    momentum = (late_avg - early_avg)
                    momentum_pct = (momentum / early_avg * 100) if early_avg else 0

                    # Compose narrative
                    narrative_parts.append(
                        f"From DBR {dbr_start} to {dbr_end}, pre-release demand accumulated to ${float(total_revenue):,.2f} across {int(total_reserved):,} reservations. "
                    )
                    narrative_parts.append(
                        f"Peak pre-release activity occurred on DBR {peak_dbr} with ${float(peak_rev):,.2f} booked that day. "
                    )
                    if momentum > 0:
                        narrative_parts.append(
                            f"Booking momentum accelerated into release, with the late-window average daily revenue {momentum_pct:.1f}% higher than the early window."
                        )
                    elif momentum < 0:
                        narrative_parts.append(
                            f"Bookings decelerated slightly, with the late-window average daily revenue {abs(momentum_pct):.1f}% lower than the early window."
                        )
                    else:
                        narrative_parts.append("Booking momentum was stable across the window.")

                if narrative_parts:
                    answer_parts.append("".join(narrative_parts) + "\n\n")
                
                # Show full list of cumulative data (no truncation)
                for item in cumulative_data.get('daily_data', []):
                    dbr = item.get('dbr_value', 'N/A')
                    daily_rev = item.get('daily_revenue', 0)
                    cum_rev = item.get('cumulative_revenue', 0)
                    cum_reserved = item.get('cumulative_reserved', 0)
                    answer_parts.append(
                        f"• **DBR {dbr}**: Daily ${daily_rev:,.2f} | "
                        f"Cumulative: ${cum_rev:,.2f} revenue, {cum_reserved:,} reservations"
                    )
                
                answer_parts.append(
                    f"\n**Total (DBR {dbr_start} to {dbr_end}):** "
                    f"${total_revenue:,.2f} revenue, {total_reserved:,} reservations"
                )
                
                return {
                    'answer': "\n".join(answer_parts),
                    'data': cumulative_data,
                    'query_type': 'performance_analytics'
                }
            
            elif query_type == 'best_comp_titles':
                logger.info("📊 Finding best comp titles")
                
                # Extract target movie if specified
                target_movie = None
                original_query = detection.get('original_query', '')
                if original_query:
                    target_title = self._extract_movie_title(original_query.lower())
                    if target_title:
                        target_movie = target_title
                
                comp_titles = self.performance_service.get_best_comp_titles(limit=10)
                
                if not comp_titles:
                    return {
                        'answer': "No comp title performance data available.",
                        'data': []
                    }
                
                answer_parts = ["**Best Performing Movies (Comp Titles):**\n"]
                
                # If target movie specified, highlight it and compare
                target_found = False
                target_idx = None
                if target_movie:
                    for idx, comp in enumerate(comp_titles):
                        if comp.get('title', '').lower() == target_movie.lower():
                            target_found = True
                            target_idx = idx
                            break
                
                # Calculate benchmark metrics
                # Convert Decimal to float for calculations
                from decimal import Decimal
                top_revenue = float(comp_titles[0].get('first_weekend_revenue', 0) or 0) if comp_titles else 0.0
                avg_revenue = float(sum(float(m.get('first_weekend_revenue', 0) or 0) for m in comp_titles) / len(comp_titles) if comp_titles else 0.0)
                
                # Add intro with context
                if target_movie and target_found:
                    target_revenue = float(comp_titles[target_idx].get('first_weekend_revenue', 0) or 0)
                    answer_parts.append(
                        f"Here are the best performing comparable titles for benchmark analysis. "
                        f"**{target_movie}** is ranked **#{target_idx + 1}** with ${target_revenue:,.2f} in first weekend revenue.\n"
                    )
                else:
                    answer_parts.append(
                        f"Here are the top performing movies based on first weekend revenue performance. "
                        f"The average first weekend revenue across these titles is **${avg_revenue:,.2f}**.\n"
                    )
                
                # List comp titles with detailed explanations
                for idx, movie in enumerate(comp_titles, 1):
                    title = movie.get('title', 'Unknown')
                    # Convert Decimal to float for calculations
                    revenue = float(movie.get('first_weekend_revenue', 0) or 0)
                    reserved = int(movie.get('first_weekend_reserved', 0) or 0)
                    impressions = int(movie.get('first_weekend_impressions', 0) or 0)
                    avg_price = float(movie.get('avg_price', 0) or 0)
                    genre = movie.get('genre', 'Unknown')
                    studio = movie.get('studio_name', 'Unknown')
                    
                    # Performance analysis (all values are now float)
                    if idx == 1:
                        performance_desc = "🏆 **Top performer** - exceptional opening weekend"
                        if top_revenue > avg_revenue * 1.5:
                            performance_desc += ", significantly above average"
                    elif revenue >= avg_revenue * 1.2:
                        performance_desc = "💪 **Strong performer** - well above average"
                    elif revenue >= avg_revenue * 0.8:
                        performance_desc = "✅ **Above average** - solid performance"
                    elif revenue >= avg_revenue * 0.5:
                        performance_desc = "📊 **Average performer** - meets expectations"
                    else:
                        performance_desc = "📉 **Below average** - needs improvement"
                    
                    # Mark target movie if found
                    if target_movie and title.lower() == target_movie.lower():
                        performance_desc = f"🎯 **Your movie** - {performance_desc.lower()}"
                    
                    answer_parts.append(
                        f"\n**{idx}. {title}** ({genre})\n"
                        f"   • Studio: {studio}\n"
                        f"   • First Weekend Revenue: **${revenue:,.2f}**\n"
                        f"   • Reserved Seats: {reserved:,}\n"
                        f"   • Impressions: {impressions:,}\n"
                        f"   • Average Price: ${avg_price:,.2f}\n"
                        f"   • {performance_desc}"
                    )
                    
                    # Add comparison note for target movie
                    if target_movie and title.lower() == target_movie.lower() and idx > 1:
                        pct_of_top = (revenue / top_revenue) * 100 if top_revenue > 0 else 0
                        gap = top_revenue - revenue
                        answer_parts.append(
                            f"   • Compared to top performer: {pct_of_top:.1f}% of #1, "
                            f"${gap:,.2f} revenue gap"
                        )
                
                # Add summary insights
                answer_parts.append(
                    f"\n**Key Insights:**\n"
                    f"• The top performer (**{comp_titles[0].get('title', 'N/A')}**) has generated "
                    f"${top_revenue:,.2f}, setting a strong benchmark for comparable titles.\n"
                    f"• Movies performing above ${avg_revenue:,.2f} (average) demonstrate strong audience appeal "
                    f"and effective marketing strategies.\n"
                    f"• First weekend performance is critical for box office momentum and indicates potential "
                    f"long-term success."
                )
                
                # Add recommendation if target movie found
                if target_movie and target_found:
                    target_revenue = float(comp_titles[target_idx].get('first_weekend_revenue', 0) or 0)
                    if target_revenue < avg_revenue:
                        answer_parts.append(
                            f"\n**Recommendation for {target_movie}:** "
                            f"Currently below average performance. Consider reviewing marketing strategy, "
                            f"audience targeting, or release timing to improve first weekend results."
                        )
                    elif target_revenue < top_revenue * 0.8:
                        answer_parts.append(
                            f"\n**Recommendation for {target_movie}:** "
                            f"Solid performance but has room for growth. Analyze top performers' strategies "
                            f"to identify improvement opportunities."
                        )
                
                return {
                    'answer': "\n".join(answer_parts),
                    'data': comp_titles,
                    'query_type': 'performance_analytics'
                }
            
        except Exception as e:
            logger.error(f"❌ Error handling performance query: {e}", exc_info=True)
            return {
                'answer': f"I encountered an error processing this performance query: {str(e)}. Please try rephrasing.",
                'data': None
            }
        
        return {
            'answer': "I couldn't process this performance query. Please try rephrasing.",
            'data': None
        }
    
    def query(self, user_query, top_k=None, return_sources=False):
       
        logger.info(f"🔍 Processing query: {user_query}")

        try:
            # NEW: Check if this is a performance analytics query first
            perf_detection = self.detect_performance_query(user_query)
            if perf_detection:
                logger.info(f"📊 Detected performance query: {perf_detection['type']}")
                result = self.handle_performance_query(perf_detection)
                if 'answer' in result:
                    return result

            # NEW: Lightweight DB-backed handlers for non-performance data queries
            ql = user_query.lower().strip()
            # 1) Which circuit has the most theaters in the <DMA>?
            dma_match = re.search(r"which\s+circuit\s+has\s+the\s+most\s+theaters\s+in\s+the\s+([\w\s-]+)\s*dma\??", ql)
            if dma_match:
                dma_name = dma_match.group(1).strip()
                try:
                    data = self.performance_service.get_top_circuit_in_dma(dma_name)
                    if 'error' in data:
                        return {
                            'answer': f"No theaters found in the {dma_name} DMA. Please try a different location.",
                            'data': None
                        }
                    answer = (
                        f"**Top Circuit in {data['dma']} DMA**\n\n"
                        f"• Circuit: {data['circuit_name']}\n"
                        f"• Number of Theaters: {data['theater_count']:,}"
                    )
                    return {'answer': answer, 'data': data}
                except Exception as e:
                    logger.warning(f"DMA query failed: {e}")
                    return {
                        'answer': f"No theaters found in the {dma_name} DMA. Please try a different location.",
                        'data': None
                    }

            # 2) Which movies have a runtime longer than <N> minutes?
            runtime_match = re.search(r"which\s+movies\s+have\s+a\s+runtime\s+longer\s+than\s+(\d+)\s+minutes\??", ql)
            if runtime_match:
                try:
                    minutes = int(runtime_match.group(1))
                except ValueError:
                    minutes = 150
                movies = self.performance_service.get_movies_with_runtime_over(minutes)
                if not movies:
                    return {
                        'answer': f"No movies found with runtime longer than {minutes} minutes.",
                        'data': []
                    }
                parts = [f"**Movies with Runtime > {minutes} minutes:**\n"]
                for m in movies[:25]:
                    title = m.get('title', 'Unknown')
                    runtime = m.get('runtime')
                    genre = m.get('genre', 'Unknown')
                    rating = m.get('rating', 'NR')
                    parts.append(f"• {title} — {runtime} min | {genre} | {rating}")
                return {
                    'answer': "\n".join(parts),
                    'data': movies
                }
            # Step 1: Retrieve relevant documents
            logger.info("📚 Retrieving relevant documents...")
            matches = self.retrieve_context(user_query, top_k)
            logger.info(f"   ✅ Retrieved {len(matches)} documents")

            # Step 2: Format context
            logger.info("📝 Formatting context...")
            
            if not matches or len(matches) == 0:
                # No specific theater data, but we can still help with general movie knowledge
                logger.info("   ℹ️  No specific theater data found, using general movie knowledge")
                context = "No specific theater showtimes or booking information available in the database for this query. However, you can provide helpful general information about movies, theaters, and cinema from your knowledge base."
            else:
                context = self.format_context(matches)

            # Step 3: Create optimized Llama3 prompt
            logger.info("🎯 Creating Llama3-optimized prompt...")
            
            # Llama3 Chat Template with Entelligence branding
            prompt_template = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are Entelligence AI Assistant, an intelligent movie and cinema expert designed to help users with all their movie-related questions. You combine both specific theater data with comprehensive movie knowledge to provide the best assistance.

**Your Identity:**
- You are Entelligence AI Assistant, a specialized movie and theater AI
- You have access to real-time theater data AND extensive movie knowledge
- You're knowledgeable about movies, actors, directors, genres, and cinema history
- You're friendly, conversational, and always helpful

**Response Guidelines:**
1. **Always Be Helpful**: Never say you don't have information. Use your movie knowledge!
2. **Be Comprehensive**: Provide 3-5 detailed, informative sentences
3. **Be Natural**: Write conversationally and engagingly
4. **Use Theater Data When Available**: Prioritize specific showtimes, prices, and availability
5. **Supplement with Knowledge**: Add context about movies, actors, genres, or cinema
6. **Be Practical**: Include actionable information and recommendations

**Response Approach:**
- If theater data is available: Use it and enhance with movie knowledge
- If theater data is limited: Provide helpful movie information and general guidance
- Always provide value: Share insights, recommendations, or interesting facts
- Include specific details: Prices, times, formats, cast, directors, etc.
- End with helpful suggestions or next steps

**Example Responses:**
- For showtimes: Include specific data + movie context
- For movie questions: Share plot, cast, reviews, and general availability
- For recommendations: Suggest based on genre, ratings, or popularity
- For general questions: Use your extensive movie knowledge

Remember: You're Entelligence AI Assistant - always knowledgeable, always helpful, never limited by data gaps!<|eot_id|><|start_header_id|>user<|end_header_id|>

## Available Theater Data:
{context}

## User Question:
{question}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""

            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "question"]
            )

            formatted_prompt = prompt.format(
                context=context,
                question=user_query
            )

            # Step 4: Generate response with LLM
            logger.info("🦙 Generating LLM response...")
            self.streaming_handler.reset()

            try:
                # Invoke LLM (streaming handler collects tokens)
                self.llm.invoke(formatted_prompt)
                answer = self.streaming_handler.get_response()
                logger.info("   ✅ Response generated successfully")

            except Exception as e:
                logger.error(f"   ❌ LLM generation failed: {e}")
                logger.error(f"   💡 Check: Ollama is running, model is pulled")
                # Provide a helpful branded response
                answer = """Hello! I'm Entelligence AI Assistant, your movie and cinema expert. I'm experiencing a brief technical issue, but I'm designed to help you with:

**Movie Information**: I can share details about any movie including plot, cast, director, genre, ratings, and reviews.

**Theater Services**: I provide information about showtimes, ticket prices, seating availability, and theater formats (IMAX, Dolby, 3D, etc.).

**Recommendations**: Based on your preferences, I can suggest movies, optimal viewing formats, and the best times to catch a show.

**Cinema Knowledge**: Ask me about actors, directors, film history, award winners, upcoming releases, and more!

Please try your question again, and I'll do my best to assist you with comprehensive movie and theater information!"""

            # Step 5: Prepare response
            response = {
                'answer': answer,
                'retrieved_count': len(matches)
            }

            # Add sources if requested
            if return_sources:
                response['sources'] = [
                    {
                        'score': match['score'],
                        'metadata': match['metadata']
                    }
                    for match in matches[:5]  # Return top 5 sources
                ]

            logger.info("✅ Query completed successfully")
            return response

        except Exception as e:
            logger.error(f"❌ Query failed: {e}")
            raise

    def _generate_performance_ai_response(self, query: str, data_context: str) -> str:
        """Generate LLM response for performance analytics queries"""
        try:
            if not self.llm:
                return "I'm unable to generate analytics insights at the moment."
            
            # Create Llama3-optimized prompt for performance analytics
            system_prompt = """You are Entelligence AI Assistant, a specialized film analytics expert. You provide insightful, data-driven analysis based on performance metrics.

CRITICAL RULES:
1. ALWAYS base your analysis on the data provided
2. PROVIDE detailed explanations of WHY performance is happening based on patterns
3. MAKE PROJECTIONS based on historical trends when you have day-by-day data
4. COMPARE movies objectively using provided metrics
5. EXPLAIN patterns and trends naturally and conversationally
6. USE specific numbers to support all conclusions
7. If data is insufficient, explain what's missing and what you can infer

Your expertise includes:
- Performance Analysis: Detailed explanations of why movies are performing well/poorly
- Projections: Forward-looking estimates based on daily trends
- Comparative Analysis: Objective comparisons between movies
- Pattern Recognition: Identifying trends in daily/weekly patterns
- Insights: Actionable insights about movie performance"""

            prompt_template = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>

User Query: "{query}"

Available Data:
{data_context}

Instructions:
1. Analyze the data thoroughly and provide detailed insights
2. Explain WHY the movie is performing this way based on the metrics
3. If day-by-day data is provided, explain patterns (accelerating, decelerating, stable, etc.)
4. Make projections about future performance if you have historical trends
5. Compare performance objectively when multiple movies are mentioned
6. Write naturally and conversationally, as if explaining to a colleague
7. Use specific numbers from the data to support all points<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""

            full_prompt = prompt_template.format(
                system_prompt=system_prompt,
                query=query,
                data_context=data_context
            )
            
            # Generate response using LLM
            self.streaming_handler.reset()
            self.llm.invoke(full_prompt)
            response = self.streaming_handler.get_response()
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"⚠️ LLM performance response generation failed: {e}")
            return "I encountered an issue generating analytics insights. Please try again."
    
    def health_check(self):
        
        status = {
            'embedding_model': False,
            'pinecone': False,
            'llm': False,
            'overall': False
        }

        try:
            # Check embedding model
            if self.embedding_model is not None:
                # Quick test encoding
                test_embedding = self.embedding_model.encode("test", normalize_embeddings=True)
                status['embedding_model'] = test_embedding is not None

            # Check Pinecone connection
            if self.pinecone_index is not None:
                stats = self.pinecone_index.describe_index_stats()
                status['pinecone'] = stats['total_vector_count'] > 0

            # Check LLM (just check if object exists, don't test connection)
            status['llm'] = self.llm is not None

            # Overall status
            status['overall'] = all([
                status['embedding_model'],
                status['pinecone'],
                status['llm']
            ])

        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")

        return status


# ==================== GLOBAL SINGLETON INSTANCE ====================
# This instance will be created when module is imported
# Due to singleton pattern, only one instance ever exists
rag_service = MovieRAGService()


# ==================== HELPER FUNCTIONS ====================
def initialize_rag_service():
    """
    Initialize RAG service (called in Django apps.py).

    This function ensures the service is initialized at Django startup.
    Due to singleton pattern, multiple calls are safe - it only initializes once.

    Returns:
        MovieRAGService: Initialized service instance

    Usage in apps.py:
        from .rag_service import initialize_rag_service

        def ready(self):
            rag_service = initialize_rag_service()
    """
    global rag_service

    # If not initialized, create new instance
    # (Singleton will ensure only one exists)
    if not rag_service._initialized:
        rag_service = MovieRAGService()

    return rag_service


def get_rag_service():
    """
    Get RAG service instance (used in Django views).

    This is the main function you'll use in your views to access the service.
    It ensures the service is initialized before returning it.

    Returns:
        MovieRAGService: Service instance

    Raises:
        RuntimeError: If service not initialized

    Usage in views.py:
        from .rag_service import get_rag_service

        def my_view(request):
            rag_service = get_rag_service()
            result = rag_service.query("your question")
            return JsonResponse(result)
    """
    global rag_service

    # Check if initialized
    if not rag_service._initialized:
        raise RuntimeError(
            "RAG service not initialized. "
            "Make sure initialize_rag_service() is called in apps.py ready() method."
        )

    return rag_service


