# engine/embeddings.py
import numpy as np
from config import EMBED_DIMS, RANDOM_STATE

try:
    import umap
    UMAP_AVAILABLE = True
except:
    from sklearn.decomposition import PCA
    UMAP_AVAILABLE = False

def make_embedding(matrix: np.ndarray):
    if UMAP_AVAILABLE:
        reducer = umap.UMAP(n_components=EMBED_DIMS, random_state=RANDOM_STATE)
    else:
        reducer = PCA(n_components=EMBED_DIMS, random_state=RANDOM_STATE)

    emb = reducer.fit_transform(matrix)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return emb / norms