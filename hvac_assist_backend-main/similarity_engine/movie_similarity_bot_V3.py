import pandas as pd
import numpy as np
from tqdm import tqdm
import warnings
import os
import json
import requests
import re
from typing import Dict, Any, Optional, Tuple
from pinecone import Pinecone, ServerlessSpec
import time

warnings.filterwarnings("ignore")

# ==================== CONFIGURATION ====================
OLLAMA_MODEL = "llama3:8b"
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_K = 5
MIN_SIMILARITY_SCORE = 0.95  # Changed from 0.99 to 0.95
MAX_DAILY_GROWTH_DIFF = 10.0 # Maximum 5% difference per day (increased from 2% for real-world variance)

# ==================== PINECONE CONFIGURATION ====================
PINECONE_API_KEY = "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ"
PINECONE_INDEX_NAME = "movie-similarity-3"  # Changed to v3
PINECONE_NAMESPACE = "movie-growth-vectors-3"  # Changed to v3
VECTOR_DIMENSION = 60

# ==================== GLOBAL VARIABLES ====================
pc = None
pinecone_index = None
embeddings = None
valid_titles = []
metadata = []
df_full = None


# ==================== PINECONE FUNCTIONS ====================
def initialize_pinecone():
    """Initialize Pinecone connection and manage index"""
    global pc, pinecone_index

    try:
        print("🔧 Initializing Pinecone...")
        pc = Pinecone(api_key=PINECONE_API_KEY)

        existing_indexes = pc.list_indexes()
        index_names = [idx.name for idx in existing_indexes]

        if PINECONE_INDEX_NAME in index_names:
            print(f"✓ Index '{PINECONE_INDEX_NAME}' found")
            pinecone_index = pc.Index(PINECONE_INDEX_NAME)

            print(f"🗑️ Deleting old data from namespace '{PINECONE_NAMESPACE}'...")
            pinecone_index.delete(delete_all=True, namespace=PINECONE_NAMESPACE)
            time.sleep(2)
            print("✓ Old data deleted")
        else:
            print(f"📝 Creating new index '{PINECONE_INDEX_NAME}'...")
            pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=VECTOR_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            print("✓ Index created")
            time.sleep(5)
            pinecone_index = pc.Index(PINECONE_INDEX_NAME)

        print(f"✓ Connected to Pinecone index '{PINECONE_INDEX_NAME}'")
        return True

    except Exception as e:
        print(f"❌ Pinecone initialization failed: {e}")
        return False


def upload_vectors_to_pinecone(embeddings_array, titles_list, metadata_list):
    """Upload vectors to Pinecone in batches"""
    global pinecone_index

    try:
        print(f"\n📤 Uploading {len(embeddings_array)} vectors to Pinecone...")

        batch_size = 100
        vectors_to_upsert = []

        for i in range(len(embeddings_array)):
            vector_id = f"movie_{i}"

            vector_metadata = {
                "title": titles_list[i],
                "total_revenue": float(metadata_list[i]["total_revenue"]),
                "active_days": int(metadata_list[i]["active_days"]),
                "dbr_start": int(metadata_list[i]["dbr_start"]),  # NEW
                "dbr_end": int(metadata_list[i]["dbr_end"]),  # NEW
                "index": i
            }

            vectors_to_upsert.append({
                "id": vector_id,
                "values": embeddings_array[i].tolist(),
                "metadata": vector_metadata
            })

            if len(vectors_to_upsert) >= batch_size:
                pinecone_index.upsert(
                    vectors=vectors_to_upsert,
                    namespace=PINECONE_NAMESPACE
                )
                vectors_to_upsert = []

        if vectors_to_upsert:
            pinecone_index.upsert(
                vectors=vectors_to_upsert,
                namespace=PINECONE_NAMESPACE
            )

        print(f"✓ All vectors uploaded to namespace '{PINECONE_NAMESPACE}'")
        time.sleep(2)

        stats = pinecone_index.describe_index_stats()
        namespace_count = stats.namespaces.get(PINECONE_NAMESPACE, {}).get('vector_count', 0)
        print(f"✓ Verified: {namespace_count} vectors in namespace")

        return True

    except Exception as e:
        print(f"❌ Vector upload failed: {e}")
        return False


