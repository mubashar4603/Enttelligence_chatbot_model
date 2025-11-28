"""
DBR-Specific Similarity Search - Main Interface
Exactly like the screenshot format you showed
"""

import pandas as pd
from dbr_specific_search import DBRSpecificSimilarity
from core.data_loader import DataLoader
from core.preprocessor import MoviePreprocessor
from core.vector_builder import VectorBuilder
import pickle
import os
import config

class DBRSimilarityInterface:
    """User-friendly interface for DBR-specific search"""
    
    def __init__(self):
        self.finder = None
        self._initialize()
    
    def _initialize(self):
        """Initialize or load system"""
        print("🔧 Initializing DBR-Specific Similarity Finder...")
        
        # Check cache
        if os.path.exists(config.CACHE_FILES['movies_db']) and os.path.exists(config.CACHE_FILES['metadata']):
            print("📦 Loading from cache...")
            with open(config.CACHE_FILES['movies_db'], 'rb') as f:
                movies_db = pickle.load(f)
            with open(config.CACHE_FILES['metadata'], 'rb') as f:
                metadata = pickle.load(f)
        else:
            print("🔨 Building from scratch...")
            loader = DataLoader()
            df = loader.load()
            
            preprocessor = MoviePreprocessor(df)
            movies_db = preprocessor.process_all_movies()
            
            builder = VectorBuilder(movies_db)
            _, metadata = builder.build_embeddings()
        
        self.finder = DBRSpecificSimilarity(movies_db, metadata)
        print("✅ Ready!\n")
    
    def search(
        self,
        query_movie: str,
        max_growth_diff: float = 3.0,
        min_consecutive_dbrs: int = 3,
        output_format: str = 'table'
    ):
        """
        Search for DBR-specific matches
        
        Args:
            query_movie: Movie name
            max_growth_diff: Max growth % difference (default: 3%)
            min_consecutive_dbrs: Min consecutive matching DBRs (default: 3)
            output_format: 'table', 'csv', or 'both'
        """
        print(f"🔍 Searching for DBR-specific matches for: {query_movie}")
        print(f"   Max growth difference: {max_growth_diff}%")
        print(f"   Min consecutive DBRs: {min_consecutive_dbrs}")
        print()
        
        results = self.finder.find_dbr_specific_matches(
            query_movie,
            max_growth_diff=max_growth_diff,
            min_consecutive_dbrs=min_consecutive_dbrs
        )
        
        if not results:
            print("❌ No matches found")
            return None
        
        # Convert to DataFrame
        df = self.finder.export_to_dataframe(query_movie, results)
        
        print(f"✅ Found {len(df)} DBR-specific matches across {len(results)} movies\n")
        
        if output_format in ['table', 'both']:
            self._display_table(df, query_movie)
        
        if output_format in ['csv', 'both']:
            filename = f"{query_movie.replace(' ', '_')}_dbr_matches.csv"
            df.to_csv(filename, index=False)
            print(f"\n💾 Saved to: {filename}")
        
        return df
    
    def _display_table(self, df: pd.DataFrame, query_movie: str):
        """Display results in table format like screenshot"""
        print("=" * 120)
        print(f"{query_movie} - Similar Titles")
        print("=" * 120)
        print(f"{'Target Title':<20} {'Similar Title':<30} {'DBR':<6} {'Target Growth':<15} {'Similar Growth':<15}")
        print("-" * 120)
        
        # Group by similar movie for better readability
        for similar_movie in df['Similar Title'].unique():
            movie_df = df[df['Similar Title'] == similar_movie].sort_values('DBR')
            
            for idx, row in movie_df.iterrows():
                print(f"{row['Target Title']:<20} {row['Similar Title']:<30} {row['DBR']:<6} {row['Target Growth']:<15.2f} {row['Similar Growth']:<15.2f}")
            
            print()  # Blank line between movies
    
    def compare_specific_movies(
        self,
        query_movie: str,
        similar_movies: list,
        max_growth_diff: float = 3.0
    ):
        """
        Compare query movie with specific similar movies
        (Like your screenshot showing Zootopia 2 vs specific movies)
        """
        print(f"🔍 Comparing {query_movie} with specific movies...")
        print()
        
        all_results = self.finder.find_dbr_specific_matches(
            query_movie,
            max_growth_diff=max_growth_diff,
            min_consecutive_dbrs=1  # Show all matching DBRs
        )
        
        # Filter to only requested movies
        filtered_results = [r for r in all_results if r['similar_movie'] in similar_movies]
        
        if not filtered_results:
            print("❌ No matches found with specified movies")
            return None
        
        df = self.finder.export_to_dataframe(query_movie, filtered_results)
        
        self._display_table(df, query_movie)
        
        return df


def main():
    """Main interactive interface"""
    print("=" * 120)
    print("🎬 DBR-SPECIFIC MOVIE SIMILARITY FINDER")
    print("=" * 120)
    print()
    
    interface = DBRSimilarityInterface()
    
    print("=" * 120)
    print("💬 INTERACTIVE MODE")
    print("=" * 120)
    print("Commands:")
    print("  1. Enter movie name to find all DBR-specific matches")
    print("  2. Type 'compare' to compare with specific movies")
    print("  3. Type 'exit' to quit")
    print()
    
    while True:
        try:
            user_input = input("🔍 Enter command or movie name: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if user_input.lower() == 'compare':
                query = input("  Query movie: ").strip()
                similar = input("  Similar movies (comma-separated): ").strip()
                similar_list = [s.strip() for s in similar.split(',')]
                
                max_diff = input("  Max growth difference % (default 3.0): ").strip()
                max_diff = float(max_diff) if max_diff else 3.0
                
                interface.compare_specific_movies(query, similar_list, max_diff)
            else:
                # Regular search
                max_diff = input(f"  Max growth difference % (default 3.0, press Enter to skip): ").strip()
                max_diff = float(max_diff) if max_diff else 3.0
                
                min_dbrs = input(f"  Min consecutive DBRs (default 3, press Enter to skip): ").strip()
                min_dbrs = int(min_dbrs) if min_dbrs else 3
                
                interface.search(user_input, max_growth_diff=max_diff, min_consecutive_dbrs=min_dbrs, output_format='both')
            
            print()
            
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    main()
