"""
FAISS Indexer Module
Manages FAISS index creation and search
"""

import numpy as np
import faiss
import os
from typing import Tuple, List
import config

class FAISSIndexer:
    """Build and manage FAISS indexes for similarity search"""
    
    def __init__(self):
        self.index_fast = None
        self.index_exact = None
        self.dimension = config.VECTOR_DIMENSION
        self.n_movies = 0
    
    def build_indexes(self, embeddings: np.ndarray) -> Tuple[faiss.Index, faiss.Index]:
        """
        Build FAISS indexes
        
        Args:
            embeddings: Numpy array of shape (n_movies, dimension)
            
        Returns:
            Tuple of (fast_index, exact_index)
        """
        self.n_movies = embeddings.shape[0]
        
        if config.VERBOSE:
            print(f"\n🔧 Building FAISS indexes for {self.n_movies} movies...")
        
        # Build exact index (always)
        self.index_exact = self._build_flat_index(embeddings)
        
        # Build fast index (IVF-PQ) if dataset is large enough
        if self.n_movies >= config.USE_IVF_THRESHOLD:
            self.index_fast = self._build_ivf_pq_index(embeddings)
        else:
            # Use flat index for small datasets
            self.index_fast = self.index_exact
            if config.VERBOSE:
                print(f"  Using Flat index (dataset < {config.USE_IVF_THRESHOLD} movies)")
        
        return self.index_fast, self.index_exact
    
    def _build_flat_index(self, embeddings: np.ndarray) -> faiss.Index:
        """
        Build flat (exact) index
        
        Args:
            embeddings: Embeddings array
            
        Returns:
            faiss.Index: Flat index
        """
        if config.VERBOSE:
            print("  Building Flat index (exact search)...")
        
        # Use L2 distance (for normalized vectors, L2 is equivalent to cosine)
        index = faiss.IndexFlatL2(self.dimension)
        index.add(embeddings)
        
        if config.VERBOSE:
            print(f"    ✓ Flat index built: {index.ntotal} vectors")
        
        return index
    
    def _build_ivf_pq_index(self, embeddings: np.ndarray) -> faiss.Index:
        """
        Build IVF-PQ index for fast approximate search
        
        Args:
            embeddings: Embeddings array
            
        Returns:
            faiss.Index: IVF-PQ index
        """
        if config.VERBOSE:
            print("  Building IVF-PQ index (fast approximate search)...")
        
        # Calculate nlist (number of clusters)
        nlist = self._calculate_nlist(self.n_movies)
        
        # PQ parameters
        m = config.PQ_M
        nbits = config.PQ_NBITS
        
        if config.VERBOSE:
            print(f"    Parameters: nlist={nlist}, m={m}, nbits={nbits}")
        
        # Create quantizer (for clustering)
        quantizer = faiss.IndexFlatL2(self.dimension)
        
        # Create IVF-PQ index
        index = faiss.IndexIVFPQ(quantizer, self.dimension, nlist, m, nbits)
        
        # Train index
        if config.VERBOSE:
            print("    Training index...")
        index.train(embeddings)
        
        # Add vectors
        if config.VERBOSE:
            print("    Adding vectors...")
        index.add(embeddings)
        
        # Set search parameters
        index.nprobe = config.IVF_NPROBE
        
        if config.VERBOSE:
            print(f"    ✓ IVF-PQ index built: {index.ntotal} vectors, nprobe={index.nprobe}")
        
        return index
    
    def _calculate_nlist(self, n_movies: int) -> int:
        """
        Calculate optimal nlist for IVF
        
        Args:
            n_movies: Number of movies
            
        Returns:
            int: nlist value
        """
        # Use sqrt(N) or N * ratio, whichever is smaller
        nlist_sqrt = int(np.sqrt(n_movies))
        nlist_ratio = int(n_movies * config.IVF_NLIST_RATIO)
        
        nlist = min(nlist_sqrt, nlist_ratio)
        
        # Clamp to min/max
        nlist = max(config.IVF_NLIST_MIN, min(nlist, config.IVF_NLIST_MAX))
        
        return nlist
    
    def search(self, query_vector: np.ndarray, k: int, use_fast=True) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search for similar vectors
        
        Args:
            query_vector: Query vector (1D or 2D)
            k: Number of results
            use_fast: Use fast index (True) or exact index (False)
            
        Returns:
            Tuple of (distances, indices)
        """
        # Ensure 2D shape
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        
        # Choose index
        index = self.index_fast if use_fast else self.index_exact
        
        # Search
        distances, indices = index.search(query_vector, k)
        
        return distances, indices
    
    def save_indexes(self, fast_path: str = None, exact_path: str = None):
        """Save indexes to disk"""
        fast_path = fast_path or config.CACHE_FILES['index_fast']
        exact_path = exact_path or config.CACHE_FILES['index_exact']
        
        if self.index_fast is not None and self.index_fast != self.index_exact:
            faiss.write_index(self.index_fast, fast_path)
            if config.VERBOSE:
                print(f"  Saved fast index to: {fast_path}")
        
        if self.index_exact is not None:
            faiss.write_index(self.index_exact, exact_path)
            if config.VERBOSE:
                print(f"  Saved exact index to: {exact_path}")
    
    def load_indexes(self, fast_path: str = None, exact_path: str = None) -> bool:
        """
        Load indexes from disk
        
        Returns:
            bool: True if successful
        """
        fast_path = fast_path or config.CACHE_FILES['index_fast']
        exact_path = exact_path or config.CACHE_FILES['index_exact']
        
        try:
            if os.path.exists(exact_path):
                self.index_exact = faiss.read_index(exact_path)
                if config.VERBOSE:
                    print(f"  Loaded exact index: {self.index_exact.ntotal} vectors")
            
            if os.path.exists(fast_path):
                self.index_fast = faiss.read_index(fast_path)
                if config.VERBOSE:
                    print(f"  Loaded fast index: {self.index_fast.ntotal} vectors")
            else:
                # Use exact as fast if fast doesn't exist
                self.index_fast = self.index_exact
            
            return True
        except Exception as e:
            if config.VERBOSE:
                print(f"  Failed to load indexes: {e}")
            return False


if __name__ == "__main__":
    # Test FAISS indexer
    import sys
    sys.path.append('..')
    from core.data_loader import DataLoader
    from core.preprocessor import MoviePreprocessor
    from core.vector_builder import VectorBuilder
    
    loader = DataLoader()
    df = loader.load()
    
    preprocessor = MoviePreprocessor(df)
    movies_db = preprocessor.process_all_movies()
    
    builder = VectorBuilder(movies_db)
    embeddings, metadata = builder.build_embeddings()
    
    indexer = FAISSIndexer()
    fast_idx, exact_idx = indexer.build_indexes(embeddings)
    
    print("\n" + "="*60)
    print("FAISS INDEXER TEST")
    print("="*60)
    print(f"Fast index type: {type(fast_idx).__name__}")
    print(f"Exact index type: {type(exact_idx).__name__}")
    print(f"Fast index vectors: {fast_idx.ntotal}")
    print(f"Exact index vectors: {exact_idx.ntotal}")
    
    # Test search
    print("\n" + "="*60)
    print("SEARCH TEST")
    print("="*60)
    query_vec = embeddings[0]
    distances, indices = indexer.search(query_vec, k=5, use_fast=True)
    
    print(f"Query movie: {metadata[0]['title']}")
    print(f"\nTop 5 similar (fast index):")
    for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
        print(f"  {i+1}. {metadata[idx]['title']} (distance: {dist:.4f})")
