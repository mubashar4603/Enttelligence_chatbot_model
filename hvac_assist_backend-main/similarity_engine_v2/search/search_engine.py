"""
Search Engine Module
Main 3-stage search pipeline
"""

import numpy as np
from typing import Dict, List, Any, Optional
import time
import config

class SearchEngine:
    """High-performance 3-stage search engine"""
    
    def __init__(self, faiss_indexer, dbr_matcher, movies_db, embeddings, metadata):
        """
        Initialize search engine
        
        Args:
            faiss_indexer: FAISSIndexer instance
            dbr_matcher: DBRMatcher instance
            movies_db: Dictionary of movie data
            embeddings: Numpy array of embeddings
            metadata: List of metadata dicts
        """
        self.indexer = faiss_indexer
        self.dbr_matcher = dbr_matcher
        self.movies_db = movies_db
        self.embeddings = embeddings
        self.metadata = metadata
        
        # Build title to ID mapping
        self.title_to_id = {meta['title']: meta['movie_id'] for meta in metadata}
        
        # Import similarity metrics
        from .similarity_metrics import SimilarityMetrics
        self.metrics = SimilarityMetrics()
    
    def search(
        self,
        query_movie: str,
        k: int = None,
        min_score: float = None,
        min_overlap_days: int = None,
        use_fast_index: bool = True
    ) -> Dict[str, Any]:
        """
        Search for similar movies (3-stage pipeline)
        
        Args:
            query_movie: Movie title to search for
            k: Number of results (default: from config)
            min_score: Minimum similarity score (default: from config)
            min_overlap_days: Minimum DBR overlap (default: from config)
            use_fast_index: Use fast index for stage 1
            
        Returns:
            Dict with search results
        """
        # Set defaults
        k = k or config.DEFAULT_K
        min_score = min_score or config.MIN_SIMILARITY_SCORE
        min_overlap_days = min_overlap_days or config.MIN_DBR_OVERLAP_DAYS
        
        start_time = time.time()
        
        # Find query movie
        query_id = self._find_movie_id(query_movie)
        if query_id is None:
            return {
                'status': 'error',
                'message': f"Movie '{query_movie}' not found",
                'suggestions': self._get_suggestions(query_movie)
            }
        
        query_title = self.metadata[query_id]['title']
        query_data = self.movies_db[query_title]
        
        # Stage 1: FAISS approximate search
        stage1_start = time.time()
        candidates = self._stage1_faiss_search(query_id, k, use_fast_index)
        stage1_time = time.time() - stage1_start
        
        # Stage 2: DBR overlap filtering
        stage2_start = time.time()
        filtered = self._stage2_dbr_filter(query_id, candidates, min_overlap_days)
        stage2_time = time.time() - stage2_start
        
        # Stage 3: Fine-grained validation
        stage3_start = time.time()
        results = self._stage3_validate_and_rank(query_id, query_data, filtered, k, min_score)
        stage3_time = time.time() - stage3_start
        
        total_time = time.time() - start_time
        
        if not results:
            return {
                'status': 'no_matches',
                'query_movie': query_title,
                'message': f"No similar movies found (min_score: {min_score}, min_overlap: {min_overlap_days} days)",
                'search_time_ms': round(total_time * 1000, 2)
            }
        
        return {
            'status': 'success',
            'query_movie': query_title,
            'query_metadata': {
                'dbr_range': f"DBR {query_data['dbr_range'][0]} to {query_data['dbr_range'][1]}",
                'active_days': query_data['active_days'],
                'total_revenue': query_data['total_revenue'],
                'avg_daily_revenue': query_data.get('avg_daily_revenue', 0)
            },
            'similar_movies': results,
            'total_found': len(results),
            'performance': {
                'total_time_ms': round(total_time * 1000, 2),
                'stage1_time_ms': round(stage1_time * 1000, 2),
                'stage2_time_ms': round(stage2_time * 1000, 2),
                'stage3_time_ms': round(stage3_time * 1000, 2),
                'candidates_stage1': len(candidates),
                'candidates_stage2': len(filtered)
            }
        }
    
    def _find_movie_id(self, query: str) -> Optional[int]:
        """Find movie ID with fuzzy matching"""
        query_lower = query.lower().strip()
        
        # Exact match
        if query in self.title_to_id:
            return self.title_to_id[query]
        
        # Case-insensitive match
        for title, movie_id in self.title_to_id.items():
            if title.lower() == query_lower:
                return movie_id
        
        # Partial match
        for title, movie_id in self.title_to_id.items():
            if query_lower in title.lower():
                return movie_id
        
        return None
    
    def _get_suggestions(self, query: str, max_suggestions: int = 5) -> List[str]:
        """Get movie title suggestions for failed search"""
        query_lower = query.lower()
        suggestions = []
        
        for title in self.title_to_id.keys():
            if query_lower in title.lower():
                suggestions.append(title)
                if len(suggestions) >= max_suggestions:
                    break
        
        return suggestions
    
    def _stage1_faiss_search(self, query_id: int, k: int, use_fast: bool) -> List[Dict]:
        """
        Stage 1: FAISS approximate search
        
        Returns:
            List of candidate dicts with movie_id and faiss_distance
        """
        query_vector = self.embeddings[query_id]
        
        # Fetch more candidates for filtering
        search_k = min(k * config.FAISS_SEARCH_K_MULTIPLIER, len(self.embeddings))
        
        # Search
        distances, indices = self.indexer.search(query_vector, search_k, use_fast=use_fast)
        
        # Convert to candidates list
        candidates = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == query_id:  # Skip self
                continue
            
            candidates.append({
                'movie_id': int(idx),
                'title': self.metadata[idx]['title'],
                'faiss_distance': float(dist)
            })
        
        return candidates
    
    def _stage2_dbr_filter(self, query_id: int, candidates: List[Dict], min_overlap: int) -> List[Dict]:
        """
        Stage 2: Filter by DBR overlap
        
        Returns:
            List of candidates with overlap_info added
        """
        filtered = []
        
        for candidate in candidates:
            overlap = self.dbr_matcher.find_overlap(query_id, candidate['movie_id'])
            
            if overlap and overlap['overlap_count'] >= min_overlap:
                candidate['overlap_info'] = overlap
                filtered.append(candidate)
        
        return filtered
    
    def _stage3_validate_and_rank(
        self,
        query_id: int,
        query_data: Dict,
        candidates: List[Dict],
        k: int,
        min_score: float
    ) -> List[Dict]:
        """
        Stage 3: Calculate detailed similarity and rank
        
        Returns:
            List of result dicts, sorted by similarity score
        """
        # Get query growth curve
        query_growth = query_data['growth_smoothed'] if config.USE_GAUSSIAN_SMOOTHING else query_data['growth_raw']
        
        # Pad to vector dimension
        query_growth = self._pad_vector(query_growth, config.VECTOR_DIMENSION)
        
        results = []
        
        for candidate in candidates:
            cand_title = candidate['title']
            cand_data = self.movies_db[cand_title]
            
            # Get candidate growth curve
            cand_growth = cand_data['growth_smoothed'] if config.USE_GAUSSIAN_SMOOTHING else cand_data['growth_raw']
            cand_growth = self._pad_vector(cand_growth, config.VECTOR_DIMENSION)
            
            # Calculate similarity score
            similarity_score = self.metrics.calculate_similarity_score(
                query_growth,
                cand_growth,
                candidate['overlap_info']
            )
            
            # Skip if below threshold
            if similarity_score < min_score:
                continue
            
            # Calculate tolerance metrics
            tolerance_metrics = self.metrics.calculate_tolerance_metrics(
                query_growth,
                cand_growth,
                candidate['overlap_info']
            )
            
            # Build result
            overlap_info = candidate['overlap_info']
            results.append({
                'title': cand_title,
                'similarity_score': round(similarity_score, 2),
                'total_revenue': cand_data['total_revenue'],
                'active_days': cand_data['active_days'],
                'avg_daily_revenue': cand_data.get('avg_daily_revenue', 0),
                'dbr_overlap': {
                    'range': f"DBR {overlap_info['overlap_dbrs'][0]} to {overlap_info['overlap_dbrs'][-1]}",
                    'days': overlap_info['overlap_count'],
                    'query_coverage': round(overlap_info['query_coverage'], 1),
                    'candidate_coverage': round(overlap_info['candidate_coverage'], 1)
                },
                'tolerance_metrics': {
                    'within_1pct': tolerance_metrics.get('within_1pct', 0),
                    'within_2pct': tolerance_metrics.get('within_2pct', 0),
                    'within_5pct': tolerance_metrics.get('within_5pct', 0),
                    'pass_rate_2pct': round(tolerance_metrics.get('pass_rate_2pct', 0), 1),
                    'max_diff': round(tolerance_metrics['max_diff'], 2),
                    'avg_diff': round(tolerance_metrics['avg_diff'], 2)
                },
                'revenue_comparison': 'higher' if cand_data['total_revenue'] > query_data['total_revenue'] else 'lower'
            })
        
        # Sort by similarity score (descending)
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return results[:k]
    
    def _pad_vector(self, vector: np.ndarray, target_dim: int) -> np.ndarray:
        """Pad vector to target dimension"""
        if len(vector) >= target_dim:
            return vector[:target_dim]
        return np.pad(vector, (0, target_dim - len(vector)), 'constant', constant_values=0)


if __name__ == "__main__":
    print("Search engine module - use main.py to run full system")
