"""
Quick Test Script for Similarity Engine V2
Tests basic functionality with sample queries
"""

from main import MovieSimilarityEngine, format_results
import time

def test_engine():
    """Test the similarity engine with sample queries"""
    
    print("=" * 80)
    print("🧪 TESTING SIMILARITY ENGINE V2")
    print("=" * 80)
    
    # Initialize engine
    print("\n1. Initializing engine...")
    start = time.time()
    engine = MovieSimilarityEngine(force_rebuild=False)
    init_time = time.time() - start
    print(f"   ✓ Initialized in {init_time:.2f}s")
    
    # Get statistics
    print("\n2. System Statistics:")
    stats = engine.get_statistics()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Get sample movies
    all_titles = engine.get_all_titles()
    print(f"\n3. Total movies indexed: {len(all_titles)}")
    print(f"   Sample titles:")
    for i, title in enumerate(all_titles[:10], 1):
        print(f"   {i}. {title}")
    
    # Test searches
    print("\n4. Running test searches...")
    test_movies = all_titles[:3]  # Test first 3 movies
    
    for i, movie in enumerate(test_movies, 1):
        print(f"\n   Test {i}: Searching for '{movie}'")
        start = time.time()
        results = engine.search(movie, k=5, min_score=80)
        search_time = time.time() - start
        
        if results['status'] == 'success':
            print(f"   ✓ Found {results['total_found']} similar movies in {search_time*1000:.2f}ms")
            print(f"   Top match: {results['similar_movies'][0]['title']} ({results['similar_movies'][0]['similarity_score']}%)")
        else:
            print(f"   ⚠️  {results.get('message', 'No results')}")
    
    # Performance summary
    print("\n" + "=" * 80)
    print("✅ TESTS COMPLETED")
    print("=" * 80)
    
    return engine


if __name__ == "__main__":
    engine = test_engine()
    
    # Interactive prompt
    print("\n" + "=" * 80)
    print("💬 Try a custom search? (or press Enter to skip)")
    print("=" * 80)
    
    user_input = input("🔍 Movie name: ").strip()
    
    if user_input:
        results = engine.search(user_input, k=5)
        print("\n" + format_results(results))
    
    print("\n👋 Done!")