# ==================== BUILD MOVIE DATABASE ====================
def build_movie_database():
    """Build fresh movie database from CSV"""
    global embeddings, valid_titles, metadata

    try:
        print("\n📂 Loading CSV data...")
        df = pd.read_csv("/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/similarity_engine/AI_Data_Dump_with_Growth.csv", encoding='utf-16', sep='\t')
        df = df.rename(columns={
            'Title': 'title',
            'DBR': 'dbr',
            'Sales Estimate': 'daily_revenue',
            'cumulative_revenue': 'cumulative_revenue'
        })

        df['title'] = df['title'].astype(str).str.strip()
        df = df[['title', 'dbr', 'daily_revenue', 'cumulative_revenue']]

        # Clean daily_revenue
        df.loc[df['daily_revenue'].astype(str).str.contains(r'[eE]', na=False, regex=True), 'daily_revenue'] = 0
        df['daily_revenue'] = df['daily_revenue'].astype(str).str.replace(r'[^0-9.\-]', '', regex=True).str.strip()
        df['daily_revenue'] = pd.to_numeric(df['daily_revenue'], errors='coerce').fillna(0)

        # Clean cumulative_revenue
        df.loc[df['cumulative_revenue'].astype(str).str.contains(r'[eE]', na=False, regex=True), 'cumulative_revenue'] = 0
        df['cumulative_revenue'] = df['cumulative_revenue'].astype(str).str.replace(r'[^0-9.\-]', '', regex=True).str.strip()
        df['cumulative_revenue'] = pd.to_numeric(df['cumulative_revenue'], errors='coerce').fillna(0)

        df['day'] = pd.to_numeric(df['dbr'], errors='coerce').fillna(0).astype(int)

        print("🔨 Building growth curves for ALL movies...")
        curves = []
        valid_titles = []
        metadata = []

        for title, group in tqdm(df.groupby('title'), desc="Processing movies"):
            group = group.groupby('day').agg({
                'daily_revenue': 'sum',
                'cumulative_revenue': 'max'
            }).reset_index().sort_values('day')

            active = group[group['daily_revenue'] > 100]
            if len(active) < 3:
                continue

            daily = active['daily_revenue'].values
            growth = np.diff(daily) / (daily[:-1] + 1e-8) * 100.0
            growth = np.nan_to_num(growth, nan=0.0)
            growth = np.clip(growth, -99, 999)

            target = 60
            if len(growth) > target:
                growth = growth[:target]
            else:
                growth = np.pad(growth, (0, target - len(growth)), 'constant', constant_values=0)

            total_rev = group['cumulative_revenue'].max()
            if total_rev < 1000:
                continue

            # Get DBR range
            dbr_start = int(active['day'].min())
            dbr_end = int(active['day'].max())

            curves.append(growth.astype(np.float32))
            valid_titles.append(title)
            metadata.append({
                'title': title,
                'total_revenue': float(total_rev),
                'active_days': len(active),
                'dbr_start': dbr_start,
                'dbr_end': dbr_end,
                'growth_vector': growth.tolist()
            })

        print(f"✓ Growth curves built for {len(curves)} movies")

        # CRITICAL CHANGE: Remove L2 normalization - keep raw values
        print("🔄 Preparing embeddings (raw growth values)...")
        curves = np.array(curves)
        embeddings = curves.astype('float32')  # NO NORMALIZATION!

        print(f"✓ Fresh embeddings created! Shape: {embeddings.shape}")
        print(f"⚠️  V3 NOTE: Using RAW growth values (no normalization)")
        return True

    except Exception as e:
        print(f"❌ Database build failed: {e}")
        return False


