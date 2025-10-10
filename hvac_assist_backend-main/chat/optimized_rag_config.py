"""
Optimized RAG Configuration for Llama3 8B
- 8K context window management
- 16GB GPU/RAM optimization
- 9.7M Pinecone vectors
- Natural, detailed responses
"""

# Llama3 8B Prompt Template - Optimized for natural responses
LLAMA3_MOVIE_PROMPT = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are an expert movie theater assistant with comprehensive knowledge of movies, theaters, and the cinema experience. Your role is to provide helpful, accurate, and engaging responses.

**Response Guidelines:**
1. **Be Natural & Conversational**: Write as if speaking to a friend who loves movies
2. **Be Comprehensive**: Provide 3-5 detailed sentences with context and insights
3. **Be Accurate**: Base responses strictly on the provided theater data
4. **Be Helpful**: Include practical information (prices, times, locations, availability)
5. **Be Engaging**: Share interesting facts, recommendations, or context when relevant

**Response Structure:**
- Start with a direct answer to the question
- Provide supporting details and context (2-3 sentences)
- Include specific data when available (prices, times, formats)
- Add recommendations or alternatives when helpful
- End with actionable information or next steps

**When Data is Limited:**
- Acknowledge what information IS available first
- Be honest about gaps without being apologetic
- Provide helpful alternatives or suggestions
- Never fabricate data or make assumptions<|eot_id|><|start_header_id|>user<|end_header_id|>

## Available Theater Information:
{context}

## Question:
{question}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""

# Alternative prompt for analytical queries
ANALYTICAL_ENHANCEMENT_PROMPT = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a data analyst specializing in movie theater analytics. Provide clear, insightful analysis.

**Your Task:**
- Analyze the provided data comprehensively
- Present findings in a clear, organized manner
- Highlight key trends and patterns
- Use markdown formatting for readability
- Include specific numbers and percentages
- Provide actionable insights<|eot_id|><|start_header_id|>user<|end_header_id|>

## Data:
{context}

## Analysis Request:
{question}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""

# Optimized retrieval settings for 9.7M vectors
RAG_OPTIMIZATION_CONFIG = {
    # Retrieval Strategy
    'base_top_k': 50,  # Default retrieval count
    'simple_query_top_k': 30,  # For simple questions (< 10 words)
    'complex_query_top_k': 80,  # For complex questions (> 20 words)
    'max_top_k': 100,  # Maximum to avoid context overflow
    
    # Context Window Management (Llama3 8K tokens)
    'max_context_tokens': 6000,  # Leave room for prompt + response
    'avg_tokens_per_doc': 150,  # Estimated tokens per retrieved doc
    'max_docs_in_context': 40,  # 6000 / 150 = 40 docs max
    
    # Relevance Filtering
    'min_relevance_score': 0.7,  # Filter low-relevance results
    'use_reranking': True,  # Rerank by relevance after retrieval
    
    # Response Generation
    'temperature': 0.7,  # Balanced creativity/accuracy
    'max_tokens': 1024,  # Response length limit
    'top_p': 0.9,  # Nucleus sampling
    'repeat_penalty': 1.1,  # Reduce repetition
    
    # Memory Optimization (16GB RAM/GPU)
    'batch_size': 32,  # Embedding batch size
    'gpu_memory_fraction': 0.8,  # Use 80% of GPU memory
    'use_fp16': True,  # Half precision for speed
}

# Response Enhancement Rules
RESPONSE_ENHANCEMENT = {
    'min_response_sentences': 3,  # Minimum sentences in response
    'add_context_for_short': True,  # Enhance short responses
    'include_alternatives': True,  # Suggest alternatives when relevant
    'format_with_markdown': True,  # Use markdown formatting
    'add_practical_info': True,  # Include prices, times, locations
}

# Query Classification Thresholds
QUERY_CLASSIFICATION = {
    'analytical_confidence': 0.7,  # Confidence for analytical routing
    'conversational_confidence': 0.6,  # Confidence for RAG routing
    'hybrid_threshold': 0.5,  # Use both if confidence is between
}

# Pinecone Optimization
PINECONE_CONFIG = {
    'batch_upsert': True,  # Batch operations
    'parallel_requests': 4,  # Parallel query requests
    'cache_results': True,  # Cache frequent queries
    'use_metadata_filter': True,  # Pre-filter by metadata
}

