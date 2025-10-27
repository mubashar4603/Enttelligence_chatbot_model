#!/usr/bin/env python3
"""
Test 25 selected queries for the enhanced time-period aware system
"""

# Selected 25 diverse queries for testing
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

print("=" * 80)
print("25 SELECTED TEST QUERIES")
print("=" * 80)

for i, query in enumerate(selected_queries, 1):
    print(f"\n{i:2d}. {query}")

print("\n" + "=" * 80)
print(f"Total: {len(selected_queries)} queries")
print("=" * 80)

# Write to file
with open("selected_25_queries.txt", "w") as f:
    f.write("25 SELECTED TEST QUERIES\n")
    f.write("=" * 80 + "\n\n")
    for i, query in enumerate(selected_queries, 1):
        f.write(f"{i:2d}. {query}\n")
    f.write("\n" + "=" * 80 + "\n")

print("\n✅ Queries saved to: selected_25_queries.txt")

# Now create a test runner that will test each query
test_runner_code = '''
import os
import django
from django.conf import settings
import sys

# Setup Django
sys.path.insert(0, "/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from chat.intelligent_film_analytics_agent import IntelligentFilmAnalyticsAgent

# Initialize agent
agent = IntelligentFilmAnalyticsAgent()
agent.initialize_components()

selected_queries = [
    # Comp Titles
    "What are the best comp titles for Twisters?",
    "Find comparable titles for Dune: Part Two",
    "What are the best comp titles for Twisters last week?",
    "Find comp titles for Monkey Man last month",
    "What are comparable titles for Homestead in the last 7 days?",
    "Show me comp titles for Fantastic Four today",
    
    # Performance Analysis
    "How is Twisters performing?",
    "Is Dune: Part Two overperforming?",
    "Is Twisters overperforming last week?",
    "How is Dune: Part Two performing in the last 7 days?",
    "Performance of Weapons last week",
    "Is Monkey Man overperforming in the last 3 days?",
    
    # Overperforming/Underperforming
    "Is Twisters overperforming last week?",
    "Is Joker: Folie a Deux underperforming?",
    "Which movie overperformed most last week?",
    "What movies are underperforming this week?",
    
    # Sales & Revenue
    "What is Twisters estimated sales?",
    "What is Twisters sales last week?",
    "What movies had the highest sales last week?",
    
    # Best Performing
    "What is the best performing movie?",
    "Which movie is overperforming?",
    "Which movie overperformed most last week?",
    
    # Day-Specific
    "How did Twisters perform last Friday?",
    "Weekend performance for Monkey Man",
    "Thursday overperformance for Weapons"
]

print("=" * 80)
print("TESTING 25 SELECTED QUERIES")
print("=" * 80)

results = []
for i, query in enumerate(selected_queries, 1):
    print(f"\\n{'='*80}")
    print(f"Query {i}/25: {query}")
    print("-" * 80)
    
    try:
        result = agent.process_intelligent_query(query)
        print(f"\\n✅ SUCCESS")
        print(f"Type: {result.get('type', 'Unknown')}")
        print(f"Retrieved Count: {result.get('retrieved_count', 0)}")
        if 'message' in result:
            msg = result['message'][:200] if len(result['message']) > 200 else result['message']
            print(f"Message Preview: {msg}...")
        results.append({"query": query, "status": "success", "result": result})
    except Exception as e:
        print(f"\\n❌ ERROR: {str(e)}")
        results.append({"query": query, "status": "error", "error": str(e)})
    
    print("-" * 80)

# Summary
print("\\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

successful = sum(1 for r in results if r['status'] == 'success')
failed = sum(1 for r in results if r['status'] == 'error')

print(f"\\n✅ Successful: {successful}/25")
print(f"❌ Failed: {failed}/25")

if failed > 0:
    print("\\nFailed Queries:")
    for result in results:
        if result['status'] == 'error':
            print(f"  - {result['query']}: {result['error']}")

print("=" * 80)
'''

with open("run_test_25_queries.py", "w") as f:
    f.write(test_runner_code)

print("\n✅ Test runner created: run_test_25_queries.py")
print("\nTo run the tests, execute:")
print("  cd /home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main")
print("  python3 run_test_25_queries.py")

