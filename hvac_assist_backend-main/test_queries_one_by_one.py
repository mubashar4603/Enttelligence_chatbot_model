#!/usr/bin/env python3
"""
Test the 25 selected queries one by one
"""

import os
import sys
import django

# Add project directory to path
project_dir = "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main"
sys.path.insert(0, project_dir)

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from chat.intelligent_film_analytics_agent import IntelligentFilmAnalyticsAgent

# 25 selected test queries
selected_queries = [
    # Comp Titles (6 queries)
    "What are the best comp titles for Twisters?",
    "Find comparable titles for Dune: Part Two",
    "What are the best comp titles for Twisters last week?",
    "Find comp titles for Monkey Man last month",
    "What are comparable titles for Homestead in the last 7 days?",
    "Show me comp titles for Fantastic Four today",
    
    # Performance Analysis (6 queries)
    "How is Twisters performing?",
    "Is Dune: Part Two overperforming?",
    "Is Twisters overperforming last week?",
    "How is Dune: Part Two performing in the last 7 days?",
    "Performance of Weapons last week",
    "Is Monkey Man overperforming in the last 3 days?",
    
    # Overperforming/Underperforming (4 queries)
    "Is Twisters overperforming last week?",
    "Is Joker: Folie a Deux underperforming?",
    "Which movie overperformed most last week?",
    "What movies are underperforming this week?",
    
    # Sales & Revenue (3 queries)
    "What is Twisters estimated sales?",
    "What is Twisters sales last week?",
    "What movies had the highest sales last week?",
    
    # Best Performing (3 queries)
    "What is the best performing movie?",
    "Which movie is overperforming?",
    "Which movie overperformed most last week?",
    
    # Day-Specific (3 queries)
    "How did Twisters perform last Friday?",
    "Weekend performance for Monkey Man",
    "Thursday overperformance for Weapons"
]

def test_queries():
    """Test all queries one by one"""
    print("=" * 80)
    print("TESTING 25 SELECTED QUERIES FOR TIME-PERIOD AWARE SYSTEM")
    print("=" * 80)
    print("\nInitializing Intelligent Film Analytics Agent...")
    
    try:
        # Initialize agent
        agent = IntelligentFilmAnalyticsAgent()
        agent.initialize_components()
        print("✅ Agent initialized successfully\n")
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        return
    
    results = []
    
    for i, query in enumerate(selected_queries, 1):
        print("\n" + "=" * 80)
        print(f"Query {i}/25: {query}")
        print("-" * 80)
        
        try:
            # Process query
            result = agent.process_intelligent_query(query)
            
            # Extract key information
            status = "SUCCESS"
            result_type = result.get('type', 'Unknown')
            retrieved_count = result.get('retrieved_count', 0)
            message = result.get('message', 'No message')
            
            # Truncate message for display
            if len(message) > 200:
                msg_preview = message[:200] + "..."
            else:
                msg_preview = message
            
            print(f"\n✅ {status}")
            print(f"Type: {result_type}")
            print(f"Retrieved Documents: {retrieved_count}")
            print(f"\nResponse Preview:\n{msg_preview}")
            
            results.append({
                "query": query,
                "status": "success",
                "type": result_type,
                "retrieved_count": retrieved_count
            })
            
        except Exception as e:
            print(f"\n❌ ERROR")
            print(f"Error: {str(e)}")
            results.append({
                "query": query,
                "status": "error",
                "error": str(e)
            })
        
        print("-" * 80)
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    successful = sum(1 for r in results if r['status'] == 'success')
    failed = sum(1 for r in results if r['status'] == 'error')
    
    print(f"\n✅ Successful: {successful}/25")
    print(f"❌ Failed: {failed}/25")
    print(f"Success Rate: {(successful/25)*100:.1f}%")
    
    if failed > 0:
        print("\n" + "-" * 80)
        print("FAILED QUERIES:")
        print("-" * 80)
        for result in results:
            if result['status'] == 'error':
                print(f"\n❌ {result['query']}")
                print(f"   Error: {result['error']}")
    
    # Print query type breakdown
    print("\n" + "-" * 80)
    print("QUERY TYPE BREAKDOWN:")
    print("-" * 80)
    type_counts = {}
    for result in results:
        if result['status'] == 'success':
            qtype = result.get('type', 'Unknown')
            type_counts[qtype] = type_counts.get(qtype, 0) + 1
    
    for qtype, count in sorted(type_counts.items()):
        print(f"  {qtype}: {count}")
    
    print("\n" + "=" * 80)
    
    # Save results to file
    import json
    with open("test_results_25_queries.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Detailed results saved to: test_results_25_queries.json")
    print("=" * 80)
    
    return results

if __name__ == "__main__":
    test_queries()

