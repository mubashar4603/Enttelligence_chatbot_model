"""
Movie Preprocessor Module
Builds per-movie data structures with DBR mapping and growth calculation
"""

import pandas as pd
import numpy as np
from scipy.ndimage import gaussian_filter1d
from typing import Dict, List, Tuple, Any
from tqdm import tqdm
import config

class MoviePreprocessor:
    """Process raw movie data into structured format with growth curves"""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.movies_db = {}
    
    def process_all_movies(self) -> Dict[str, Dict[str, Any]]:
        """
        Process all movies and build database
        
        Returns:
            Dict: {movie_title: movie_data_dict}
        """
        if config.VERBOSE:
            print("\n🔨 Processing movies...")
        
        movies_db = {}
        skipped = 0
        
        # Group by title
        grouped = self.df.groupby('title')
        
        for title, group in tqdm(grouped, desc="Processing movies", disable=not config.VERBOSE):
            movie_data = self._process_single_movie(title, group)
            
            if movie_data is None:
                skipped += 1
                continue
            
            movies_db[title] = movie_data
        
        self.movies_db = movies_db
        
        if config.VERBOSE:
            print(f"✓ Processed {len(movies_db)} movies")
            print(f"  Skipped {skipped} movies (insufficient data)")
        
        return movies_db
    
    def _process_single_movie(self, title: str, group: pd.DataFrame) -> Dict[str, Any]:
        """
        Process a single movie
        
        Args:
            title: Movie title
            group: DataFrame for this movie
            
        Returns:
            Dict with movie data or None if insufficient data
        """
        # Sort by DBR
        group = group.sort_values('dbr')
        
        # Aggregate by DBR (in case of duplicates)
        agg_dict = {
            'daily_revenue': 'sum',
            'cumulative_revenue': 'max'
        }
        
        # Include growth_pct if it exists in the data
        if 'growth_pct' in group.columns:
            agg_dict['growth_pct'] = 'mean'  # Average if duplicates
        
        group = group.groupby('dbr').agg(agg_dict).reset_index().sort_values('dbr')
        
        # Filter active days (revenue above threshold)
        active = group[group['daily_revenue'] > config.MIN_REVENUE_THRESHOLD].copy()
        
        # Check minimum requirements
        if len(active) < config.MIN_ACTIVE_DAYS:
            return None
        
        total_revenue = group['cumulative_revenue'].max()
        if total_revenue < config.MIN_TOTAL_REVENUE:
            return None
        
        # Extract data
        dbr_list = active['dbr'].tolist()
        revenue_list = active['daily_revenue'].values
        
        # Use original Growth (%) from CSV if available, otherwise calculate
        if 'growth_pct' in active.columns:
            growth_raw = active['growth_pct'].values
            # Handle NaN values
            growth_raw = np.nan_to_num(growth_raw, nan=0.0, posinf=999.0, neginf=-99.0)
        else:
            # Fallback: calculate growth rate
            growth_raw = self._calculate_growth(revenue_list)
        
        # Apply Gaussian smoothing if enabled
        if config.USE_GAUSSIAN_SMOOTHING:
            growth_smoothed = gaussian_filter1d(growth_raw, sigma=config.SMOOTHING_SIGMA)
        else:
            growth_smoothed = growth_raw.copy()
        
        return {
            'title': title,
            'dbr_list': dbr_list,
            'dbr_range': (int(min(dbr_list)), int(max(dbr_list))),
            'revenue': revenue_list.tolist(),
            'growth_raw': growth_raw,
            'growth_smoothed': growth_smoothed,
            'total_revenue': float(total_revenue),
            'active_days': len(active),
            'avg_daily_revenue': float(np.mean(revenue_list))
        }
    
    def _calculate_growth(self, revenue: np.ndarray) -> np.ndarray:
        """
        Calculate daily growth rate
        
        Args:
            revenue: Array of daily revenue values
            
        Returns:
            np.ndarray: Growth rate percentages
        """
        # Calculate percentage change
        growth = np.diff(revenue) / (revenue[:-1] + 1e-8) * 100.0
        
        # Handle NaN and inf
        growth = np.nan_to_num(growth, nan=0.0, posinf=999.0, neginf=-99.0)
        
        # Clip extreme values
        growth = np.clip(growth, -99, 999)
        
        return growth
    
    def get_movie(self, title: str) -> Dict[str, Any]:
        """Get processed data for a specific movie"""
        return self.movies_db.get(title)
    
    def get_all_titles(self) -> List[str]:
        """Get list of all processed movie titles"""
        return list(self.movies_db.keys())
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about processed movies"""
        if not self.movies_db:
            return {}
        
        active_days_list = [m['active_days'] for m in self.movies_db.values()]
        revenues = [m['total_revenue'] for m in self.movies_db.values()]
        
        return {
            'total_movies': len(self.movies_db),
            'avg_active_days': np.mean(active_days_list),
            'median_active_days': np.median(active_days_list),
            'min_active_days': min(active_days_list),
            'max_active_days': max(active_days_list),
            'avg_revenue': np.mean(revenues),
            'median_revenue': np.median(revenues),
            'total_revenue_all': sum(revenues)
        }


if __name__ == "__main__":
    # Test preprocessor
    from data_loader import DataLoader
    
    loader = DataLoader()
    df = loader.load()
    
    preprocessor = MoviePreprocessor(df)
    movies_db = preprocessor.process_all_movies()
    
    print("\n" + "="*60)
    print("PREPROCESSING STATISTICS")
    print("="*60)
    stats = preprocessor.get_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    # Show sample movie
    print("\n" + "="*60)
    print("SAMPLE MOVIE DATA")
    print("="*60)
    sample_title = list(movies_db.keys())[0]
    sample_data = movies_db[sample_title]
    print(f"\nMovie: {sample_title}")
    for key, value in sample_data.items():
        if isinstance(value, (list, np.ndarray)) and len(value) > 5:
            print(f"  {key}: {value[:5]}... (length: {len(value)})")
        else:
            print(f"  {key}: {value}")
