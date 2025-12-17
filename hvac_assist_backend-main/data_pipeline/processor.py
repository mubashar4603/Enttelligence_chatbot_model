import sys
import os
import pickle
import numpy as np
import pandas as pd

# Add parent directory to path to import similarity_engine_v2
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from similarity_engine_v2 import config
from similarity_engine_v2.core.data_loader import DataLoader
from similarity_engine_v2.core.preprocessor import MoviePreprocessor
from similarity_engine_v2.core.vector_builder import VectorBuilder
from logger import setup_logger

logger = setup_logger()

class PipelineProcessor:
    """
    Handles data processing and embedding generation using
    the existing similarity engine logic.
    """
    def __init__(self, input_file_path):
        self.input_file_path = input_file_path

    def run(self):
        """
        Run the processing pipeline:
        0. Check/Calculate Growth (%) if missing
        1. Load Data
        2. Preprocess
        3. Build Embeddings
        4. Save to Cache
        """
        logger.info("🚀 Starting Data Processing...")

        # 0. Ensure Growth Column Exists
        # The user specifically requested to mimic 'calculate_growth.py' if the column is missing
        processed_file_path = self._ensure_growth_column(self.input_file_path)
        
        # 1. Load Data
        logger.info(f"📂 Loading data from: {processed_file_path}")
        
        try:
            # Initialize DataLoader with custom path
            # Temporarily override config value for this run
            original_data_path = config.DATA_PATH
            config.DATA_PATH = processed_file_path
            
            loader = DataLoader() # Reads config.DATA_PATH
            df = loader.load()
            
            logger.info(f"   Rows loaded: {len(df)}")
            
            # 2. Preprocess
            logger.info("🧹 Preprocessing...")
            preprocessor = MoviePreprocessor(df)
            movies_db = preprocessor.process_all_movies()
            logger.info(f"   Valid Movies Processed: {len(movies_db)}")
            
            # 3. Build Embeddings
            logger.info("🧠 Generating Embeddings (VectorBuilder)...")
            builder = VectorBuilder(movies_db)
            embeddings, metadata = builder.build_embeddings(
                use_smoothed=config.USE_GAUSSIAN_SMOOTHING
            )
            logger.info(f"   Embeddings Generated: {len(embeddings)}")

            # 4. Save to Cache
            self._save_to_cache(movies_db, metadata, embeddings)
            
            # Restore config
            config.DATA_PATH = original_data_path
            
            # Clean up temp file if we created one
            if processed_file_path != self.input_file_path and os.path.exists(processed_file_path):
                os.remove(processed_file_path)
                logger.info("🧹 Cleaned up temporary file")
            
            return True

        except Exception as e:
            logger.error(f"❌ Processing Error: {str(e)}")
            raise

    def _ensure_growth_column(self, input_path):
        """
        Check if 'Growth (%)' column exists. If not, calculate it and save to temp file.
        Returns path to correct file (original or temp).
        """
        logger.info("🔍 Checking for 'Growth (%)' column...")
        
        try:
            # Try reading just header/first row to check columns
            try:
                df = pd.read_csv(input_path, encoding='utf-8', nrows=5)
            except:
                try:
                    df = pd.read_csv(input_path, encoding='utf-16', sep='\t', nrows=5)
                except:
                    df = pd.read_csv(input_path, encoding='ISO-8859-1', nrows=5)

            # Check if headers need cleaning
            df.columns = df.columns.str.strip()
            
            if 'Growth (%)' in df.columns:
                logger.info("✅ 'Growth (%)' column found. Proceeding with original file.")
                return input_path
            
            logger.info("⚠️ 'Growth (%)' column MISSING. Calculating it now...")
            return self._calculate_and_save_growth(input_path)
            
        except Exception as e:
            logger.error(f"Error checking columns: {e}")
            raise e

    def _calculate_and_save_growth(self, input_path):
        """
        Logic ported from similarity_engine_v2/calculate_growth.py
        """
        import pandas as pd
        import numpy as np

        logger.info("🧮 performing manual growth calculation...")
        
        # Read full file
        try:
            df = pd.read_csv(input_path, encoding='utf-8')
        except:
            try:
                df = pd.read_csv(input_path, encoding='utf-16', sep='\t')
            except:
                df = pd.read_csv(input_path, encoding='ISO-8859-1')
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Map 'Cuml Sales Estimate' (no dot) to 'Cuml. Sales Estimate' if needed for consistency
        if 'Cuml Sales Estimate' in df.columns and 'Cuml. Sales Estimate' not in df.columns:
            df.rename(columns={'Cuml Sales Estimate': 'Cuml. Sales Estimate'}, inplace=True)

        target_col = 'Cuml. Sales Estimate'
        if target_col not in df.columns:
             # Try finding it nicely
             candidates = [c for c in df.columns if 'Cuml' in c and 'Sales' in c]
             if candidates:
                 target_col = candidates[0]
             else:
                 raise ValueError("Could not find Cumulative Sales column for calculation")

        # Convert to numeric
        df[target_col] = df[target_col].astype(str).str.replace(',', '').str.replace('"', '')
        df[target_col] = pd.to_numeric(df[target_col], errors='coerce')
        
        # Sort
        # Ensure we have Title and DBR
        if 'DBR' not in df.columns or 'Title' not in df.columns:
             # Try case insensitive lookup
             df.columns = [c.capitalize() if c.lower() in ['title', 'dbr'] else c for c in df.columns]
        
        df = df.sort_values(['Title', 'DBR']).reset_index(drop=True)
        
        # Calculate
        df['Growth (%)'] = np.nan
        
        # We can vectorize this for speed instead of iterating
        # Group by title
        grouped = df.groupby('Title')[target_col]
        
        # Shifted value (Previous Day)
        prev_cumulative = grouped.shift(1)
        
        # Calculate Growth: ((Curr - Prev) / Prev) * 100
        # Avoid division by zero
        growth = ((df[target_col] - prev_cumulative) / prev_cumulative) * 100
        
        # Fill NaN (first day) with 0
        growth = growth.fillna(0)
        
        # Handle infinite growth (if prev was 0) - though shift(1) handles it, division by zero might give inf
        growth = growth.replace([np.inf, -np.inf], 0)
        
        df['Growth (%)'] = growth.round(2)
        
        # Save to temp file
        temp_path = os.path.join(os.path.dirname(input_path), "temp_processed_growth.csv")
        df.to_csv(temp_path, index=False, encoding='utf-8')
        
        logger.info(f"✅ Growth calculated and saved to {temp_path}")
        return temp_path

    def _save_to_cache(self, movies_db, metadata, embeddings):
        """Save check-pointed artifacts to cache"""
        logger.info("💾 Saving artifacts to cache...")
        
        # Ensure cache dir exists
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        
        # Save movies_db
        with open(config.CACHE_FILES['movies_db'], 'wb') as f:
            pickle.dump(movies_db, f)
            
        # Save metadata
        with open(config.CACHE_FILES['metadata'], 'wb') as f:
            pickle.dump(metadata, f)
            
        # Save embeddings
        np.save(config.CACHE_FILES['embeddings'], embeddings)
        
        logger.info(f"✅ Cache updated at {config.CACHE_DIR}")
