#!/usr/bin/env python3
"""
Test Queries for Time-Period Aware Movie Performance Analysis

These queries test the enhanced system that considers:
- Day-by-day sales estimates based on date_sh
- Time periods (last week, last month, yesterday, etc.)
- Release dates for comparing movies at similar stages
"""

# ==================== COMP TITLES QUERIES ====================

comp_titles_queries = [
    # Basic comp titles queries
    "What are the best comp titles for Twisters?",
    "Find comparable titles for Dune: Part Two",
    "What movies are similar to Joker: Folie a Deux?",
    "Show me comp titles for Weapons",
    
    # Comp titles with time periods
    "What are the best comp titles for Twisters last week?",
    "Find comp titles for Monkey Man last month",
    "What are comparable titles for Homestead in the last 7 days?",
    "Show me comp titles for Jurrasic World Rebirth last week",
    
    # Comp titles with specific time periods
    "What are the best comp titles for Twisters last 3 days?",
    "Find comp titles for Dune: Part Two this week",
    "What movies are similar to Joker: Folie a Deux in the last 30 days?",
    
    # Comp titles for yesterday/today
    "What are comparable titles for Weapons yesterday?",
    "Show me comp titles for Fantastic Four today",
]

# ==================== PERFORMANCE ANALYSIS QUERIES ====================

performance_queries = [
    # Basic performance queries
    "How is Twisters performing?",
    "Is Dune: Part Two overperforming?",
    "Is Joker: Folie a Deux underperforming?",
    "Performance analysis of Weapons",
    "How is Monkey Man performing?",
    
    # Performance with time periods
    "Is Twisters overperforming last week?",
    "How is Dune: Part Two performing in the last 7 days?",
    "Is Joker: Folie a Deux underperforming this month?",
    "Performance of Weapons last week",
    "Is Monkey Man overperforming in the last 3 days?",
    
    # Performance with specific periods
    "Is Twisters underperforming yesterday?",
    "How is Dune: Part Two performing today?",
    "Is Joker: Folie a Deux overperforming last month?",
    "Performance of Weapons this week",
    "Is Monkey Man performing well last week?",
]

# ==================== BEST PERFORMING MOVIES QUERIES ====================

best_performing_queries = [
    # Without time period
    "What is the best performing movie?",
    "Which movie is overperforming?",
    "Show me the top performing movies",
    "Which movies are underperforming?",
    "What are the best comp titles?",
    
    # With time periods
    "Which movie overperformed last week?",
    "What is the best performing movie in the last 7 days?",
    "Which movies are underperforming last month?",
    "Show me top performing movies yesterday",
    "Which movie is performing best this week?",
    
    # Comparative queries
    "Which movie overperformed most last week?",
    "What movies overperformed in the last 3 days?",
    "Which movies are underperforming this month?",
]

# ==================== SALES AND REVENUE QUERIES ====================

sales_queries = [
    # Without time period
    "What is Twisters estimated sales?",
    "Sales prediction for Dune: Part Two",
    "Estimated revenue for Joker: Folie a Deux",
    "How much is Weapons making?",
    
    # With time periods
    "What is Twisters sales last week?",
    "Sales for Dune: Part Two in the last 7 days",
    "Estimated revenue for Joker: Folie a Deux last month",
    "How much is Weapons making yesterday?",
    "Revenue for Monkey Man this week",
    
    # Top sellers
    "What movies had the highest sales last week?",
    "Which movie made the most revenue yesterday?",
    "Top selling movies in the last month",
]

# ==================== OVERPERFORMING/UNDERPERFORMING QUERIES ====================

over_under_queries = [
    # Single movie
    "Is Twisters overperforming last week?",
    "Is Dune: Part Two underperforming?",
    "Is Joker: Folie a Deux overperforming today?",
    "Is Weapons underperforming last month?",
    
    # Multiple movies comparative
    "Which movie overperformed most last week?",
    "What movies are underperforming this week?",
    "Show me movies that overperformed yesterday",
    "Which movies underperformed last month?",
    
    # Combined queries
    "Is Twisters overperforming compared to comp titles last week?",
    "Which movie overperformed more: Twisters or Dune: Part Two last week?",
]

# ==================== DAY-OF-WEEK SPECIFIC QUERIES ====================

day_specific_queries = [
    "How did Twisters perform last Friday?",
    "Saturday performance for Dune: Part Two",
    "Sunday sales for Joker: Folie a Deux",
    "Thursday overperformance for Weapons",
    "Weekend performance for Monkey Man",
    
    # With time periods
    "How did Twisters perform last weekend?",
    "Weekend performance of Dune: Part Two last week",
    "Friday performance for Joker: Folie a Deux last month",
]

# ==================== COMBINED SCENARIO QUERIES ====================

scenario_queries = [
    # Scenario 1: Comparing movies across time
    "Is Twisters performing better than Dune: Part Two last week?",
    "Which movie performed better last week: Twisters or Weapons?",
    
    # Scenario 2: Time-series comparison
    "How is Twisters performing compared to last week?",
    "Is Dune: Part Two doing better than last month?",
    
    # Scenario 3: Comp titles with performance
    "What are the best comp titles for Twisters and how are they performing?",
    "Show me comp titles for Dune: Part Two and their last week performance",
    
    # Scenario 4: Best performers in specific time
    "Which movie overperformed most in the last 7 days?",
    "Show me the top 3 performing movies last week",
    "What are the best comp titles based on last week's performance?",
]

# ==================== EDGE CASES AND VALIDATION ====================

edge_case_queries = [
    # Mixed time periods
    "Comp titles for Twisters last week and their performance last month",
    
    # Today vs yesterday
    "Is Twisters performing better today than yesterday?",
    "Which movie sold more: today or yesterday?",
    
    # Multiple movies in one query
    "Compare performance of Twisters, Dune: Part Two, and Joker: Folie a Deux last week",
    
    # Specific date queries (if needed)
    "Comp titles for Twisters released on the same day as me",
    "Movies that released in the same week as Twisters",
]

# ==================== PRINT ALL TEST QUERIES ====================

if __name__ == "__main__":
    print("=" * 80)
    print("TEST QUERIES FOR TIME-PERIOD AWARE MOVIE PERFORMANCE ANALYSIS")
    print("=" * 80)
    
    all_queries = {
        "COMP TITLES": comp_titles_queries,
        "PERFORMANCE ANALYSIS": performance_queries,
        "BEST PERFORMING": best_performing_queries,
        "SALES & REVENUE": sales_queries,
        "OVERPERFORMING/UNDERPERFORMING": over_under_queries,
        "DAY-SPECIFIC": day_specific_queries,
        "SCENARIO": scenario_queries,
        "EDGE CASES": edge_case_queries,
    }
    
    for category, queries in all_queries.items():
        print(f"\n{category} QUERIES ({len(queries)} queries):")
        print("-" * 80)
        for i, query in enumerate(queries, 1):
            print(f"{i:2d}. {query}")
    
    total_queries = sum(len(queries) for queries in all_queries.values())
    print("\n" + "=" * 80)
    print(f"TOTAL: {total_queries} test queries")
    print("=" * 80)
    
    # Write to file for easy access
    with open("test_queries_list.txt", "w") as f:
        f.write("ALL TEST QUERIES\n")
        f.write("=" * 80 + "\n\n")
        for category, queries in all_queries.items():
            f.write(f"\n{category}\n")
            f.write("-" * 80 + "\n")
            for query in queries:
                f.write(f"{query}\n")
    
    print(f"\n✅ Queries saved to: test_queries_list.txt")

