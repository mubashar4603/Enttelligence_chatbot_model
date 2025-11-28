"""
DBR Matcher Module
Handles DBR overlap detection and filtering
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from similarity_engine_v2 import config

class DBRMatcher:
    """Match and filter movies based on DBR overlap"""
    
    def __init__(self, metadata: List[Dict[str, Any]]):
        """
        Initialize with movie metadata
        
        Args:
            metadata: List of movie metadata dicts with dbr_list and dbr_range
        """
        self.metadata = metadata
        self._build_dbr_index()
    
    def _build_dbr_index(self):
        """Build index for fast DBR lookup"""
        self.dbr_index = {}
        for meta in self.metadata:
            movie_id = meta['movie_id']
            self.dbr_index[movie_id] = {
                'dbr_list': meta['dbr_list'],
                'dbr_range': meta['dbr_range'],
                'dbr_set': set(meta['dbr_list'])
            }
    
    def find_overlap(self, query_id: int, candidate_id: int) -> Optional[Dict[str, Any]]:
        """
        Find DBR overlap between two movies
        
        Args:
            query_id: Query movie ID
            candidate_id: Candidate movie ID
            
        Returns:
            Dict with overlap info or None if insufficient overlap
        """
        query_info = self.dbr_index[query_id]
        cand_info = self.dbr_index[candidate_id]
        
        # Find common DBRs (handles missing values)
        common_dbrs = query_info['dbr_set'] & cand_info['dbr_set']
        
        if len(common_dbrs) < config.MIN_DBR_OVERLAP_DAYS:
            return None
        
        # Sort common DBRs
        common_dbrs_sorted = sorted(list(common_dbrs))
        
        # Get indices in original lists
        query_indices = [query_info['dbr_list'].index(dbr) for dbr in common_dbrs_sorted]
        cand_indices = [cand_info['dbr_list'].index(dbr) for dbr in common_dbrs_sorted]
        
        # Calculate coverage (what % of each movie's DBRs overlap)
        query_coverage = len(common_dbrs) / len(query_info['dbr_list']) * 100
        cand_coverage = len(common_dbrs) / len(cand_info['dbr_list']) * 100
        
        return {
            'overlap_dbrs': common_dbrs_sorted,
            'overlap_count': len(common_dbrs),
            'overlap_range': (common_dbrs_sorted[0], common_dbrs_sorted[-1]),
            'query_indices': query_indices,
            'candidate_indices': cand_indices,
            'query_coverage': query_coverage,
            'candidate_coverage': cand_coverage,
            'avg_coverage': (query_coverage + cand_coverage) / 2
        }
    
    def filter_by_overlap(self, query_id: int, candidate_ids: List[int]) -> List[Tuple[int, Dict]]:
        """
        Filter candidates by DBR overlap
        
        Args:
            query_id: Query movie ID
            candidate_ids: List of candidate movie IDs
            
        Returns:
            List of (candidate_id, overlap_info) tuples for valid candidates
        """
        valid_candidates = []
        
        for cand_id in candidate_ids:
            if cand_id == query_id:
                continue
            
            overlap = self.find_overlap(query_id, cand_id)
            if overlap is not None:
                valid_candidates.append((cand_id, overlap))
        
        return valid_candidates
    
    def get_dbr_info(self, movie_id: int) -> Dict[str, Any]:
        """Get DBR information for a movie"""
        return self.dbr_index.get(movie_id, {})


if __name__ == "__main__":
    # Test DBR matcher
    from data_loader import DataLoader
    from preprocessor import MoviePreprocessor
    from vector_builder import VectorBuilder
    
    loader = DataLoader()
    df = loader.load()
    
    preprocessor = MoviePreprocessor(df)
    movies_db = preprocessor.process_all_movies()
    
    builder = VectorBuilder(movies_db)
    embeddings, metadata = builder.build_embeddings()
    
    matcher = DBRMatcher(metadata)
    
    print("\n" + "="*60)
    print("DBR MATCHER TEST")
    print("="*60)
    
    # Test overlap between first two movies
    if len(metadata) >= 2:
        movie1_id = 0
        movie2_id = 1
        
        movie1 = metadata[movie1_id]
        movie2 = metadata[movie2_id]
        
        print(f"\nMovie 1: {movie1['title']}")
        print(f"  DBR range: {movie1['dbr_range']}")
        print(f"  DBR count: {len(movie1['dbr_list'])}")
        print(f"  DBRs: {movie1['dbr_list']}")
        
        print(f"\nMovie 2: {movie2['title']}")
        print(f"  DBR range: {movie2['dbr_range']}")
        print(f"  DBR count: {len(movie2['dbr_list'])}")
        print(f"  DBRs: {movie2['dbr_list']}")
        
        overlap = matcher.find_overlap(movie1_id, movie2_id)
        
        if overlap:
            print(f"\nOverlap found:")
            print(f"  Overlap DBRs: {overlap['overlap_dbrs']}")
            print(f"  Overlap count: {overlap['overlap_count']}")
            print(f"  Overlap range: DBR {overlap['overlap_range'][0]} to {overlap['overlap_range'][1]}")
            print(f"  Query coverage: {overlap['query_coverage']:.1f}%")
            print(f"  Candidate coverage: {overlap['candidate_coverage']:.1f}%")
        else:
            print(f"\nNo sufficient overlap (minimum: {config.MIN_DBR_OVERLAP_DAYS} days)")