# ==================== DBR OVERLAP DETECTION ====================
def find_dbr_overlap(query_dbr_range: Tuple[int, int], candidate_dbr_range: Tuple[int, int]) -> Tuple[int, int, int]:
    """
    Find overlapping DBR range between two movies
    Returns: (overlap_start, overlap_end, overlap_days)
    """
    query_start, query_end = query_dbr_range
    cand_start, cand_end = candidate_dbr_range

    overlap_start = max(query_start, cand_start)
    overlap_end = min(query_end, cand_end)

    if overlap_start <= overlap_end:
        overlap_days = overlap_end - overlap_start + 1
        return overlap_start, overlap_end, overlap_days
    else:
        return 0, 0, 0  # No overlap


# ==================== DAY-BY-DAY VALIDATION ====================
def validate_daily_growth_similarity(
    query_growth: np.ndarray,
    candidate_growth: np.ndarray,
    max_diff: float = MAX_DAILY_GROWTH_DIFF
) -> Dict[str, Any]:
    """
    Validate that day-by-day growth difference is within threshold
    Returns validation metrics
    """
    # Calculate absolute difference for each day
    daily_diffs = np.abs(query_growth - candidate_growth)
    
    # Find non-zero days (active days)
    active_mask = (query_growth != 0) | (candidate_growth != 0)
    active_diffs = daily_diffs[active_mask]
    
    if len(active_diffs) == 0:
        return {
            'valid': False,
            'max_diff': 0.0,
            'avg_diff': 0.0,
            'days_within_threshold': 0,
            'total_active_days': 0,
            'pass_rate': 0.0
        }
    
    max_daily_diff = float(np.max(active_diffs))
    avg_daily_diff = float(np.mean(active_diffs))
    days_within_threshold = int(np.sum(active_diffs <= max_diff))
    total_active_days = len(active_diffs)
    pass_rate = (days_within_threshold / total_active_days) * 100.0
    
    # Valid if ALL active days are within threshold
    is_valid = max_daily_diff <= max_diff
    
    return {
        'valid': is_valid,
        'max_diff': round(max_daily_diff, 2),
        'avg_diff': round(avg_daily_diff, 2),
        'days_within_threshold': days_within_threshold,
        'total_active_days': total_active_days,
        'pass_rate': round(pass_rate, 1)
    }


# ==================== SYSTEM INITIALIZATION ====================
def initialize_system():
    """Initialize complete system"""
    global df_full

    try:
        if not initialize_pinecone():
            return False

        print("\n🔄 Building FRESH embeddings from CSV (V3 - No Normalization)...\n")
        if not build_movie_database():
            return False

        if not upload_vectors_to_pinecone(embeddings, valid_titles, metadata):
            return False

        df_full = pd.read_csv("/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/similarity_engine/AI_Data_Dump_with_Growth.csv", encoding='utf-16', sep='\t')
        df_full = df_full.rename(columns={
            'Title': 'title',
            'DBR': 'dbr',
            'Sales Estimate': 'daily_revenue',
            'cumulative_revenue': 'cumulative_revenue'
        })
        df_full['title'] = df_full['title'].astype(str).str.strip()

        print(f"\n✅ System ready! {len(valid_titles)} movies indexed")
        print(f"📊 V3 Features: 95% threshold + ±{MAX_DAILY_GROWTH_DIFF}% daily validation\n")
        return True

    except Exception as e:
        print(f"❌ Initialization error: {e}")
        return False


# ==================== IMPROVED MOVIE SEARCH ====================
def normalize_movie_name(name: str) -> str:
    """Normalize movie name for better matching"""
    # Remove special characters, convert to lowercase
    normalized = re.sub(r'[^a-z0-9\s]', '', name.lower())
    # Remove extra spaces
    normalized = ' '.join(normalized.split())
    return normalized


