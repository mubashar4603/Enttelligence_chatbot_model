# engine/similarity_engine.py
import os
import numpy as np
import pandas as pd
import faiss
from config import CACHE_DIR, DATA_PATH
from .curve_builder import build_resampled_matrix
from .embeddings import make_embedding

class MovieSimilarityEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._load_or_build()
        self._initialized = True

    def _load_or_build(self):
        cache_files = ["matrix.npy", "embeddings.npy", "titles.npy", "meta.csv", "faiss.index"]
        if all(os.path.exists(os.path.join(CACHE_DIR, f)) for f in cache_files):
            print("Loading from cache...")
            self.matrix = np.load(os.path.join(CACHE_DIR, "matrix.npy"))
            self.embeddings = np.load(os.path.join(CACHE_DIR, "embeddings.npy"))
            self.titles = np.load(os.path.join(CACHE_DIR, "titles.npy"), allow_pickle=True).tolist()
            self.meta = pd.read_csv(os.path.join(CACHE_DIR, "meta.csv"))
            self.index = faiss.read_index(os.path.join(CACHE_DIR, "faiss.index"))
        else:
            print("Building engine from CSV...")
            df = pd.read_csv(DATA_PATH)
            df["DBR"] = df["DBR"].astype(float)
            df["cumulative_revenue"] = df["cumulative_revenue"].astype(float)

            self.matrix, self.titles, self.meta = build_resampled_matrix(df)
            self.embeddings = make_embedding(self.matrix)

            # Save cache
            np.save(os.path.join(CACHE_DIR, "matrix.npy"), self.matrix)
            np.save(os.path.join(CACHE_DIR, "embeddings.npy"), self.embeddings)
            np.save(os.path.join(CACHE_DIR, "titles.npy"), self.titles)
            self.meta.to_csv(os.path.join(CACHE_DIR, "meta.csv"), index=False)

            # FAISS
            dim = self.embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dim)
            self.index.add(self.embeddings.astype('float32'))
            faiss.write_index(self.index, os.path.join(CACHE_DIR, "faiss.index"))

        def search(vec, k=6):
            if vec.ndim == 1: vec = vec.reshape(1, -1)
            D, I = self.index.search(vec.astype('float32'), k)
            return I.flatten(), D.flatten()
        self.search = search

    def find_similar(self, title: str, top_k=5):
        if title not in self.titles:
            return None
        idx = self.titles.index(title)
        vec = self.embeddings[idx]
        I, S = self.search(vec, top_k + 1)
        mask = I != idx
        return [(self.titles[i], float(S[i])) for i, s in zip(I[mask], S[mask])][:top_k]