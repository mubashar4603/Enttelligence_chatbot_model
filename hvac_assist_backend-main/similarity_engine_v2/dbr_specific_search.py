"""
DBR-by-DBR Similarity Finder
Finds movies that are similar on SPECIFIC DBR ranges, not overall similarity
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any
import sys
sys.path.append('..')
import similarity_engine_v2.config as config

class DBRSpecificSimilarity:
    """Find movies similar on specific DBR ranges"""
    
    def __init__(self, movies_db: Dict, metadata: List[Dict]):
        self.movies_db = movies_db
        self.metadata = metadata
        self.title_to_id = {meta['title']: meta['movie_id'] for meta in metadata}
    
    def find_dbr_specific_matches(
        self,
        query_movie: str,
        max_growth_diff: float = 3.0,
        min_consecutive_dbrs: int = 3,
        min_dbr: int = None,
        max_dbr: int = None,
        match_mode: str = None,  # 'consecutive' or 'percentage'
        min_percentage: float = None  # Minimum percentage for percentage mode
    ) -> Dict[str, Any]:
        """
        Find movies that match on specific DBR ranges
        
        Args:
            query_movie: Target movie name
            max_growth_diff: Maximum growth % difference (default: 3%)
            min_consecutive_dbrs: Minimum consecutive matching DBRs (default: 3)
            min_dbr: Minimum DBR to consider (inclusive)
            max_dbr: Maximum DBR to consider (inclusive)
            match_mode: 'consecutive' or 'percentage' (defaults to config setting)
            min_percentage: Minimum percentage threshold for percentage mode (defaults to config)
            
        Returns:
            Dict with 'high_similarity' and 'low_similarity' lists (percentage mode)
            or List of matches (consecutive mode)
        """
        # Use config defaults if not specified
        if match_mode is None:
            match_mode = 'percentage' if config.ENABLE_PERCENTAGE_MATCHING else 'consecutive'
        if min_percentage is None:
            min_percentage = config.MIN_PERCENTAGE_THRESHOLD
            
        if query_movie not in self.movies_db:
            return {'high_similarity': [], 'low_similarity': []} if match_mode == 'percentage' else []
        
        query_data = self.movies_db[query_movie]
        query_dbrs = query_data['dbr_list']
        query_growth = query_data['growth_raw']
        
        # Build DBR to growth mapping for query
        query_dbr_growth = {}
        for i, dbr in enumerate(query_dbrs[:-1]):  # -1 because growth is diff
            # Apply Range Filtering
            if min_dbr is not None and dbr < min_dbr:
                continue
            if max_dbr is not None and dbr > max_dbr:
                continue
                
            if i < len(query_growth):
                query_dbr_growth[dbr] = query_growth[i]
        
        # Total DBRs in query (for percentage calculation)
        total_query_dbrs = len(query_dbr_growth)
        
        # Find matches for each DBR
        results = []
        
        # Check each candidate movie
        for cand_title, cand_data in self.movies_db.items():
            if cand_title == query_movie:
                continue
            
            cand_dbrs = cand_data['dbr_list']
            cand_growth = cand_data['growth_raw']
            
            # Build DBR to growth mapping for candidate
            cand_dbr_growth = {}
            for i, dbr in enumerate(cand_dbrs[:-1]):
                # Apply Range Filtering
                if min_dbr is not None and dbr < min_dbr:
                    continue
                if max_dbr is not None and dbr > max_dbr:
                    continue
                    
                if i < len(cand_growth):
                    cand_dbr_growth[dbr] = cand_growth[i]
            
            # Find matching DBR ranges
            matching_ranges = self._find_matching_ranges(
                query_dbr_growth,
                cand_dbr_growth,
                max_growth_diff,
                min_consecutive_dbrs
            )
            
            if matching_ranges:
                # Calculate total matching DBRs and percentage
                total_matching_dbrs = sum(r['dbr_count'] for r in matching_ranges)
                match_percentage = (total_matching_dbrs / total_query_dbrs * 100) if total_query_dbrs > 0 else 0
                
                # Collect all matched DBRs
                matched_dbrs = []
                for range_info in matching_ranges:
                    matched_dbrs.extend([d['dbr'] for d in range_info['dbr_details']])
                
                results.append({
                    'similar_movie': cand_title,
                    'matching_ranges': matching_ranges,
                    'total_revenue': cand_data['total_revenue'],
                    'match_percentage': round(match_percentage, 2),
                    'total_query_dbrs': total_query_dbrs,
                    'total_matching_dbrs': total_matching_dbrs,
                    'matched_dbrs': matched_dbrs
                })
        
        # Filter based on mode
        if match_mode == 'percentage':
            high_similarity = [r for r in results if r['match_percentage'] >= min_percentage]
            low_similarity = [r for r in results if 1 <= r['match_percentage'] < min_percentage]
            return {
                'high_similarity': high_similarity,
                'low_similarity': low_similarity,
                'query_movie': query_movie,
                'total_query_dbrs': total_query_dbrs
            }
        else:
            # Consecutive mode - return as before
            return results
    
    def _find_matching_ranges(
        self,
        query_dbr_growth: Dict[int, float],
        cand_dbr_growth: Dict[int, float],
        max_diff: float,
        min_consecutive: int
    ) -> List[Dict]:
        """Find consecutive DBR ranges where growth is similar"""
        # Find common DBRs
        common_dbrs = sorted(set(query_dbr_growth.keys()) & set(cand_dbr_growth.keys()))
        
        if len(common_dbrs) < min_consecutive:
            return []
        
        # Find consecutive matching ranges
        ranges = []
        current_range = []
        current_diffs = []
        
        for dbr in common_dbrs:
            query_val = query_dbr_growth[dbr]
            cand_val = cand_dbr_growth[dbr]
            diff = abs(query_val - cand_val)
            
            if diff <= max_diff:
                # Check for consecutiveness
                if not current_range or dbr == current_range[-1] + 1:
                    current_range.append(dbr)
                    current_diffs.append({
                        'dbr': dbr,
                        'target_growth': round(query_val, 2),
                        'similar_growth': round(cand_val, 2),
                        'difference': round(diff, 2)
                    })
                else:
                    # Not consecutive - break range
                    if len(current_range) >= min_consecutive:
                        ranges.append({
                            'dbr_start': current_range[0],
                            'dbr_end': current_range[-1],
                            'dbr_count': len(current_range),
                            'dbr_details': current_diffs,
                            'avg_difference': round(np.mean([d['difference'] for d in current_diffs]), 2)
                        })
                    
                    # Start new range
                    current_range = [dbr]
                    current_diffs = [{
                        'dbr': dbr,
                        'target_growth': round(query_val, 2),
                        'similar_growth': round(cand_val, 2),
                        'difference': round(diff, 2)
                    }]
            else:
                # End of consecutive range
                if len(current_range) >= min_consecutive:
                    ranges.append({
                        'dbr_start': current_range[0],
                        'dbr_end': current_range[-1],
                        'dbr_count': len(current_range),
                        'dbr_details': current_diffs,
                        'avg_difference': round(np.mean([d['difference'] for d in current_diffs]), 2)
                    })
                current_range = []
                current_diffs = []
        
        # Check last range
        if len(current_range) >= min_consecutive:
            ranges.append({
                'dbr_start': current_range[0],
                'dbr_end': current_range[-1],
                'dbr_count': len(current_range),
                'dbr_details': current_diffs,
                'avg_difference': round(np.mean([d['difference'] for d in current_diffs]), 2)
            })
        
        return ranges
    
    def format_results(self, query_movie: str, results: List[Dict]) -> str:
        """Format results for display"""
        output = []
        output.append("=" * 100)
        output.append(f"🎬 DBR-SPECIFIC SIMILARITY FOR: {query_movie}")
        output.append("=" * 100)
        
        if not results:
            output.append("\n❌ No similar movies found with matching DBR ranges")
            return "\n".join(output)
        
        # Group by similar movie
        for result in results:
            output.append(f"\n📊 SIMILAR MOVIE: {result['similar_movie']}")
            output.append(f"   Total Revenue: ${result['total_revenue']:,.2f}")
            output.append(f"   Matching DBR Ranges: {len(result['matching_ranges'])}")
            
            for i, range_info in enumerate(result['matching_ranges'], 1):
                output.append(f"\n   Range {i}: DBR {range_info['dbr_start']} to {range_info['dbr_end']} ({range_info['dbr_count']} days)")
                output.append(f"   Avg Difference: {range_info['avg_difference']}%")
                
                # Show first few DBRs
                output.append(f"   Sample DBRs:")
                for detail in range_info['dbr_details'][:5]:  # Show first 5
                    output.append(f"      DBR {detail['dbr']}: Target={detail['target_growth']}%, Similar={detail['similar_growth']}%, Diff={detail['difference']}%")
                
                if len(range_info['dbr_details']) > 5:
                    output.append(f"      ... and {len(range_info['dbr_details']) - 5} more DBRs")
        
        return "\n".join(output)
    
    def export_to_dataframe(self, query_movie: str, results: List[Dict]) -> pd.DataFrame:
        """Export results to pandas DataFrame (like your screenshot format)"""
        rows = []
        
        for result in results:
            similar_movie = result['similar_movie']
            
            for range_info in result['matching_ranges']:
                for detail in range_info['dbr_details']:
                    rows.append({
                        'Target Title': query_movie,
                        'Similar Title': similar_movie,
                        'DBR': detail['dbr'],
                        'Target Growth': detail['target_growth'],
                        'Similar Growth': detail['similar_growth'],
                        'Difference': detail['difference']
                    })
        
        return pd.DataFrame(rows)
    
    def export_to_dataframe_with_percentage(self, query_movie: str, results: List[Dict], include_details: bool = True) -> pd.DataFrame:
        """
        Export results with percentage information to pandas DataFrame
        
        Args:
            query_movie: Query movie name
            results: List of match results with percentage info
            include_details: If True, include DBR-by-DBR details; if False, just summary
        """
        rows = []
        
        for result in results:
            similar_movie = result['similar_movie']
            match_percentage = result.get('match_percentage', 0)
            total_matching_dbrs = result.get('total_matching_dbrs', 0)
            
            if include_details:
                # Detailed view with all matching DBRs
                for range_info in result['matching_ranges']:
                    for detail in range_info['dbr_details']:
                        rows.append({
                            'Target Title': query_movie,
                            'Similar Title': similar_movie,
                            'Match %': match_percentage,
                            'Matching DBRs': total_matching_dbrs,
                            'DBR': detail['dbr'],
                            'Target Growth': detail['target_growth'],
                            'Similar Growth': detail['similar_growth'],
                            'Difference': detail['difference']
                        })
            else:
                # Summary view (for low similarity table)
                # Get DBR ranges
                dbr_ranges = []
                for range_info in result['matching_ranges']:
                    dbr_ranges.append(f"{range_info['dbr_start']} to {range_info['dbr_end']}")
                
                rows.append({
                    'Similar Title': similar_movie,
                    'Match %': match_percentage,
                    'Matching DBRs': total_matching_dbrs,
                    'DBR Ranges': ', '.join(dbr_ranges)
                })
        
        return pd.DataFrame(rows)



if __name__ == "__main__":
    # Test the DBR-specific similarity
    from core.data_loader import DataLoader
    from core.preprocessor import MoviePreprocessor
    from core.vector_builder import VectorBuilder
    
    print("Loading data...")
    loader = DataLoader()
    df = loader.load()
    
    print("Processing movies...")
    preprocessor = MoviePreprocessor(df)
    movies_db = preprocessor.process_all_movies()
    
    print("Building vectors...")
    builder = VectorBuilder(movies_db)
    embeddings, metadata = builder.build_embeddings()
    
    print("\n" + "=" * 100)
    print("DBR-SPECIFIC SIMILARITY FINDER")
    print("=" * 100)
    
    # Initialize finder
    finder = DBRSpecificSimilarity(movies_db, metadata)
    
    # Test with a movie
    test_movie = input("\nEnter movie name to test: ").strip()
    
    if test_movie:
        print(f"\nSearching for DBR-specific matches for '{test_movie}'...")
        print("(Max growth difference: 3%, Min consecutive DBRs: 3)")
        
        results = finder.find_dbr_specific_matches(
            test_movie,
            max_growth_diff=3.0,
            min_consecutive_dbrs=3
        )
        
        print(finder.format_results(test_movie, results))
        
        # Export to DataFrame
        if results:
            df_results = finder.export_to_dataframe(test_movie, results)
            print(f"\n\n📊 DATAFRAME FORMAT (first 20 rows):")
            print(df_results.head(20).to_string(index=False))
            
            # Save to CSV
            output_file = f"{test_movie.replace(' ', '_')}_dbr_matches.csv"
            df_results.to_csv(output_file, index=False)
            print(f"\n💾 Saved to: {output_file}")
