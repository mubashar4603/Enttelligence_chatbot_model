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
        min_consecutive_dbrs: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find movies that match on specific DBR ranges
        
        Args:
            query_movie: Target movie name
            max_growth_diff: Maximum growth % difference (default: 3%)
            min_consecutive_dbrs: Minimum consecutive matching DBRs (default: 3)
            
        Returns:
            List of matches with DBR ranges and similar movies
        """
        if query_movie not in self.movies_db:
            return []
        
        query_data = self.movies_db[query_movie]
        query_dbrs = query_data['dbr_list']
        query_growth = query_data['growth_raw']
        
        # Build DBR to growth mapping for query
        query_dbr_growth = {}
        for i, dbr in enumerate(query_dbrs[:-1]):  # -1 because growth is diff
            if i < len(query_growth):
                query_dbr_growth[dbr] = query_growth[i]
        
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
                results.append({
                    'similar_movie': cand_title,
                    'matching_ranges': matching_ranges,
                    'total_revenue': cand_data['total_revenue']
                })
        
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
                current_range.append(dbr)
                current_diffs.append({
                    'dbr': dbr,
                    'target_growth': round(query_val, 2),
                    'similar_growth': round(cand_val, 2),
                    'difference': round(diff, 2)
                })
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
