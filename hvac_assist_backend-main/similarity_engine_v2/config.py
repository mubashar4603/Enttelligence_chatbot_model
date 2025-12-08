"""
Configuration for High-Performance Movie Similarity Engine V2
"""

import os

# ==================== PATHS ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DATA_PATH = os.path.join(os.path.dirname(BASE_DIR), "similarity_engine", "AI_Data_Dump_with_Growth.csv")
# DATA_PATH = os.path.join(os.path.dirname(BASE_DIR), "similarity_engine_v2", "AI_Data_Dump_1205.csv")
DATA_PATH = os.path.join(os.path.dirname(BASE_DIR), "similarity_engine_v2", "AI_Data_Dump_1203_with_Growth_CAL.csv")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
GRAPHS_DIR = os.path.join(BASE_DIR, "graphs")

# Ensure directories exist
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(GRAPHS_DIR, exist_ok=True)

# ==================== DATA PREPROCESSING ====================
MIN_REVENUE_THRESHOLD = 0    # Minimum daily revenue to consider as "active day"
MIN_ACTIVE_DAYS = 3          # Minimum active days for a movie to be included
MIN_TOTAL_REVENUE = 1000     # Minimum total revenue for a movie to be included

# ==================== VECTOR GENERATION ====================
VECTOR_DIMENSION = 60        # Fixed vector dimension for FAISS
USE_GAUSSIAN_SMOOTHING = True
SMOOTHING_SIGMA = 1.0        # Gaussian smoothing parameter
USE_L2_NORMALIZATION = True  # Normalize vectors for cosine similarity

# ==================== FAISS INDEX CONFIGURATION ====================
# For datasets < 10K movies, use Flat index
# For datasets >= 10K movies, use IVF-PQ index

# IVF Parameters
IVF_NLIST_RATIO = 0.01       # nlist = sqrt(N) or N * ratio, whichever is smaller
IVF_NLIST_MIN = 100          # Minimum number of clusters
IVF_NLIST_MAX = 4096         # Maximum number of clusters
IVF_NPROBE = 32              # Number of clusters to search (higher = more accurate, slower)

# PQ Parameters
PQ_M = 10                    # Number of subvectors (must divide VECTOR_DIMENSION, 60/10=6)
PQ_NBITS = 8                 # Bits per subvector

# Index Selection Threshold
USE_IVF_THRESHOLD = 10000    # Use IVF-PQ if dataset has >= this many movies

# ==================== SEARCH PARAMETERS ====================
DEFAULT_K = 5                # Default number of similar movies to return
MIN_SIMILARITY_SCORE = 85    # Minimum similarity score (0-100)
MIN_DBR_OVERLAP_DAYS = 5     # Minimum overlapping DBR days required

# FAISS search parameters
FAISS_SEARCH_K_MULTIPLIER = 20  # Fetch K * multiplier candidates for filtering

# ==================== SIMILARITY METRICS ====================
# Weights for multi-metric similarity score (must sum to 1.0)
METRIC_WEIGHTS = {
    'cosine': 0.40,          # Cosine similarity
    'correlation': 0.30,     # Pearson correlation
    'mape': 0.20,            # Mean Absolute Percentage Error
    'coverage': 0.10         # DBR overlap coverage bonus
}

# Tolerance thresholds for daily growth differences
TOLERANCE_THRESHOLDS = [1.0, 2.0, 5.0, 10.0]  # Percentage differences to track

# ==================== DBR MATCHING MODES ====================
ENABLE_PERCENTAGE_MATCHING = True  # Toggle between percentage and consecutive count modes
MIN_PERCENTAGE_THRESHOLD = 50.0      # Minimum % of DBRs that must match (used in percentage mode)

# ==================== CACHING ====================
ENABLE_CACHE = True
MAX_CACHE_SIZE = 10000       # Maximum number of cached search results
CACHE_FILES = {
    'embeddings': os.path.join(CACHE_DIR, 'embeddings.npy'),
    'metadata': os.path.join(CACHE_DIR, 'metadata.pkl'),
    'movies_db': os.path.join(CACHE_DIR, 'movies_db.pkl'),
    'index_fast': os.path.join(CACHE_DIR, 'index_fast.faiss'),
    'index_exact': os.path.join(CACHE_DIR, 'index_exact.faiss'),
}

# ==================== PERFORMANCE ====================
USE_PARALLEL_SEARCH = False  # Enable parallel index search (experimental)
NUM_WORKERS = 3              # Number of parallel workers

# ==================== OUTPUT ====================
GENERATE_GRAPHS = True       # Generate similarity graphs
GRAPH_DPI = 150              # Graph resolution
GRAPH_FIGSIZE = (12, 6)      # Graph size in inches

# Verbosity
VERBOSE = True               # Print detailed progress information
DEBUG = False                # Enable debug logging

# ==================== LLM CONFIGURATION ====================
OLLAMA_MODEL = "llama3:8b"
OLLAMA_URL = "http://localhost:11434/api/generate"
ENABLE_LLM_ANALYSIS = True

# ==================== VALIDATION ====================
def validate_config():
    """Validate configuration parameters"""
    assert VECTOR_DIMENSION % PQ_M == 0, f"VECTOR_DIMENSION ({VECTOR_DIMENSION}) must be divisible by PQ_M ({PQ_M})"
    
    # Use tolerance for floating-point comparison
    weights_sum = sum(METRIC_WEIGHTS.values())
    assert abs(weights_sum - 1.0) < 1e-6, f"METRIC_WEIGHTS must sum to 1.0, got {weights_sum}"
    
    assert 0 <= MIN_SIMILARITY_SCORE <= 100, f"MIN_SIMILARITY_SCORE must be between 0 and 100"
    assert os.path.exists(DATA_PATH), f"Data file not found: {DATA_PATH}"
    
    if VERBOSE:
        print("✓ Configuration validated successfully")

# Validate on import
validate_config()
