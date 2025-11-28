"""
Main Entry Point for Movie Similarity Engine V2
High-Performance Scalable Architecture
"""

import os
import pickle
import numpy as np
import json
from typing import Dict, Any, Optional
import config

# Import core modules
from core.data_loader import DataLoader
from core.preprocessor import MoviePreprocessor
from core.vector_builder import VectorBuilder
from core.dbr_matcher import DBRMatcher

# Import search modules
from search.faiss_indexer import FAISSIndexer
from search.search_engine import SearchEngine

class MovieSimilarityEngine:
    """Main class for movie similarity search"""
    
    def __init__(self, force_rebuild: bool = False):
        """
        Initialize the similarity engine
        
        Args:
            force_rebuild: Force rebuild of indexes even if cache exists
        """
        self.force_rebuild = force_rebuild
        self.search_engine = None
        self.movies_db = None
        self.embeddings = None
        self.metadata = None
        
        # Initialize
        self._initialize()
    
    def _initialize(self):
        """Initialize or load the system"""
        # Check if cache exists
        cache_exists = self._check_cache()
        
        if cache_exists and not self.force_rebuild:
            if config.VERBOSE:
                print("\n📦 Loading from cache...")
            self._load_from_cache()
        else:
            if config.VERBOSE:
                print("\n🔨 Building fresh indexes...")
            self._build_from_scratch()
            self._save_to_cache()
        
        if config.VERBOSE:
            print("\n✅ System ready!")
            print(f"   Total movies indexed: {len(self.metadata)}")
            print(f"   Vector dimension: {config.VECTOR_DIMENSION}")
            print(f"   Gaussian smoothing: {'Enabled' if config.USE_GAUSSIAN_SMOOTHING else 'Disabled'}")
    
    def _check_cache(self) -> bool:
        """Check if all cache files exist"""
        required_files = [
            config.CACHE_FILES['embeddings'],
            config.CACHE_FILES['metadata'],
            config.CACHE_FILES['movies_db'],
            config.CACHE_FILES['index_exact']
        ]
        
        return all(os.path.exists(f) for f in required_files)
    
    def _build_from_scratch(self):
        """Build everything from scratch"""
        # Step 1: Load data
        loader = DataLoader()
        df = loader.load()
        
        # Step 2: Preprocess movies
        preprocessor = MoviePreprocessor(df)
        self.movies_db = preprocessor.process_all_movies()
        
        # Step 3: Build vectors
        builder = VectorBuilder(self.movies_db)
        self.embeddings, self.metadata = builder.build_embeddings(
            use_smoothed=config.USE_GAUSSIAN_SMOOTHING
        )
        
        # Step 4: Build FAISS indexes
        indexer = FAISSIndexer()
        fast_idx, exact_idx = indexer.build_indexes(self.embeddings)
        
        # Step 5: Build DBR matcher
        dbr_matcher = DBRMatcher(self.metadata)
        
        # Step 6: Create search engine
        self.search_engine = SearchEngine(
            indexer, dbr_matcher, self.movies_db,
            self.embeddings, self.metadata
        )
    
    def _save_to_cache(self):
        """Save to cache"""
        if config.VERBOSE:
            print("\n💾 Saving to cache...")
        
        # Save embeddings
        np.save(config.CACHE_FILES['embeddings'], self.embeddings)
        
        # Save metadata
        with open(config.CACHE_FILES['metadata'], 'wb') as f:
            pickle.dump(self.metadata, f)
        
        # Save movies_db
        with open(config.CACHE_FILES['movies_db'], 'wb') as f:
            pickle.dump(self.movies_db, f)
        
        # Save FAISS indexes
        self.search_engine.indexer.save_indexes()
        
        if config.VERBOSE:
            print("   ✓ Cache saved")
    
    def _load_from_cache(self):
        """Load from cache"""
        # Load embeddings
        self.embeddings = np.load(config.CACHE_FILES['embeddings'])
        
        # Load metadata
        with open(config.CACHE_FILES['metadata'], 'rb') as f:
            self.metadata = pickle.load(f)
        
        # Load movies_db
        with open(config.CACHE_FILES['movies_db'], 'rb') as f:
            self.movies_db = pickle.load(f)
        
        # Load FAISS indexes
        indexer = FAISSIndexer()
        indexer.load_indexes()
        
        # Build DBR matcher
        dbr_matcher = DBRMatcher(self.metadata)
        
        # Create search engine
        self.search_engine = SearchEngine(
            indexer, dbr_matcher, self.movies_db,
            self.embeddings, self.metadata
        )
        
        if config.VERBOSE:
            print("   ✓ Loaded from cache")
    
    def search(
        self,
        query_movie: str,
        k: int = None,
        min_score: float = None,
        min_overlap_days: int = None
    ) -> Dict[str, Any]:
        """
        Search for similar movies
        
        Args:
            query_movie: Movie title
            k: Number of results (default: 5)
            min_score: Minimum similarity score (default: 85)
            min_overlap_days: Minimum DBR overlap (default: 5)
            
        Returns:
            Dict with search results
        """
        return self.search_engine.search(
            query_movie, k, min_score, min_overlap_days
        )
    
    def get_all_titles(self) -> list:
        """Get list of all indexed movie titles"""
        return sorted([meta['title'] for meta in self.metadata])
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics"""
        return {
            'total_movies': len(self.metadata),
            'vector_dimension': config.VECTOR_DIMENSION,
            'gaussian_smoothing': config.USE_GAUSSIAN_SMOOTHING,
            'min_similarity_score': config.MIN_SIMILARITY_SCORE,
            'min_dbr_overlap': config.MIN_DBR_OVERLAP_DAYS,
            'cache_enabled': config.ENABLE_CACHE,
            'index_type': 'IVF-PQ' if len(self.metadata) >= config.USE_IVF_THRESHOLD else 'Flat'
        }


def format_results(results: Dict[str, Any], verbose: bool = True) -> str:
    """Format search results for display"""
    if results['status'] != 'success':
        return f"❌ {results.get('message', 'Search failed')}"
    
    output = []
    output.append("=" * 80)
    output.append(f"🎬 QUERY MOVIE: {results['query_movie']}")
    output.append("=" * 80)
    
    qm = results['query_metadata']
    output.append(f"  DBR Range: {qm['dbr_range']}")
    output.append(f"  Active Days: {qm['active_days']}")
    output.append(f"  Total Revenue: ${qm['total_revenue']:,.2f}")
    output.append(f"  Avg Daily Revenue: ${qm.get('avg_daily_revenue', 0):,.2f}")
    
    output.append("\n" + "=" * 80)
    output.append(f"📊 SIMILAR MOVIES (Found {results['total_found']})")
    output.append("=" * 80)
    
    for i, movie in enumerate(results['similar_movies'], 1):
        output.append(f"\n{i}. {movie['title']}")
        output.append(f"   Similarity Score: {movie['similarity_score']}%")
        output.append(f"   Total Revenue: ${movie['total_revenue']:,.2f} ({movie['revenue_comparison']})")
        output.append(f"   Active Days: {movie['active_days']}")
        
        # DBR Overlap
        overlap = movie['dbr_overlap']
        output.append(f"   DBR Overlap: {overlap['range']} ({overlap['days']} days)")
        output.append(f"   Coverage: Query {overlap['query_coverage']}%, Candidate {overlap['candidate_coverage']}%")
        
        # Tolerance metrics
        tol = movie['tolerance_metrics']
        output.append(f"   Tolerance: {tol['within_1pct']} days ≤1%, {tol['within_2pct']} days ≤2%, {tol['within_5pct']} days ≤5%")
        output.append(f"   Max Diff: {tol['max_diff']}%, Avg Diff: {tol['avg_diff']}%")
    
    if verbose and 'performance' in results:
        perf = results['performance']
        output.append("\n" + "=" * 80)
        output.append("⚡ PERFORMANCE")
        output.append("=" * 80)
        output.append(f"  Total Time: {perf['total_time_ms']:.2f}ms")
        output.append(f"  Stage 1 (FAISS): {perf['stage1_time_ms']:.2f}ms ({perf['candidates_stage1']} candidates)")
        output.append(f"  Stage 2 (DBR Filter): {perf['stage2_time_ms']:.2f}ms ({perf['candidates_stage2']} candidates)")
        output.append(f"  Stage 3 (Validation): {perf['stage3_time_ms']:.2f}ms")
    
    return "\n".join(output)


def main():
    """Main interactive loop"""
    print("=" * 80)
    print("🎬 MOVIE SIMILARITY ENGINE V2")
    print("High-Performance Scalable Architecture")
    print("=" * 80)
    
    # Initialize engine
    engine = MovieSimilarityEngine(force_rebuild=False)
    
    # Show statistics
    stats = engine.get_statistics()
    print("\n📊 SYSTEM STATISTICS")
    print("-" * 80)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Interactive loop
    print("\n" + "=" * 80)
    print("💬 INTERACTIVE MODE")
    print("=" * 80)
    print("Commands:")
    print("  - Enter movie name to search")
    print("  - 'list' to show all movies")
    print("  - 'stats' to show statistics")
    print("  - 'exit' to quit")
    print()
    
    while True:
        try:
            user_input = input("🔍 Search: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if user_input.lower() == 'list':
                titles = engine.get_all_titles()
                print(f"\n📋 Total Movies: {len(titles)}")
                print("First 20:")
                for i, title in enumerate(titles[:20], 1):
                    print(f"  {i}. {title}")
                if len(titles) > 20:
                    print(f"  ... and {len(titles) - 20} more")
                print()
                continue
            
            if user_input.lower() == 'stats':
                stats = engine.get_statistics()
                print("\n📊 SYSTEM STATISTICS")
                for key, value in stats.items():
                    print(f"  {key}: {value}")
                print()
                continue
            
            # Search
            results = engine.search(user_input, k=5)
            print("\n" + format_results(results))
            print()
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    main()