def find_movie_in_database(movie_title: str) -> Optional[str]:
    """Find movie with improved matching logic"""
    if not movie_title:
        return None

    query_normalized = normalize_movie_name(movie_title)
    query_lower = movie_title.lower().strip()

    # Strategy 1: Exact match (case-insensitive)
    for title in valid_titles:
        if title.lower() == query_lower:
            return title

    # Strategy 2: Normalized exact match
    for title in valid_titles:
        if normalize_movie_name(title) == query_normalized:
            return title

    # Strategy 3: Contains match (both ways)
    for title in valid_titles:
        title_lower = title.lower()
        if query_lower in title_lower or title_lower in query_lower:
            return title

    # Strategy 4: Normalized contains match
    for title in valid_titles:
        title_normalized = normalize_movie_name(title)
        if query_normalized in title_normalized or title_normalized in query_normalized:
            return title

    # Strategy 5: Word-by-word match (for names like "3almashi" vs "almashi")
    query_words = set(query_normalized.split())
    best_match = None
    max_overlap = 0

    for title in valid_titles:
        title_words = set(normalize_movie_name(title).split())
        overlap = len(query_words & title_words)

        if overlap > max_overlap and overlap >= min(len(query_words), len(title_words)) * 0.6:
            max_overlap = overlap
            best_match = title

    return best_match


# ==================== SEARCH FUNCTION ====================
def search_similar_movies(movie_title: str, k: int = DEFAULT_K) -> Dict[str, Any]:
    """Search for similar movies using Pinecone with day-by-day validation"""
    try:
        if not movie_title or not isinstance(movie_title, str):
            return {
                "status": "error",
                "message": "Invalid movie title"
            }

        movie_title = movie_title.strip()
        k = max(1, min(int(k), 50))

        # Find movie with improved matching
        matched_title = find_movie_in_database(movie_title)

        if not matched_title:
            return {
                "status": "not_found",
                "message": f"Movie '{movie_title}' not found",
                "suggestion": "Check movie name spelling"
            }

        # Get query movie data
        query_idx = valid_titles.index(matched_title)
        query_metadata = metadata[query_idx]
        query_growth = embeddings[query_idx]  # Raw growth values (no denormalization needed)

        query_dbr_range = (query_metadata['dbr_start'], query_metadata['dbr_end'])
        query_positive_days = int(np.sum(query_growth > 0))
        query_avg_growth = float(np.mean(query_growth[query_growth > 0]) if np.any(query_growth > 0) else 0)

        # Search in Pinecone (get more candidates for filtering)
        query_vector = embeddings[query_idx].tolist()

        search_results = pinecone_index.query(
            vector=query_vector,
            top_k=min(k * 5, len(valid_titles)),  # Get 5x more for filtering
            namespace=PINECONE_NAMESPACE,
            include_metadata=True
        )

        # Process results with day-by-day validation
        results = []
        for match in search_results.matches:
            sim_title = match.metadata.get('title')

            if sim_title == matched_title:
                continue

            score = float(match.score)

            if score < MIN_SIMILARITY_SCORE:
                continue

            sim_idx = int(match.metadata.get('index'))
            sim_metadata = metadata[sim_idx]
            sim_growth = embeddings[sim_idx]  # Raw growth values

            # NEW: Day-by-day validation
            validation = validate_daily_growth_similarity(query_growth, sim_growth, MAX_DAILY_GROWTH_DIFF)
            
            if not validation['valid']:
                continue  # Skip if daily growth difference exceeds threshold

            # DBR overlap analysis
            sim_dbr_range = (sim_metadata['dbr_start'], sim_metadata['dbr_end'])
            overlap_start, overlap_end, overlap_days = find_dbr_overlap(query_dbr_range, sim_dbr_range)

            growth_diff = np.abs(query_growth - sim_growth)
            avg_growth_diff = float(np.mean(growth_diff))

            sim_positive_days = int(np.sum(sim_growth > 0))
            sim_avg_growth = float(np.mean(sim_growth[sim_growth > 0]) if np.any(sim_growth > 0) else 0)

            results.append({
                'title': sim_title,
                'confidence': round(score, 3),
                'total_revenue': sim_metadata['total_revenue'],
                'active_days': sim_metadata['active_days'],
                'analysis': {
                    'avg_growth_difference': round(avg_growth_diff, 2),
                    'positive_growth_days': sim_positive_days,
                    'avg_daily_growth': round(sim_avg_growth, 2),
                    'revenue_comparison': 'higher' if sim_metadata['total_revenue'] > query_metadata['total_revenue'] else 'lower'
                },
                'validation': validation,  # NEW: Day-by-day validation metrics
                'dbr_overlap': {  # NEW: DBR overlap info
                    'overlap_start': overlap_start,
                    'overlap_end': overlap_end,
                    'overlap_days': overlap_days,
                    'query_range': f"DBR {query_dbr_range[0]} to {query_dbr_range[1]}",
                    'candidate_range': f"DBR {sim_dbr_range[0]} to {sim_dbr_range[1]}"
                }
            })

            if len(results) >= k:
                break

        if not results:
            return {
                "status": "no_matches",
                "query_movie": matched_title,
                "message": f"No similar movies found (threshold: {MIN_SIMILARITY_SCORE}, max daily diff: {MAX_DAILY_GROWTH_DIFF}%)"
            }

        return {
            "status": "success",
            "query_movie": matched_title,
            "query_metadata": {
                "total_revenue": query_metadata['total_revenue'],
                "active_days": query_metadata['active_days'],
                "avg_daily_growth": round(query_avg_growth, 2),
                "positive_growth_days": query_positive_days,
                "dbr_range": f"DBR {query_dbr_range[0]} to {query_dbr_range[1]}"
            },
            "similar_movies": results,
            "total_found": len(results)
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Search error: {str(e)}"
        }


