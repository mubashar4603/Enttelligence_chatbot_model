"""
Quick test script for optimized query processor
Tests all query types with the optimized system
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from chat.optimized_query_processor import get_query_processor

def test_query(query, description):
    """Test a single query and print results"""
    print(f"\n{'='*80}")
    print(f"🧪 TEST: {description}")
    print(f"📝 Query: {query}")
    print(f"{'='*80}")
    
    try:
        processor = get_query_processor()
        response = processor.process_query(query)
        
        print(f"\n✅ Type: {response.get('type')}")
        print(f"\n📄 Response:\n{response.get('message', 'No message')}")
        
        if response.get('data'):
            print(f"\n📊 Data available: Yes")
        
        if response.get('sources'):
            print(f"\n📚 Sources: {len(response.get('sources'))} retrieved")
        
        if response.get('retrieved_count'):
            print(f"📥 Retrieved count: {response.get('retrieved_count')}")
        
        print(f"\n{'-'*80}")
        return True
    
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run comprehensive tests"""
    print("\n" + "="*80)
    print("🚀 OPTIMIZED QUERY PROCESSOR TEST SUITE")
    print("="*80)
    
    tests = [
        # Conversational (RAG) queries
        ("Tell me about Avatar 2 and where it's playing", "Conversational - Movie Info"),
        ("What amenities does AMC Empire 25 have?", "Conversational - Theater Info"),
        
        # Analytical queries
        ("How many horror movies are there?", "Analytical - Count"),
        ("What's the sum of reserved seats for all movies?", "Analytical - Sum"),
        ("Average ticket price for IMAX movies", "Analytical - Average"),
        ("Top 5 most popular movies", "Analytical - Top N"),
        
        # Comparative queries
        ("Compare IMAX vs Standard format prices", "Comparative - Format"),
        ("AMC vs Regal theater comparison", "Comparative - Theaters"),
        
        # Complex queries
        ("Show me horror movies in California priced under $15", "Complex - Multi-filter"),
    ]
    
    success_count = 0
    total_count = len(tests)
    
    for query, description in tests:
        if test_query(query, description):
            success_count += 1
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 TEST SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Successful: {success_count}/{total_count}")
    print(f"❌ Failed: {total_count - success_count}/{total_count}")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    main()

