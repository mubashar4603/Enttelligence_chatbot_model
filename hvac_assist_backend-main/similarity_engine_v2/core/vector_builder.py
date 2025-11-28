"""
Vector Builder Module
Generates fixed-dimension embeddings from growth curves
"""

import numpy as np
from typing import Dict, List, Tuple, Any
from similarity_engine_v2 import config

class VectorBuilder:
    """Build fixed-dimension vectors from variable-length growth curves"""
    
    def __init__(self, movies_db: Dict[str, Dict[str, Any]]):
        self.movies_db = movies_db
        self.embeddings = None
        self.metadata = []
    
    def build_embeddings(self, use_smoothed=True) -> Tuple[np.ndarray, List[Dict]]:
        """
        Build embeddings for all movies
        
        Args:
            use_smoothed: Use smoothed growth curves (True) or raw (False)
            
        Returns:
            Tuple of (embeddings_array, metadata_list)
        """
        if config.VERBOSE:
            print(f"\n🔄 Building embeddings (smoothed={use_smoothed})...")
        
        embeddings_list = []
        metadata_list = []
        
        for movie_id, (title, data) in enumerate(self.movies_db.items()):
            # Choose growth curve
            growth = data['growth_smoothed'] if use_smoothed else data['growth_raw']
            
            # Pad or truncate to fixed dimension
            vector = self._pad_or_truncate(growth, config.VECTOR_DIMENSION)
            
            # L2 normalize if enabled (for cosine similarity)
            if config.USE_L2_NORMALIZATION:
                vector = self._l2_normalize(vector)
            
            embeddings_list.append(vector)
            
            # Store metadata
            metadata_list.append({
                'movie_id': movie_id,
                'title': title,
                'dbr_range': data['dbr_range'],
                'dbr_list': data['dbr_list'],
                'total_revenue': data['total_revenue'],
                'active_days': data['active_days'],
                'avg_daily_revenue': data.get('avg_daily_revenue', 0)
            })
        
        self.embeddings = np.array(embeddings_list, dtype=np.float32)
        self.metadata = metadata_list
        
        if config.VERBOSE:
            print(f"✓ Built {len(embeddings_list)} embeddings")
            print(f"  Shape: {self.embeddings.shape}")
            print(f"  Dtype: {self.embeddings.dtype}")
        
        return self.embeddings, self.metadata
    
    def _pad_or_truncate(self, vector: np.ndarray, target_dim: int) -> np.ndarray:
        """
        Pad or truncate vector to target dimension
        
        Args:
            vector: Input vector
            target_dim: Target dimension
            
        Returns:
            np.ndarray: Padded/truncated vector
        """
        if len(vector) > target_dim:
            # Truncate
            return vector[:target_dim]
        elif len(vector) < target_dim:
            # Pad with zeros
            return np.pad(vector, (0, target_dim - len(vector)), 'constant', constant_values=0)
        else:
            return vector
    
    def _l2_normalize(self, vector: np.ndarray) -> np.ndarray:
        """
        L2 normalize vector (unit length)
        
        Args:
            vector: Input vector
            
        Returns:
            np.ndarray: Normalized vector
        """
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm
    
    def get_embedding(self, movie_id: int) -> np.ndarray:
        """Get embedding for a specific movie ID"""
        if self.embeddings is None:
            raise Exception("Embeddings not built. Call build_embeddings() first.")
        return self.embeddings[movie_id]
    
    def get_metadata(self, movie_id: int) -> Dict[str, Any]:
        """Get metadata for a specific movie ID"""
        if not self.metadata:
            raise Exception("Metadata not built. Call build_embeddings() first.")
        return self.metadata[movie_id]
    
    def find_movie_id(self, title: str) -> int:
        """Find movie ID by title"""
        for meta in self.metadata:
            if meta['title'] == title:
                return meta['movie_id']
        return -1


if __name__ == "__main__":
    # Test vector builder
    from data_loader import DataLoader
    from preprocessor import MoviePreprocessor
    
    loader = DataLoader()
    df = loader.load()
    
    preprocessor = MoviePreprocessor(df)
    movies_db = preprocessor.process_all_movies()
    
    builder = VectorBuilder(movies_db)
    embeddings, metadata = builder.build_embeddings(use_smoothed=True)
    
    print("\n" + "="*60)
    print("VECTOR BUILDER STATISTICS")
    print("="*60)
    print(f"Total embeddings: {len(embeddings)}")
    print(f"Embedding shape: {embeddings.shape}")
    print(f"Embedding dtype: {embeddings.dtype}")
    print(f"Memory usage: {embeddings.nbytes / 1024 / 1024:.2f} MB")
    
    # Show sample embedding
    print("\n" + "="*60)
    print("SAMPLE EMBEDDING")
    print("="*60)
    sample_id = 0
    sample_meta = metadata[sample_id]
    sample_emb = embeddings[sample_id]
    print(f"Movie: {sample_meta['title']}")
    print(f"Embedding (first 10): {sample_emb[:10]}")
    print(f"L2 norm: {np.linalg.norm(sample_emb):.6f}")
