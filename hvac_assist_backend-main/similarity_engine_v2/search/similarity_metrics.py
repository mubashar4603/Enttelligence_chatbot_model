"""
Similarity Metrics Module
Calculate multi-metric similarity scores and tolerance metrics
"""

import numpy as np
from typing import Dict, Any
import config

class SimilarityMetrics:
    """Calculate various similarity metrics between growth curves"""
    
    @staticmethod
    def calculate_similarity_score(
        query_growth: np.ndarray,
        candidate_growth: np.ndarray,
        overlap_info: Dict[str, Any]
    ) -> float:
        """
        Calculate composite similarity score
        
        Args:
            query_growth: Query movie growth curve
            candidate_growth: Candidate movie growth curve
            overlap_info: DBR overlap information
            
        Returns:
            float: Similarity score (0-100)
        """
        # Extract overlapping portions
        q_overlap = query_growth[overlap_info['query_indices']]
        c_overlap = candidate_growth[overlap_info['candidate_indices']]
        
        # Calculate individual metrics
        cosine_sim = SimilarityMetrics._cosine_similarity(q_overlap, c_overlap)
        correlation = SimilarityMetrics._pearson_correlation(q_overlap, c_overlap)
        mape_sim = SimilarityMetrics._mape_similarity(q_overlap, c_overlap)
        coverage_bonus = SimilarityMetrics._coverage_bonus(overlap_info)
        
        # Weighted average
        score = (
            config.METRIC_WEIGHTS['cosine'] * cosine_sim +
            config.METRIC_WEIGHTS['correlation'] * max(correlation, 0) +  # Ignore negative correlation
            config.METRIC_WEIGHTS['mape'] * mape_sim +
            config.METRIC_WEIGHTS['coverage'] * coverage_bonus
        ) * 100
        
        return float(score)
    
    @staticmethod
    def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    @staticmethod
    def _pearson_correlation(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate Pearson correlation coefficient"""
        if len(vec1) < 2:
            return 0.0
        
        try:
            corr_matrix = np.corrcoef(vec1, vec2)
            return float(corr_matrix[0, 1])
        except:
            return 0.0
    
    @staticmethod
    def _mape_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate similarity based on Mean Absolute Percentage Error
        Returns value between 0 and 1 (higher is more similar)
        """
        # Calculate absolute percentage differences
        abs_diff = np.abs(vec1 - vec2)
        abs_values = np.abs(vec1) + 1e-8  # Add epsilon to avoid division by zero
        
        # MAPE
        mape = np.mean(abs_diff / abs_values)
        
        # Convert to similarity (1 - normalized MAPE)
        # Clamp MAPE to reasonable range
        mape = min(mape, 2.0)  # Cap at 200% difference
        similarity = 1.0 - (mape / 2.0)
        
        return float(max(similarity, 0.0))
    
    @staticmethod
    def _coverage_bonus(overlap_info: Dict[str, Any]) -> float:
        """
        Calculate coverage bonus based on overlap
        Returns value between 0 and 1
        """
        # Use average coverage percentage
        avg_coverage = overlap_info.get('avg_coverage', 0)
        
        # Normalize to 0-1 (assuming 30 days is "full coverage")
        coverage_score = min(overlap_info['overlap_count'] / 30.0, 1.0)
        
        # Also consider percentage coverage
        pct_score = avg_coverage / 100.0
        
        # Average of both
        return float((coverage_score + pct_score) / 2.0)
    
    @staticmethod
    def calculate_tolerance_metrics(
        query_growth: np.ndarray,
        candidate_growth: np.ndarray,
        overlap_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate tolerance metrics (how many days within X% difference)
        
        Args:
            query_growth: Query movie growth curve
            candidate_growth: Candidate movie growth curve
            overlap_info: DBR overlap information
            
        Returns:
            Dict with tolerance metrics
        """
        # Extract overlapping portions
        q_overlap = query_growth[overlap_info['query_indices']]
        c_overlap = candidate_growth[overlap_info['candidate_indices']]
        
        # Calculate absolute differences
        daily_diffs = np.abs(q_overlap - c_overlap)
        total_days = len(daily_diffs)
        
        # Count days within each threshold
        tolerance_counts = {}
        tolerance_rates = {}
        
        for threshold in config.TOLERANCE_THRESHOLDS:
            within_threshold = np.sum(daily_diffs <= threshold)
            tolerance_counts[f'within_{int(threshold)}pct'] = int(within_threshold)
            tolerance_rates[f'pass_rate_{int(threshold)}pct'] = float(within_threshold / total_days * 100)
        
        return {
            **tolerance_counts,
            **tolerance_rates,
            'max_diff': float(np.max(daily_diffs)),
            'avg_diff': float(np.mean(daily_diffs)),
            'median_diff': float(np.median(daily_diffs)),
            'std_diff': float(np.std(daily_diffs)),
            'total_days': total_days
        }
    
    @staticmethod
    def calculate_all_metrics(
        query_growth: np.ndarray,
        candidate_growth: np.ndarray,
        overlap_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate all metrics at once
        
        Returns:
            Dict with similarity_score and tolerance_metrics
        """
        similarity_score = SimilarityMetrics.calculate_similarity_score(
            query_growth, candidate_growth, overlap_info
        )
        
        tolerance_metrics = SimilarityMetrics.calculate_tolerance_metrics(
            query_growth, candidate_growth, overlap_info
        )
        
        return {
            'similarity_score': similarity_score,
            'tolerance_metrics': tolerance_metrics
        }


if __name__ == "__main__":
    # Test similarity metrics
    print("="*60)
    print("SIMILARITY METRICS TEST")
    print("="*60)
    
    # Create test vectors
    vec1 = np.array([10.0, 15.0, 12.0, 8.0, 5.0])
    vec2 = np.array([11.0, 14.5, 12.5, 7.5, 5.5])  # Very similar
    vec3 = np.array([50.0, 60.0, 55.0, 40.0, 30.0])  # Different scale
    
    # Test overlap info
    overlap_info = {
        'query_indices': [0, 1, 2, 3, 4],
        'candidate_indices': [0, 1, 2, 3, 4],
        'overlap_count': 5,
        'avg_coverage': 100.0
    }
    
    # Test 1: Similar vectors
    print("\nTest 1: Similar vectors")
    print(f"Vec1: {vec1}")
    print(f"Vec2: {vec2}")
    
    score = SimilarityMetrics.calculate_similarity_score(vec1, vec2, overlap_info)
    print(f"Similarity score: {score:.2f}")
    
    tolerance = SimilarityMetrics.calculate_tolerance_metrics(vec1, vec2, overlap_info)
    print(f"Tolerance metrics:")
    for key, value in tolerance.items():
        print(f"  {key}: {value}")
    
    # Test 2: Different scale
    print("\nTest 2: Different scale (same pattern)")
    print(f"Vec1: {vec1}")
    print(f"Vec3: {vec3}")
    
    score = SimilarityMetrics.calculate_similarity_score(vec1, vec3, overlap_info)
    print(f"Similarity score: {score:.2f}")
    
    tolerance = SimilarityMetrics.calculate_tolerance_metrics(vec1, vec3, overlap_info)
    print(f"Max difference: {tolerance['max_diff']:.2f}")
    print(f"Avg difference: {tolerance['avg_diff']:.2f}")
