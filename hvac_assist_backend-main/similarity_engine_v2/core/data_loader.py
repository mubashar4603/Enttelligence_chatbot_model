"""
Data Loader Module
Handles CSV loading and data cleaning
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
import config

class DataLoader:
    """Load and clean movie revenue data from CSV"""
    
    def __init__(self, data_path: str = None):
        self.data_path = data_path or config.DATA_PATH
        self.df = None
    
    def load(self) -> pd.DataFrame:
        """
        Load CSV data with proper encoding and cleaning
        
        Returns:
            pd.DataFrame: Cleaned dataframe
        """
        if config.VERBOSE:
            print(f"📂 Loading data from: {self.data_path}")
        
        try:
            # Load with UTF-16 encoding (as per data analysis)
            df = pd.read_csv(self.data_path, encoding='utf-16', sep='\t')
            
            if config.VERBOSE:
                print(f"   Loaded {len(df)} rows")
            
            # Clean and standardize
            df = self._clean_dataframe(df)
            
            self.df = df
            return df
            
        except Exception as e:
            raise Exception(f"Failed to load data: {e}")
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and standardize dataframe columns
        
        Args:
            df: Raw dataframe
            
        Returns:
            pd.DataFrame: Cleaned dataframe
        """
        # Rename columns to standard names
        column_mapping = {
            'Title': 'title',
            'DBR': 'dbr',
            'Sales Estimate': 'daily_revenue',
            'cumulative_revenue': 'cumulative_revenue',
            'Growth (%)': 'growth_pct'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Clean title
        df['title'] = df['title'].astype(str).str.strip()
        
        # Clean revenue columns (remove commas, convert to numeric)
        for col in ['daily_revenue', 'cumulative_revenue']:
            if col in df.columns:
                # Remove scientific notation entries
                df.loc[df[col].astype(str).str.contains(r'[eE]', na=False, regex=True), col] = 0
                
                # Remove commas and non-numeric characters except . and -
                df[col] = (df[col].astype(str)
                          .str.replace(',', '')
                          .str.replace(r'[^0-9.\-]', '', regex=True)
                          .str.strip())
                
                # Convert to numeric
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Clean DBR column
        df['dbr'] = pd.to_numeric(df['dbr'], errors='coerce').fillna(0).astype(int)
        
        # Clean growth percentage if exists
        if 'growth_pct' in df.columns:
            df['growth_pct'] = pd.to_numeric(df['growth_pct'], errors='coerce').fillna(0)
        
        # Select only needed columns
        needed_cols = ['title', 'dbr', 'daily_revenue', 'cumulative_revenue']
        if 'growth_pct' in df.columns:
            needed_cols.append('growth_pct')
        
        df = df[needed_cols]
        
        if config.VERBOSE:
            print(f"   Cleaned data: {len(df)} rows, {len(df.columns)} columns")
            print(f"   Unique movies: {df['title'].nunique()}")
        
        return df
    
    def get_movie_data(self, title: str) -> pd.DataFrame:
        """
        Get data for a specific movie
        
        Args:
            title: Movie title
            
        Returns:
            pd.DataFrame: Movie data sorted by DBR
        """
        if self.df is None:
            raise Exception("Data not loaded. Call load() first.")
        
        movie_data = self.df[self.df['title'] == title].sort_values('dbr')
        return movie_data
    
    def get_all_titles(self) -> list:
        """Get list of all unique movie titles"""
        if self.df is None:
            raise Exception("Data not loaded. Call load() first.")
        
        return sorted(self.df['title'].unique().tolist())
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get dataset statistics"""
        if self.df is None:
            raise Exception("Data not loaded. Call load() first.")
        
        return {
            'total_rows': len(self.df),
            'unique_movies': self.df['title'].nunique(),
            'dbr_range': (int(self.df['dbr'].min()), int(self.df['dbr'].max())),
            'total_revenue_range': (
                float(self.df['daily_revenue'].min()),
                float(self.df['daily_revenue'].max())
            ),
            'avg_rows_per_movie': len(self.df) / self.df['title'].nunique()
        }


if __name__ == "__main__":
    # Test data loader
    loader = DataLoader()
    df = loader.load()
    
    print("\n" + "="*60)
    print("DATA STATISTICS")
    print("="*60)
    stats = loader.get_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    print("\n" + "="*60)
    print("SAMPLE DATA")
    print("="*60)
    print(df.head(10))
