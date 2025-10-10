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
from langchain_community.llms import Ollama
from langchain.prompts import PromptTemplate
from langchain.callbacks.base import BaseCallbackHandler
import logging
from django.conf import settings

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

    # Retrieval settings
    TOP_K = 100  # Number of similar documents to retrieve

    # LLM settings
    OLLAMA_MODEL = "llama3:8b"
    OLLAMA_BASE_URL = "http://localhost:11434"  # Change if Ollama runs elsewhere
    TEMPERATURE = 0.7  # Lower = more focused, Higher = more creative
    MAX_TOKENS = 8192   # Maximum response length


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
            self.llm = Ollama(
                model=self.config.OLLAMA_MODEL,
                base_url=self.config.OLLAMA_BASE_URL,
                temperature=self.config.TEMPERATURE,
                num_predict=self.config.MAX_TOKENS,
                callbacks=[self.streaming_handler]
            )

            logger.info("   ✅ LLaMA setup complete (will connect on first query)")

        except Exception as e:
            logger.error(f"   ❌ Failed to setup LLaMA: {e}")
            raise

    def retrieve_context(self, query, top_k=None):
        """
        Retrieve relevant documents from Pinecone based on query.

        Process:
        1. Convert query to embedding vector
        2. Search Pinecone for similar vectors
        3. Return top_k most similar documents with metadata

        Args:
            query (str): User's question
            top_k (int, optional): Number of results to retrieve. 
                                   Defaults to config.TOP_K (20)

        Returns:
            list: List of matches, each containing:
                  - id: vector ID
                  - score: similarity score (0-1)
                  - metadata: document metadata (title, genre, etc.)

        Example:
            matches = self.retrieve_context("AMC New York movies")
            print(matches[0]['metadata']['title'])  # "A Man Called Otto"
        """
        if top_k is None:
            top_k = self.config.TOP_K

        try:
            # Step 1: Generate embedding for query
            query_embedding = self.embedding_model.encode(
                query,
                normalize_embeddings=True  # Must match embeddings_pipeline.py
            )

            # Step 2: Search Pinecone
            results = self.pinecone_index.query(
                vector=query_embedding.tolist(),
                top_k=top_k,
                include_metadata=True
            )

            # Step 3: Return matches
            return results['matches']

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

    def query(self, user_query, top_k=None, return_sources=False):
       
        logger.info(f"🔍 Processing query: {user_query}")

        try:
            # Step 1: Retrieve relevant documents
            logger.info("📚 Retrieving relevant documents...")
            matches = self.retrieve_context(user_query, top_k)
            logger.info(f"   ✅ Retrieved {len(matches)} documents")

            # Handle case when no matches found
            if not matches:
                logger.warning("   ⚠️  No relevant documents found in vector store")
                context = "No specific movie theater information found in the database. Using general knowledge to assist."
            else:
                context = self.format_context(matches)

            # Step 2: Format context
            logger.info("📝 Formatting context...")
            context = self.format_context(matches)

            # Step 3: Create prompt
            logger.info("🎯 Creating prompt...")
            prompt_template = """
## System Prompt
You are a helpful assistant for a movie ticketing system. You must answer the user's question only using the information provided below.

## RETRIEVED INFORMATION:
{context}

## USER QUESTION:
{question}

## INSTRUCTIONS:
- Return to the point answer, don't make hallucination.
- Answer only using the content from the retrieved information above.
- Do NOT use any prior, external, or general knowledge.
- If the retrieved information does not contain the answer, reply exactly with:
- 👉 “I don’t have any information about that.”
- Do not explain why you don’t have the data.
- Do not suggest websites, apps, or external sources.
- Do not make assumptions, predictions, or fabricated answers.
- Keep the response clear, natural, and concise.

            
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
                # Provide a more comprehensive response
                answer = """I apologize for the technical difficulty I'm experiencing. Let me explain how I can help you when I'm back to normal operation:

1. Theater Information: I can provide detailed information about movie theaters, including locations, amenities, seating options, and special formats like IMAX or Dolby.

2. Movie Details: I can share comprehensive information about movies, including plot summaries, cast and crew details, reviews, and interesting behind-the-scenes facts.

3. Showtimes and Tickets: I can help you find available showtimes, check seat availability, and provide detailed pricing information, including special discounts and premium format prices.

4. Recommendations: Based on your interests, I can suggest movies that are currently showing and recommend the best viewing experience for each film.

Please try your question again in a moment when our system is fully operational. In the meantime, you can also check our website or mobile app for immediate assistance."""

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


