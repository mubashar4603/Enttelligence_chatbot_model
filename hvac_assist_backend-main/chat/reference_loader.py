import os
import sys
import pickle
import numpy as np
from pathlib import Path
import pdfplumber
import openai
from sentence_transformers import SentenceTransformer

# Constants
DOCS_PATH = Path("Related_doca")
CACHE_PATH = Path("embedding_cache.pkl")
BUILD_FLAG_PATH = Path("embedding_cache.building")

CHUNK_SIZE = 500
OVERLAP = 50
EMBED_MODEL = "text-embedding-ada-002"

# Local model for fast similarity
local_embed_model = SentenceTransformer("all-MiniLM-L6-v2")

# Set your OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")


def is_cache_building():
    return BUILD_FLAG_PATH.exists()


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def extract_text_chunks():
    all_chunks = []
    for file in DOCS_PATH.glob("**/*.pdf"):
        try:
            with pdfplumber.open(file) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            chunks = chunk_text(text)
            for chunk in chunks:
                all_chunks.append((chunk, str(file)))
        except Exception as e:
            print(f"Error processing {file}: {e}", file=sys.stderr)
    return all_chunks


def get_openai_embedding(text):
    try:
        result = openai.Embedding.create(
            model=EMBED_MODEL,
            input=text,
        )
        return result["data"][0]["embedding"]
    except Exception as e:
        print(f"Embedding failed: {e}", file=sys.stderr)
        return None


def build_embedding_cache():
    if is_cache_building():
        return None

    try:
        BUILD_FLAG_PATH.touch()
        print("Building reference embeddings...", file=sys.stderr)

        chunks = extract_text_chunks()
        if not chunks:
            return []

        texts, metas = zip(*chunks)

        embeddings = []
        for i, text in enumerate(texts):
            emb = get_openai_embedding(text)
            if emb:
                embeddings.append(emb)
                print(f"Embedded {i + 1}/{len(texts)}", file=sys.stderr)
            else:
                embeddings.append([0.0] * 1536)  # fallback padding

        embeddings = np.array(embeddings)

        with open(CACHE_PATH, "wb") as f:
            pickle.dump((embeddings, metas), f)

        print("Reference embeddings built successfully.", file=sys.stderr)
        return embeddings, metas

    finally:
        if BUILD_FLAG_PATH.exists():
            BUILD_FLAG_PATH.unlink()


def get_np_embedding_cache():
    if not CACHE_PATH.exists():
        return None, None
    with open(CACHE_PATH, "rb") as f:
        embeddings, metas = pickle.load(f)
    return embeddings, metas


def search_related_chunks(query, top_k=5, max_chunk_length=1000):
    print(f"search_related_chunks called (pid={os.getpid()})", file=sys.stderr)

    if is_cache_building():
        return "[Reference index is being built. Please try again later.]"

    embeddings, metas = get_np_embedding_cache()
    if embeddings is None or metas is None:
        cache = build_embedding_cache()
        if cache is None:
            return "[Reference index is being built. Please try again later.]"
        if not cache:
            return "[No reference documents found.]"
        embeddings, metas = get_np_embedding_cache()

    query_emb = local_embed_model.encode([query])[0]
    query_emb = np.array(query_emb)

    dot_products = np.dot(embeddings, query_emb)
    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_emb)
    similarities = dot_products / norms

    top_indices = similarities.argsort()[::-1][:top_k]
    results = [metas[i][0][:max_chunk_length] for i in top_indices]

    return "\n".join(results)
