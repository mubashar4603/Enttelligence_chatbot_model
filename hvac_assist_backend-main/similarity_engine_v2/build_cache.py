"""
Quick script to build cache files
"""
import sys
sys.path.append('..')

print("Building cache...") 

from similarity_engine_v2.llm_agent import MovieSimilarityAgent

print("Initializing agent...")
agent = MovieSimilarityAgent()

print("✅ Cache built successfully!")
print("You can now run: python3 batch_process_all_movies.py --test")