# ==================== QUERY PARSING (SIMPLIFIED) ====================
def parse_user_query(query: str) -> Dict[str, Any]:
    """Parse user query without LLM - Direct regex approach"""
    query_lower = query.lower().strip()

    # Extract number/k value
    k_value = DEFAULT_K

    # Pattern 1: "top 10", "top 5", etc.
    match = re.search(r'top\s+(\d+)', query_lower)
    if match:
        k_value = int(match.group(1))

    # Pattern 2: "5 similar", "10 movies", etc.
    match = re.search(r'(\d+)\s+(?:similar|movies?|films?)', query_lower)
    if match:
        k_value = int(match.group(1))

    # Pattern 3: Just a number at start "10 movies like X"
    match = re.search(r'^(\d+)', query_lower)
    if match:
        k_value = int(match.group(1))

    # Extract movie name
    movie_name = query

    # Remove common phrases
    patterns_to_remove = [
        r'(?:find|show|give|get|search)\s+(?:me\s+)?',
        r'(?:similar|like|comparable)\s+(?:to|with)?\s*',
        r'(?:movies?|films?)\s+',
        r'top\s+\d+\s+',
        r'^\d+\s+',
        r'which\s+(?:movie|film)?\s*(?:is)?\s*',  # NEW: Handle 'which movie is'
        r'what\s+(?:movie|film)?\s*(?:is)?\s*',   # NEW: Handle 'what movie is'
        r'is\s+(?:similar\s+to)?\s*',              # NEW: Handle 'is similar to'
        r'performed\s+like\s+',
    ]

    for pattern in patterns_to_remove:
        movie_name = re.sub(pattern, '', movie_name, flags=re.IGNORECASE)

    movie_name = movie_name.strip()

    # If still no movie name extracted, use original query
    if not movie_name or len(movie_name) < 2:
        # Try to find quoted text
        quoted = re.findall(r'["\']([^"\']+)["\']', query)
        if quoted:
            movie_name = quoted[0]
        else:
            movie_name = query

    return {
        "movie_title": movie_name,
        "k": k_value
    }


