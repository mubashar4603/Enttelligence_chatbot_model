"""
Batch Process All Movies - Generate Similarity Report CSV

This script:
1. Reads all movies from the cached data
2. For each movie, runs similarity search using percentage matching
3. Generates a CSV report with:
   - Movie title
   - Movies with ≥50% match
   - Movies with <50% match
"""

import sys
sys.path.append('..')

from similarity_engine_v2.dbr_specific_search import DBRSpecificSimilarity
import similarity_engine_v2.config as config
import pandas as pd
from typing import List, Dict
import pickle
import os

def batch_process_all_movies(output_csv: str = "all_movies_similarity_report.csv", max_movies: int = None):
    """
    Process all movies and generate similarity report
    
    Args:
        output_csv: Output CSV file path
        max_movies: Maximum number of movies to process (None = all)
    """
    print("="*80)
    print("📊 BATCH PROCESSING ALL MOVIES")
    print("="*80)
    
    # Verify percentage mode is enabled
    if not config.ENABLE_PERCENTAGE_MATCHING:
        print("\n⚠️  WARNING: ENABLE_PERCENTAGE_MATCHING is False!")
        print("   Enabling percentage matching mode...")
        config.ENABLE_PERCENTAGE_MATCHING = True
    
    print(f"\n✓ Percentage Matching Mode: {config.ENABLE_PERCENTAGE_MATCHING}")
    print(f"✓ Minimum Percentage Threshold: {config.MIN_PERCENTAGE_THRESHOLD}%")
    
    # Load data from cache
    print("\n🔧 Loading cached data...")
    
    # Check if cache exists
    cache_exists = (os.path.exists(config.CACHE_FILES['movies_db']) and 
                    os.path.exists(config.CACHE_FILES['metadata']))
    
    if not cache_exists:
        print("\n⚠️  Cache files not found. Building cache automatically...")
        print("   This may take a few minutes on first run...\n")
        
        try:
            # Import only when needed to avoid scipy dependency issues
            from similarity_engine_v2.core.data_loader import DataLoader
            from similarity_engine_v2.core.preprocessor import MoviePreprocessor
            from similarity_engine_v2.core.vector_builder import VectorBuilder
            
            print("   📂 Loading data...")
            loader = DataLoader()
            df = loader.load()
            
            print("   🔨 Processing movies...")
            preprocessor = MoviePreprocessor(df)
            movies_db = preprocessor.process_all_movies()
            
            print("   📊 Building vectors...")
            builder = VectorBuilder(movies_db)
            _, metadata = builder.build_embeddings()
            
            # Save to cache
            print("   💾 Saving cache...")
            with open(config.CACHE_FILES['movies_db'], 'wb') as f:
                pickle.dump(movies_db, f)
            with open(config.CACHE_FILES['metadata'], 'wb') as f:
                pickle.dump(metadata, f)
            
            print("   ✅ Cache built successfully!\n")
            
        except ImportError as e:
            print(f"\n❌ ERROR: Missing dependencies: {e}")
            print("   Please install required packages:")
            print("   pip3 install scipy tqdm pandas numpy --user")
            return None
        except Exception as e:
            print(f"\n❌ ERROR building cache: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    else:
        print("   ✓ Cache found!")
    
    print(f"   Loading movies_db from {config.CACHE_FILES['movies_db']}")
    with open(config.CACHE_FILES['movies_db'], 'rb') as f:
        movies_db = pickle.load(f)
    
    print(f"   Loading metadata from {config.CACHE_FILES['metadata']}")
    with open(config.CACHE_FILES['metadata'], 'rb') as f:
        metadata = pickle.load(f)

    
    # Initialize finder
    finder = DBRSpecificSimilarity(movies_db, metadata)
    
    # Get all movie titles
    all_movies = list(movies_db.keys())
    
    if max_movies:
        all_movies = all_movies[:max_movies]
    
    total_movies = len(all_movies)
    print(f"\n📋 Total Movies to Process: {total_movies}")
    
    # Results storage
    results_data = []
    
    # Process each movie
    for idx, movie_title in enumerate(all_movies, 1):
        print(f"\n[{idx}/{total_movies}] Processing: {movie_title}")
        
        try:
            # Run similarity search
            results = finder.find_dbr_specific_matches(
                movie_title,
                max_growth_diff=1.0,
                min_consecutive_dbrs=6,
                match_mode='percentage',
                min_percentage=config.MIN_PERCENTAGE_THRESHOLD
            )

            
            high_sim = results.get('high_similarity', [])
            low_sim = results.get('low_similarity', [])
            total_query_dbrs = results.get('total_query_dbrs', 0)
            
            # Extract movie titles
            high_sim_titles = [movie['similar_movie'] for movie in high_sim]
            low_sim_titles = [movie['similar_movie'] for movie in low_sim]
            
            # Get percentages for high similarity
            high_sim_percentages = [f"{movie['similar_movie']} ({movie['match_percentage']}%)" 
                                   for movie in high_sim]
            low_sim_percentages = [f"{movie['similar_movie']} ({movie['match_percentage']}%)" 
                                  for movie in low_sim]
            
            print(f"   ✓ High Similarity (≥{config.MIN_PERCENTAGE_THRESHOLD}%): {len(high_sim_titles)}")
            print(f"   ✓ Low Similarity (1-{config.MIN_PERCENTAGE_THRESHOLD-0.1}%): {len(low_sim_titles)}")
            
            # Store results
            results_data.append({
                'Query Movie': movie_title,
                'Total Query DBRs': total_query_dbrs,
                'High Similarity Count (≥50%)': len(high_sim_titles),
                'High Similarity Movies (≥50%)': ', '.join(high_sim_titles) if high_sim_titles else 'None',
                'High Similarity Details': ', '.join(high_sim_percentages) if high_sim_percentages else 'None',
                'Low Similarity Count (1-49%)': len(low_sim_titles),
                'Low Similarity Movies (1-49%)': ', '.join(low_sim_titles) if low_sim_titles else 'None',
                'Low Similarity Details': ', '.join(low_sim_percentages) if low_sim_percentages else 'None'
            })
            
        except Exception as e:
            print(f"   ❌ Error processing {movie_title}: {str(e)}")
            results_data.append({
                'Query Movie': movie_title,
                'Total Query DBRs': 0,
                'High Similarity Count (≥50%)': 0,
                'High Similarity Movies (≥50%)': f'Error: {str(e)}',
                'High Similarity Details': 'N/A',
                'Low Similarity Count (1-49%)': 0,
                'Low Similarity Movies (1-49%)': 'N/A',
                'Low Similarity Details': 'N/A'
            })
    
    # Create DataFrame
    df_results = pd.DataFrame(results_data)
    
    # Save to CSV
    df_results.to_csv(output_csv, index=False)
    
    print("\n" + "="*80)
    print("✅ BATCH PROCESSING COMPLETE")
    print("="*80)
    print(f"\n📊 Summary:")
    print(f"   Total Movies Processed: {len(df_results)}")
    print(f"   Movies with ≥50% Matches: {(df_results['High Similarity Count (≥50%)'] > 0).sum()}")
    print(f"   Movies with 1-49% Matches: {(df_results['Low Similarity Count (1-49%)'] > 0).sum()}")
    print(f"   Average High Similarity Count: {df_results['High Similarity Count (≥50%)'].mean():.2f}")
    print(f"   Average Low Similarity Count: {df_results['Low Similarity Count (1-49%)'].mean():.2f}")
    
    print(f"\n💾 Results saved to: {output_csv}")
    
    # Show sample results
    print(f"\n📋 Sample Results (first 5 movies):")
    print(df_results[['Query Movie', 'High Similarity Count (≥50%)', 'Low Similarity Count (1-49%)']].head(5).to_string(index=False))
    
    return df_results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch process all movies for similarity matching')
    parser.add_argument('--output', '-o', type=str, default='all_movies_similarity_report.csv',
                       help='Output CSV file path (default: all_movies_similarity_report.csv)')
    parser.add_argument('--max-movies', '-m', type=int, default=None,
                       help='Maximum number of movies to process (default: all)')
    parser.add_argument('--test', '-t', action='store_true',
                       help='Test mode: process only first 10 movies')
    
    args = parser.parse_args()
    
    if args.test:
        print("🧪 TEST MODE: Processing first 10 movies only")
        max_movies = 10
        output_csv = 'test_similarity_report.csv'
    else:
        max_movies = args.max_movies
        output_csv = args.output
    
    try:
        batch_process_all_movies(output_csv, max_movies)
    except Exception as e:
        print(f"\n❌ BATCH PROCESSING FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
