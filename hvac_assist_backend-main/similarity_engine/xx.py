import pandas as pd
import numpy as np
from tqdm import tqdm
import warnings
import os
import json
import requests
import re
import time
from typing import Dict, Any, Optional, List, Tuple
from pinecone import Pinecone, ServerlessSpec
from scipy.ndimage import gaussian_filter1d  # Added for statistical smoothing

# Configure Logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore")

# ==================== CONFIGURATION CLASS ====================
class Config:
    # LLM Settings
    OLLAMA_MODEL = "llama3:8b"
    OLLAMA_URL = "http://localhost:11434/api/generate"
    
    # Vector DB Settings
    # In production, load these from os.environ
    PINECONE_API_KEY = "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ" 
    PINECONE_INDEX_NAME = "movie-similarity-55"
    PINECONE_NAMESPACE = "movie-growth-vectors-55"
    VECTOR_DIMENSION = 60
    
    # Algorithm Hyperparameters
    DEFAULT_K = 5
    MIN_SIMILARITY_SCORE = 0.85 # Adjusted for smoothed curves
    SMOOTHING_SIGMA = 1.0 # Standard deviation for Gaussian kernel
    
    # Data Paths
    DATA_PATH = "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/similarity_engine/AI_Data_Dump_with_Growth.csv"