# ==================== ANALYSIS GENERATION ====================
def generate_detailed_analysis(search_results: Dict[str, Any]) -> str:
    """Generate detailed analysis using Ollama LLM"""
    try:
        query_movie = search_results['query_movie']
        query_meta = search_results['query_metadata']
        similar_movies = search_results['similar_movies']

        # Prepare context for LLM
        context = f"""Analyze these box office performance similarities (V3 - Enhanced Matching):

QUERY MOVIE: {query_movie}
- Total Revenue: ${query_meta['total_revenue']:,.0f}
- Active Days: {query_meta['active_days']}
- Average Daily Growth Rate: {query_meta['avg_daily_growth']}%
- Days with Positive Growth: {query_meta['positive_growth_days']}
- {query_meta['dbr_range']}

SIMILAR MOVIES FOUND (All within ±{MAX_DAILY_GROWTH_DIFF}% daily growth):
"""

        for i, movie in enumerate(similar_movies[:5], 1):  # Top 5 only for analysis
            context += f"\n{i}. {movie['title']}"
            context += f"\n   - Similarity Score: {movie['confidence']} ({int(movie['confidence']*100)}%)"
            context += f"\n   - Total Revenue: ${movie['total_revenue']:,.0f}"
            context += f"\n   - Active Days: {movie['active_days']}"
            context += f"\n   - Avg Daily Growth: {movie['analysis']['avg_daily_growth']}%"
            context += f"\n   - Max Daily Difference: {movie['validation']['max_diff']}%"
            context += f"\n   - Avg Daily Difference: {movie['validation']['avg_diff']}%"
            context += f"\n   - Days Matching (±{MAX_DAILY_GROWTH_DIFF}%): {movie['validation']['days_within_threshold']}/{movie['validation']['total_active_days']}"
            context += f"\n   - DBR Overlap: {movie['dbr_overlap']['overlap_days']} days"
            context += f"\n   - Revenue Comparison: {movie['analysis']['revenue_comparison']} than query movie\n"

        prompt = f"""{context}

Your task as a box office analyst:
1. Explain WHY these movies are similar to "{query_movie}"
2. Identify the KEY PATTERNS they share (opening performance, sustained growth, decay rate)
3. Mention specific similarities in:
   - Growth trajectories (similar curves at which days/weeks)
   - Revenue patterns (front-loaded vs long-tail)
   - Active theatrical run length
   - Performance consistency
4. For each similar movie, provide 1-2 sentences explaining the specific match
5. Highlight that V3 ensures day-by-day growth differences are within {MAX_DAILY_GROWTH_DIFF}%
6. End with an overall summary of what these similarities tell us

Be specific with numbers and percentages. Write in a clear, professional tone.

DETAILED ANALYSIS:"""

        response = requests.post(
            OLLAMA_URL,
            json={
                'model': OLLAMA_MODEL,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': 0.5,
                    'num_predict': 800
                }
            },
            timeout=60
        )

        if response.status_code == 200:
            return response.json()['response'].strip()
        else:
            return "Analysis generation unavailable."

    except requests.exceptions.ConnectionError:
        return "⚠️ Ollama not running. Start with: ollama serve"
    except Exception as e:
        return f"⚠️ Analysis generation error: {str(e)}"