# ==================== CORE ENGINE ====================
class BoxOfficeRAGSystem:
    def __init__(self):
        self.pc = None
        self.index = None
        self.df_full = None
        self.embeddings = None
        self.valid_titles = []
        self.metadata = []
        self._initialize_pinecone()

    def _initialize_pinecone(self):
        """Initialize Pinecone with robust error handling."""
        try:
            logger.info("🔧 Initializing Pinecone Client...")
            self.pc = Pinecone(api_key=Config.PINECONE_API_KEY)
            
            existing_indexes = [idx.name for idx in self.pc.list_indexes()]

            if Config.PINECONE_INDEX_NAME not in existing_indexes:
                logger.info(f"📝 Creating new index '{Config.PINECONE_INDEX_NAME}'...")
                self.pc.create_index(
                    name=Config.PINECONE_INDEX_NAME,
                    dimension=Config.VECTOR_DIMENSION,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
                time.sleep(10) # Wait for initialization
            
            self.index = self.pc.Index(Config.PINECONE_INDEX_NAME)
            logger.info(f"✓ Connected to Index: {Config.PINECONE_INDEX_NAME}")
            
        except Exception as e:
            logger.error(f"❌ Pinecone Error: {e}")
            raise

    def preprocess_growth_curve(self, daily_revenue: np.ndarray) -> np.ndarray:
        """
        Stats Engineering: Converts daily revenue to a smoothed growth curve.
        Raw % change is too noisy. We use Gaussian Smoothing to capture the 'shape' of the run.
        """
        # 1. Calculate Growth Rate
        # Add epsilon to prevent division by zero
        growth = np.diff(daily_revenue) / (daily_revenue[:-1] + 1.0) * 100.0
        
        # 2. Clip outliers (e.g., opening day explosions or data errors)
        growth = np.clip(growth, -99, 500)
        
        # 3. Handle Length (Truncate or Pad)
        target = Config.VECTOR_DIMENSION
        if len(growth) > target:
            growth = growth[:target]
        else:
            growth = np.pad(growth, (0, target - len(growth)), 'constant', constant_values=0)
            
        # 4. Statistical Smoothing (The ML Engineer touch)
        # This removes day-to-day noise to focus on the trend (Legs vs Front-loaded)
        smoothed_growth = gaussian_filter1d(growth, sigma=Config.SMOOTHING_SIGMA)
        
        # 5. L2 Normalization (Crucial for Cosine Similarity)
        # Makes the magnitude irrelevant, focuses on the "Shape" of the curve
        norm = np.linalg.norm(smoothed_growth)
        if norm == 0:
            return smoothed_growth
        return (smoothed_growth / norm).astype(np.float32)

    def load_and_process_data(self, force_rebuild=False):
        """Loads CSV, generates embeddings, and optionally upserts to Pinecone."""
        try:
            logger.info("📂 Loading Data...")
            # Optimized CSV loading
            df = pd.read_csv(Config.DATA_PATH, encoding='utf-16', sep='\t')
            
            # Cleaning Map
            col_map = {
                'Title': 'title', 
                'DBR': 'day', 
                'Sales Estimate': 'daily_revenue',
                'cumulative_revenue': 'cumulative_revenue'
            }
            df = df.rename(columns=col_map)
            df['title'] = df['title'].astype(str).str.strip()
            
            # Vectorized cleaning
            for col in ['daily_revenue', 'cumulative_revenue']:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(r'[^0-9.\-]', '', regex=True), 
                    errors='coerce'
                ).fillna(0)
            
            df['day'] = pd.to_numeric(df['day'], errors='coerce').fillna(0).astype(int)
            
            # Store full DF for retrieval later
            self.df_full = df[['title', 'day', 'daily_revenue', 'cumulative_revenue']]

            # Check if we need to process
            stats = self.index.describe_index_stats()
            ns_count = stats.namespaces.get(Config.PINECONE_NAMESPACE, {}).get('vector_count', 0)
            
            if ns_count > 0 and not force_rebuild:
                logger.info(f"✓ Index populated with {ns_count} vectors. Skipping processing.")
                # We still need to load local metadata for lookup mapping
                self._build_local_metadata_only(df)
                return True

            logger.info("🔨 Building Growth Curves & Embeddings...")
            
            embeddings_list = []
            
            # GroupBy is expensive, do it once
            grouped = df.groupby('title')
            
            for title, group in tqdm(grouped, desc="Processing Movies"):
                group = group.sort_values('day')
                
                # Filter trivial data
                if group['cumulative_revenue'].max() < 1000 or len(group) < 3:
                    continue
                    
                daily_revs = group['daily_revenue'].values
                
                # ML Engineering: Generate robust embedding
                vector = self.preprocess_growth_curve(daily_revs)
                
                # Validation checks
                if np.isnan(vector).any():
                    continue

                embeddings_list.append(vector)
                self.valid_titles.append(title)
                self.metadata.append({
                    'title': title,
                    'total_revenue': float(group['cumulative_revenue'].max()),
                    'active_days': int(len(group))
                })

            self.embeddings = np.array(embeddings_list)
            
            # Batch Upload
            self._upload_vectors()
            return True
            
        except Exception as e:
            logger.error(f"❌ Data Pipeline Failed: {e}")
            return False

    def _build_local_metadata_only(self, df):
        """Rebuilds local lists if vectors exist in DB but memory is empty."""
        logger.info("🔄 Rebuilding local metadata map...")
        grouped = df.groupby('title')['cumulative_revenue'].agg(['max', 'count'])
        for title, row in grouped.iterrows():
            if row['max'] > 1000 and row['count'] >= 3:
                self.valid_titles.append(title)
                self.metadata.append({
                    'title': title,
                    'total_revenue': float(row['max']),
                    'active_days': int(row['count'])
                })
        # Note: We don't rebuild self.embeddings here to save RAM, 
        # as we rely on Pinecone for search.
    def _upload_vectors(self):
        """Efficient batch upload with Error Handling for new Namespaces."""
        logger.info(f"📤 Uploading {len(self.embeddings)} vectors...")
        
        batch_size = 100
        
        # --- FIX STARTS HERE ---
        # Pehle purana data delete karein, lekin agar namespace naya hai to error ignore karein
        try:
            self.index.delete(delete_all=True, namespace=Config.PINECONE_NAMESPACE)
            logger.info(f"🗑️ Cleared existing data in namespace: {Config.PINECONE_NAMESPACE}")
        except Exception as e:
            # Agar 404 error aye (Namespace not found), to iska matlab ye naya namespace hai.
            # Hum is error ko ignore kar ke aage badh jayenge.
            if "not found" in str(e).lower() or "404" in str(e):
                logger.info(f"ℹ️ Namespace '{Config.PINECONE_NAMESPACE}' is new. Skipping deletion.")
            else:
                # Agar koi aur error hai (connection etc), to crash karo
                logger.error(f"❌ Error clearing namespace: {e}")
                raise e
        # --- FIX ENDS HERE ---
        
        for i in range(0, len(self.embeddings), batch_size):
            i_end = min(i + batch_size, len(self.embeddings))
            batch_vectors = []
            
            for j in range(i, i_end):
                # Ensure JSON serializable types
                meta = self.metadata[j]
                batch_vectors.append({
                    "id": f"movie_{j}", 
                    "values": self.embeddings[j].tolist(),
                    "metadata": {
                        "title": meta['title'],
                        "total_revenue": meta['total_revenue'],
                        "active_days": meta['active_days'],
                        "index": j
                    }
                })
            
            # Upsert automatically creates the namespace if it doesn't exist
            self.index.upsert(vectors=batch_vectors, namespace=Config.PINECONE_NAMESPACE)
            
        logger.info("✓ Upload Complete")
    def find_movie_fuzzy(self, query: str) -> Optional[str]:
        """Robust string matching."""
        if not query: return None
        
        query_norm = re.sub(r'[^a-z0-9]', '', query.lower())
        
        # 1. Exact map
        title_map = {re.sub(r'[^a-z0-9]', '', t.lower()): t for t in self.valid_titles}
        if query_norm in title_map:
            return title_map[query_norm]
            
        # 2. Contains match
        for key, val in title_map.items():
            if query_norm in key:
                return val
                
        return None

    def search(self, query: str, k: int = 5):
        """Semantic Search Pipeline."""
        # 1. Parse Query
        parsed = self._parse_query_intent(query)
        target_movie = self.find_movie_fuzzy(parsed['movie'])
        k = parsed['k']

        if not target_movie:
            return {"status": "error", "message": f"Movie '{parsed['movie']}' not found."}

        # 2. Get Query Vector
        # We need the vector. If we loaded from CSV, we have it. 
        # If we didn't (cached mode), we calculate it on the fly from df_full.
        query_df = self.df_full[self.df_full['title'] == target_movie].sort_values('day')
        query_vector = self.preprocess_growth_curve(query_df['daily_revenue'].values).tolist()

        # 3. Pinecone Search
        results = self.index.query(
            vector=query_vector,
            top_k=k+1, # Fetch +1 to exclude self
            namespace=Config.PINECONE_NAMESPACE,
            include_metadata=True
        )

        matches = []
        for match in results.matches:
            if match.metadata['title'] == target_movie:
                continue
            matches.append({
                "title": match.metadata['title'],
                "score": match.score,
                "metadata": match.metadata
            })

        return {
            "status": "success",
            "query_movie": target_movie,
            "matches": matches[:k],
            "query_metadata": {
                "total": query_df['cumulative_revenue'].max(),
                "days": len(query_df)
            }
        }

    def _parse_query_intent(self, query: str) -> dict:
        """Heuristic parser."""
        k = Config.DEFAULT_K
        # Extract number
        num_match = re.search(r'\b(\d+)\b', query)
        if num_match:
            val = int(num_match.group(1))
            if 1 <= val <= 20: k = val
            
        # Remove junk words
        junk = r'(top|similar|movies?|like|show|find|me|analysis|stats|predictions|for)'
        clean_q = re.sub(junk, '', query, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r'\s+', ' ', clean_q)
        
        return {"movie": clean_q, "k": k}

    def generate_rag_analysis(self, search_result: Dict) -> str:
        """Generates ML-driven analysis using Ollama."""
        if search_result['status'] != 'success':
            return "Analysis cannot be generated due to search failure."

        q_meta = search_result['query_metadata']
        
        # Construct RAG Context
        context_str = f"Target Movie: {search_result['query_movie']} (Total Rev: ${q_meta['total']:,.0f})\n"
        context_str += "Similar Patterns Found:\n"
        
        for m in search_result['matches']:
            context_str += f"- {m['title']}: Similarity {m['score']:.2f}, Rev ${m['metadata']['total_revenue']:,.0f}\n"

        prompt = f"""
        Act as a Senior Data Scientist specializing in Theatrical Distribution.
        Analyze the following similarity search results based on revenue growth curves (normalized time-series).

        DATA:
        {context_str}

        TASK:
        1. Compare the 'Target Movie' to the similar matches.
        2. Based on the fact that these movies share similar 'Growth Curves' (legs/staying power), predict if the target movie was a front-loaded blockbuster or a sleeper hit.
        3. Provide a concise financial risk assessment.

        RESPONSE FORMAT:
        Bullet points with professional financial terminology.
        """

        try:
            resp = requests.post(
                Config.OLLAMA_URL,
                json={
                    "model": Config.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3} # Lower temp for analytical tasks
                },
                timeout=30
            )
            return resp.json()['response']
        except Exception as e:
            return f"⚠️ LLM Analysis unavailable: {e}"

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    # Initialize System
    engine = BoxOfficeRAGSystem()
    
    # Load Data (Set force_rebuild=True if CSV changed)
    engine.load_and_process_data(force_rebuild=True)
    
    while True:
        try:
            print("\n" + "="*50)
            user_input = input("🤖 Ask about a movie (or 'exit'): ")
            
            if user_input.lower() in ['exit', 'quit']:
                break
                
            print(f"⏳ Analyzing '{user_input}'...")
            
            # 1. Retrieve
            results = engine.search(user_input)
            
            if results['status'] == 'error':
                print(f"❌ {results['message']}")
                continue
                
            # 2. Display Stats
            print(f"\n🎬 MATCHES FOR: {results['query_movie']}")
            print(f"{'Movie Title':<30} | {'Sim Score':<10} | {'Revenue'}")
            print("-" * 60)
            for m in results['matches']:
                print(f"{m['title']:<30} | {m['score']:.4f}     | ${m['metadata']['total_revenue']:,.0f}")
                
            # 3. Generate Analysis
            print("\n🧠 AI ANALYSIS:")
            analysis = engine.generate_rag_analysis(results)
            print(analysis)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Runtime Error: {e}")