# ==================== FORMAT OUTPUT ====================
def format_results(search_results: Dict[str, Any]) -> str:
    """Format search results for display"""
    if search_results["status"] != "success":
        return f"❌ {search_results.get('message', 'Search failed')}"

    query_movie = search_results['query_movie']
    query_meta = search_results['query_metadata']

    output = f"\n🎬 Query Movie: {query_movie}\n"
    output += f"💰 Total Revenue: ${query_meta['total_revenue']:,.0f}\n"
    output += f"📅 Active Days: {query_meta['active_days']}\n"
    # output += f"📈 Avg Growth: {query_meta['avg_daily_growth']}%\n"
    output += f"📍 {query_meta['dbr_range']}\n"
    
    output += f"\n{'='*70}\n"
    output += f"📊 Found {search_results['total_found']} Similar Movies (V3 - Enhanced):\n"
    output += f"{'='*70}\n\n"

    for i, movie in enumerate(search_results['similar_movies'], 1):
        confidence_score = movie['confidence']
        confidence_percent = int(confidence_score * 100)

        output += f"{i}. {movie['title']}\n"
        output += f"   Similarity: {confidence_percent}% (confidence: {confidence_score})\n"
        output += f"   💰 Revenue: ${movie['total_revenue']:,.0f} ({movie['analysis']['revenue_comparison']})\n"
        output += f"   📅 Active Days: {movie['active_days']}\n"
        # output += f"   📈 Avg Growth: {movie['analysis']['avg_daily_growth']}%\n"
        output += f"   ✅ Max Daily Diff: {movie['validation']['max_diff']}% (within ±{MAX_DAILY_GROWTH_DIFF}%)\n"
        output += f"   ✅ Avg Daily Diff: {movie['validation']['avg_diff']}%\n"
        output += f"   📍 DBR Overlap: {movie['dbr_overlap']['overlap_days']} days\n"
        output += f"   → Precise day-by-day growth pattern match!\n\n"

    return output


# ==================== MAIN INTERFACE ====================
def ask(user_query: str) -> Dict[str, Any]:
    """Main interface - V3 with enhanced day-by-day validation"""
    print(f"\n{'='*70}")
    print(f"💬 USER: {user_query}")
    print('='*70 + "\n")

    try:
        # Parse query directly (no LLM)
        parsed = parse_user_query(user_query)
        movie_title = parsed["movie_title"]
        k = parsed["k"]

        print(f"🔍 Searching for {k} movies similar to: '{movie_title}'")
        print(f"📊 V3 Filters: 95% similarity + max ±{MAX_DAILY_GROWTH_DIFF}% daily difference\n")

        # Search
        search_results = search_similar_movies(movie_title, k)

        if search_results["status"] != "success":
            error_msg = search_results.get('message', 'Search failed')
            print(f"❌ {error_msg}\n")
            return {"error": error_msg, "message": ""}

        # Format output
        output = format_results(search_results)
        print(output)

        # Generate detailed analysis
        print("="*70)
        print("🤖 DETAILED ANALYSIS:")
        print("="*70 + "\n")
        print("Generating detailed analysis...\n")

        analysis = generate_detailed_analysis(search_results)
        print(analysis)

        print('\n' + '='*70)

        # Combine for return
        full_output = output + "\n" + "="*70 + "\n" + "DETAILED ANALYSIS:\n" + "="*70 + "\n\n" + analysis

        return {"message": full_output, "error": ""}

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"❌ {error_msg}\n")
        return {"error": error_msg, "message": ""}


# ==================== AUTO-INITIALIZE ====================
# initialize_system()

# ==================== MAIN LOOP ====================
def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("🎬 MOVIE SIMILARITY SEARCH V3 - ENHANCED MATCHING")
    print("="*70)

    if not initialize_system():
        print("\n❌ Initialization failed. Exiting.")
        return

    print(f"\n📊 Database: {len(valid_titles)} movies")
    print(f"🔗 Vector DB: Pinecone ({PINECONE_INDEX_NAME})")
    print(f"✅ V3 Features:")
    print(f"   • 95% similarity threshold (vs 99% in V2)")
    print(f"   • Max ±{MAX_DAILY_GROWTH_DIFF}% daily growth difference")
    print(f"   • DBR overlap detection")
    print(f"   • Raw growth values (no normalization)")
    print("\n💡 Example queries:")
    print('   • "Find similar movies to Avatar"')
    print('   • "Top 10 movies like Titanic"')
    print('   • "Show me 5 movies like Inception"')
    print('   • "3almashi similar movies"')
    print("\n" + "="*70 + "\n")

    while True:
        try:
            user_input = input("💬 Your question (or 'quit'): ").strip()

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break

            if not user_input:
                print("⚠️ Please enter a question.\n")
                continue

            ask(user_input)

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    main()
