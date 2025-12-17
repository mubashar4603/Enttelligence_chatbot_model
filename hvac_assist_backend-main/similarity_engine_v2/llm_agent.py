"""
LLM Agent with Tool Calling for DBR Similarity Search
Uses Ollama (Llama 3) to dynamically select tools and parameters
"""

import json
from decimal import Decimal
import requests
import pandas as pd
from typing import Dict, Any, List, Optional
from similarity_engine_v2.dbr_specific_search import DBRSpecificSimilarity
from similarity_engine_v2.core.data_loader import DataLoader
from similarity_engine_v2.core.preprocessor import MoviePreprocessor
from similarity_engine_v2.core.vector_builder import VectorBuilder
import pickle
import os
import similarity_engine_v2.config as config
import re

# Import analytical agent
try:
    from chat.intelligent_film_analytics_agent import get_intelligent_agent as get_analytical_agent
    ANALYTICAL_AGENT_AVAILABLE = True
except ImportError:
    ANALYTICAL_AGENT_AVAILABLE = False
    print("⚠️  Analytical agent not available")

class MovieSimilarityAgent:
    """
    Agent that uses LLM tool calling to interact with the similarity engine.
    """
    

    def __init__(self):
        self.finder = None
        self.analytical_agent = None
        self.last_cache_update = 0 # Track timestamp of cache
        self._initialize_system()
        
    def _initialize_system(self):
        """Initialize the underlying similarity engine from CACHE ONLY"""
        print("🔧 Initializing Similarity Engine (Cache Mode)...")
        
        # Check cache files
        cache_files = [config.CACHE_FILES['movies_db'], config.CACHE_FILES['metadata']]
        if all(os.path.exists(f) for f in cache_files):
            try:
                self._load_from_cache()
                print("✅ Engine Loaded from Cache!\n")
            except Exception as e:
                print(f"❌ Failed to load cache: {e}")
                print("⚠️ Please run the data pipeline to generate cache.")
        else:
            print("⚠️ Cache not found. Please run 'python manage.py run_data_pipeline' to build the index.")
            # Do NOT build from scratch automatically to respect pipeline arch
            
    def _load_from_cache(self):
        """Helper to load data from check-pointed cache files"""
        print("📦 Loading cache files...")
        with open(config.CACHE_FILES['movies_db'], 'rb') as f:
            movies_db = pickle.load(f)
        with open(config.CACHE_FILES['metadata'], 'rb') as f:
            metadata = pickle.load(f)
            
        self.finder = DBRSpecificSimilarity(movies_db, metadata)
        
        # Update timestamp tracking
        self.last_cache_update = os.path.getmtime(config.CACHE_FILES['metadata'])

    def _check_for_updates(self):
        """Check if cache file has been modified and reload if necessary"""
        try:
            if not os.path.exists(config.CACHE_FILES['metadata']):
                return

            current_mtime = os.path.getmtime(config.CACHE_FILES['metadata'])
            if current_mtime > self.last_cache_update:
                print("\n🔄 New data detected! Reloading cache...")
                self._load_from_cache()
                print("✅ Cache reloaded successfully.\n")
        except Exception as e:
            print(f"⚠️ Error checking for updates: {e}")

    def _get_analytical_agent(self):
        """Lazy initialization of analytical agent"""
        if self.analytical_agent is None and ANALYTICAL_AGENT_AVAILABLE:
            self.analytical_agent = get_analytical_agent()
        return self.analytical_agent

    # ==================== TOOLS ====================
    
    def search_similar_movies(self, movie_name: str, k: int = 5, max_growth_diff: float = 1.0, min_consecutive_dbrs: int = 1) -> str:
        """
        Tool to find similar movies based on DBR growth patterns.
        
        Args:
            movie_name: Name of the movie to search for
            k: Number of results to return (default 5)
            max_growth_diff: Maximum allowed difference in growth % (default 1.0)
            min_consecutive_dbrs: Minimum consecutive days matching (default 3)
        """
        # Find best match for title
        target = self._find_best_match(movie_name)
        if not target:
            return json.dumps({"error": f"Movie '{movie_name}' not found in database."})
            
        # Execute search
        results = self.finder.find_dbr_specific_matches(
            target,
            max_growth_diff=float(max_growth_diff),
            min_consecutive_dbrs=int(min_consecutive_dbrs)
        )
        
        if not results:
            return json.dumps({
                "status": "no_results",
                "message": f"No similar movies found for '{target}' with criteria: diff<={max_growth_diff}%, min_days>={min_consecutive_dbrs}"
            })
            
        # Sort and limit
        results.sort(key=lambda x: sum(r['dbr_count'] for r in x['matching_ranges']), reverse=True)
        top_results = results[:int(k)]
        
        # Format results for LLM
        # formatted = []
        # for res in top_results:
        #     ranges = res['matching_ranges']
        #     total_days = sum(r['dbr_count'] for r in ranges)
        #     avg_diff = sum(r['avg_difference'] for r in ranges) / len(ranges)
        #
        #     formatted.append({
        #         "title": res['similar_movie'],
        #         "total_revenue": res['total_revenue'],
        #         "matching_days": total_days,
        #         "avg_growth_diff": round(avg_diff, 2),
        #         "ranges_count": len(ranges)
        #     })
            
        return json.dumps({
            "status": "success",
            "query_movie": target,
            "count": len(top_results),
            "results": top_results
        })

    def compare_movies(self, movie1: str, movie2: str, max_growth_diff: float = 1.0) -> str:
        """
        Tool to compare two specific movies.
        """
        target1 = self._find_best_match(movie1)
        target2 = self._find_best_match(movie2)
        
        if not target1: return json.dumps({"error": f"Movie '{movie1}' not found"})
        if not target2: return json.dumps({"error": f"Movie '{movie2}' not found"})
        

        # Reuse the finder logic but filter for just the second movie
        results = self.finder.find_dbr_specific_matches(
            target1, 
            max_growth_diff=max_growth_diff,
            min_consecutive_dbrs=1 # Relax constraint for direct comparison
        )
        
        match = next((r for r in results if r['similar_movie'] == target2), None)
        
        if match:
            return json.dumps({
                "status": "success",
                "movie1": target1,
                "movie2": target2,
                "details": match['matching_ranges']
            })
        else:
            return json.dumps({"status": "error", "message": f"No significant similarity found between {target1} and {target2}"})

    def get_movie_performance(self, movie_name: str, min_dbr: int = None, max_dbr: int = None) -> str:
        """
        Get raw performance data for a single movie, optionally filtered by DBR range.
        Returns a JSON string with the data.
        """
        # Resolve movie name
        target = self._find_best_match(movie_name)
        if not target: return json.dumps({"error": f"Movie '{movie_name}' not found"})
            
        movie_data = self.finder.movies_db[target]
        dbr_list = movie_data['dbr_list']
        growth_raw = movie_data['growth_raw']
        
        # Filter data based on range
        filtered_data = []
        for i, dbr in enumerate(dbr_list[:-1]): # -1 because growth is diff
            if min_dbr is not None and dbr < min_dbr:
                continue
            if max_dbr is not None and dbr > max_dbr:
                continue
                
            if i < len(growth_raw):
                filtered_data.append({
                    "dbr": dbr,
                    "daily_growth": round(growth_raw[i], 2)
                })
                
        return json.dumps({
            "status": "success",
            "movie": target,
            "performance": filtered_data,
            "total_revenue": movie_data['total_revenue']
        })
    
    def query_analytical_engine(self, query: str) -> str:
        """
        Tool to query the analytical engine for:
        - Revenue, sales, earnings analysis
        - Theater information (locations, showtimes, capacity)
        - Market opportunities and predictions
        - Movie information (plot, actors, director)
        - Database queries (how many, list all, show me)
        
        Returns exact response from analytical agent as JSON string.
        """
        if not ANALYTICAL_AGENT_AVAILABLE:
            return json.dumps({
                "error": "Analytical engine is not available. Please check system configuration."
            })
        
        try:
            agent = self._get_analytical_agent()
            if agent is None:
                return json.dumps({
                    "error": "Failed to initialize analytical agent."
                })
            
            # Call analytical agent and get response
            result = agent.process_intelligent_query(query)
            
            # Return the result as JSON string
            def decimal_serializer(obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                raise TypeError(f"Type {type(obj)} not serializable")

            return json.dumps(result, default=decimal_serializer)
            
        except Exception as e:
            return json.dumps({
                "error": f"Analytical engine error: {str(e)}"
            })

    def search_similar_movies(self, movie_name: str, k: int = 5, max_growth_diff: float = 1.0, min_consecutive_dbrs: int = 1, min_dbr: int = None, max_dbr: int = None) -> str:
        """
        Search for similar movies based on DBR growth patterns, optionally within a specific DBR range.
        Returns a JSON string with the results.
        """
        # Resolve movie name
        target = self._find_best_match(movie_name)
        if not target: return json.dumps({"error": f"Movie '{movie_name}' not found"})

        results = self.finder.find_dbr_specific_matches(
            target, 
            max_growth_diff=max_growth_diff,
            min_consecutive_dbrs=min_consecutive_dbrs,
            min_dbr=min_dbr,
            max_dbr=max_dbr
        )
        
        # Check if percentage mode is enabled
        if config.ENABLE_PERCENTAGE_MATCHING:
            # Percentage mode - results is a dict with 'high_similarity' and 'low_similarity'
            high_sim = results.get('high_similarity', [])
            low_sim = results.get('low_similarity', [])
            
            # Sort high similarity by percentage (descending) and take top k
            high_sim.sort(key=lambda x: x.get('match_percentage', 0), reverse=True)
            top_high = high_sim[:k]
            
            # Sort low similarity by percentage (descending)
            low_sim.sort(key=lambda x: x.get('match_percentage', 0), reverse=True)
            
            return json.dumps({
                "status": "success",
                "mode": "percentage",
                "query_movie": target,
                "total_query_dbrs": results.get('total_query_dbrs', 0),
                "high_similarity": top_high,
                "low_similarity": low_sim
            })
        else:
            # Consecutive mode - results is a list
            # Sort by total matching DBRs (descending) and take top k
            results.sort(key=lambda x: sum(r['dbr_count'] for r in x['matching_ranges']), reverse=True)
            top_results = results[:k]
            
            return json.dumps({
                "status": "success",
                "mode": "consecutive",
                "query_movie": target,
                "results": top_results
            })

    def _find_best_match(self, partial_name: str) -> Optional[str]:
        """Helper to find exact movie title"""
        if not partial_name: return None
        titles = list(self.finder.movies_db.keys())
        
        # Exact
        for t in titles:
            if t.lower() == partial_name.lower(): return t
        # Contains
        matches = [t for t in titles if partial_name.lower() in t.lower()]
        if matches: return min(matches, key=len)
        return None

    # ==================== LLM INTERACTION ====================

    def process_query(self, user_query: str) -> Dict[str, str]:
        """
        Main loop:
        1. Check for data updates
        2. Send query + tool definitions to LLM
        3. LLM decides tool call
        4. Execute tool
        5. Send result back to LLM for final answer
        
        Returns:
            Dict with 'message' and 'error' keys
        """
        # Auto-reload check
        self._check_for_updates()
        
        tools_def = [
            {
                "name": "search_similar_movies",
                "description": "Finds movies with similar box office growth patterns. Use this for queries like 'similar to X', 'top 10 like X'.Example: 'what are the compareable titles of twisters. what are the similar titles of twisters'",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "movie_name": {"type": "string", "description": "Name of the movie to search for"},
                        "k": {"type": "integer", "description": "Number of movies to return (default 5)"},
                        "max_growth_diff": {"type": "number", "description": "Max allowed difference in growth percentage (default 1.0)"},
                        "min_consecutive_dbrs": {"type": "integer", "description": "Min consecutive matching days (default 1)"},
                        "min_dbr": {"type": "integer", "description": "Minimum DBR (Days Before/After Release) to consider for similarity. e.g., -10 for 10 days before release."},
                        "max_dbr": {"type": "integer", "description": "Maximum DBR (Days Before/After Release) to consider for similarity. e.g., 30 for 30 days after release."}
                    },
                    "required": ["movie_name"]
                }
            },
            {
                "name": "compare_movies",
                "description": "Compares two specific movies to see how their growth patterns overlap.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "movie1": {"type": "string", "description": "First movie name"},
                        "movie2": {"type": "string", "description": "Second movie name"},
                        "max_growth_diff": {"type": "number", "description": "Max allowed difference (default 1.0)"}
                    },
                    "required": ["movie1", "movie2"]
                }
            },
            {
                "name": "get_movie_performance",
                "description": "Gets raw performance data (daily growth percentages) for a single movie, optionally filtered by a DBR range.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "movie_name": {"type": "string", "description": "Name of the movie to get performance for"},
                        "min_dbr": {"type": "integer", "description": "Minimum DBR (Days Before/After Release) to include in the performance data. e.g., -10 for 10 days before release."},
                        "max_dbr": {"type": "integer", "description": "Maximum DBR (Days Before/After Release) to include in the performance data. e.g., 30 for 30 days after release."}
                    },
                    "required": ["movie_name"]
                }
            },
            {
                "name": "query_analytical_engine",
                "description": """Query the analytical engine for questions about:
- Revenue, sales, earnings analysis (e.g., 'What is the revenue for Dune?')
- Theater information (e.g., 'Show me theaters in New York', 'How many theaters?')
- Market opportunities and predictions (e.g., 'Where are market opportunities?')
- Movie information from database (e.g., 'Tell me about Twisters plot', 'Who are the actors?')
- General database queries (e.g., 'List all movies', 'How many seats available?', Which movies are currently in their first weekend (DIR -1 to DIR 3)?)

Use this when the query does NOT ask for similarity/comparison between movies.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "User's original query to send to analytical engine"}
                    },
                    "required": ["query"]
                }
            }
        ]
        
        system_prompt = f"""You are a helpful movie box office analyst.
You have access to the following tools:

{json.dumps(tools_def, indent=2)}

To use a tool, you MUST respond with a JSON object in this format:
{{
    "tool": "tool_name",
    "parameters": {{ ... }}
}}

If no tool is needed, just answer normally.
If the user asks for "top 10" but only 5 exist, just return the 5.

⚠️ CRITICAL WARNING FOR PERCENTAGES:
When user says "5%", you MUST extract 5, NOT 0.05
When user says "2%", you MUST extract 2, NOT 0.02
When user says "0.5%", you MUST extract 0.5, NOT 0.005
The max_growth_diff parameter expects the NUMBER before the % sign, NOT a decimal!

STRICT INSTRUCTIONS FOR PARAMETERS:
1. EXTRACTING 'k' (number of results):
   - Look for phrases like "top X", "X movies", "X similar movies" in the user query
   - Extract the number X and use it as the value for 'k'
   - Examples:
     * "top 100 movies" -> k=100
     * "top 50" -> k=50
     * "find 20 similar movies" -> k=20
     * "which 15 movies" -> k=15
   - If no number is mentioned, use default k=5

2. EXTRACTING 'min_consecutive_dbrs':
   - Look for phrases like "minimum X consecutive DBR", "at least X DBR", "X consecutive days"
   - Extract the number and use it as min_consecutive_dbrs
   - Examples:
     * "minimum 3 consecutive DBR" -> min_consecutive_dbrs=3
     * "at least 10 DBR" -> min_consecutive_dbrs=10
   - Default: min_consecutive_dbrs=2 if not mentioned
   - EXCEPTION: If the user specifies a SHORT range (e.g., "first week", "range -5 to 5"), use a lower value like min_consecutive_dbrs=3 to ensure results are found.

3. EXTRACTING 'max_growth_diff' (PERCENTAGE HANDLING):
   - Look for phrases like "X% diff", "X% difference", "X% tolerance"
   - Extract ONLY the number X that appears BEFORE the % symbol
   - DO NOT convert to decimal! If user says "5%", use 5, NOT 0.05!
   - Examples:
     * User says "2% diff" -> extract "2" -> max_growth_diff=2
     * User says "5% difference" -> extract "5" -> max_growth_diff=5
     * User says "0.5% tolerance" -> extract "0.5" -> max_growth_diff=0.5
     * User says "3% diff" -> extract "3" -> max_growth_diff=3
     * User says "10%" -> extract "10" -> max_growth_diff=10
   - Default: max_growth_diff=1 if not mentioned

4. EXTRACTING 'min_dbr' and 'max_dbr' (RANGE HANDLING):
   - "First week" / "Week 1" -> min_dbr=0, max_dbr=7
   - "Post-release" / "After release" -> min_dbr=0
   - "Pre-release" / "Before release" -> max_dbr=-1
   - "Positive DBRs" -> min_dbr=0
   - "Negative DBRs" -> max_dbr=-1
   - "Range X to Y" -> min_dbr=X, max_dbr=Y
   - "From day X to day Y" -> min_dbr=X, max_dbr=Y
   - IMPORTANT: These range parameters apply to BOTH `get_movie_performance` AND `search_similar_movies`.

5. TOOL SELECTION GUIDELINES:
   - Use `get_movie_performance` when user asks about a SINGLE movie's DBR-based performance data (e.g., "How did Twisters perform in the first week by DBR?").
   - Use `search_similar_movies` when user asks for SIMILAR movies based on growth patterns (e.g., "Which movies performed like Twisters?").
   - Use `compare_movies` when user asks to COMPARE two specific movies' growth patterns.
   - Use `query_analytical_engine` when user asks about:
     * Revenue, sales, earnings (not DBR-specific growth)
     * Theaters, showtimes, locations
     * Market opportunities, predictions
     * Movie information (plot, actors, director)
     * General database queries (how many, list all, show me)
     * ANY analytical question that is NOT about similarity/comparison

6. COMPLETE EXAMPLES:
   - Input: "Find similar movies to Twisters"
     Output: {{"tool": "search_similar_movies", "parameters": {{"movie_name": "Twisters", "k": 5, "max_growth_diff": 1, "min_consecutive_dbrs": 1}}}}
   
   - Input: "How did Twisters perform in the first week?"
     Output: {{"tool": "get_movie_performance", "parameters": {{"movie_name": "Twisters", "min_dbr": 0, "max_dbr": 7}}}}
   
   - Input: "Which movies are similar to Twisters in the first week?"
     Output: {{"tool": "search_similar_movies", "parameters": {{"movie_name": "Twisters", "min_dbr": 0, "max_dbr": 7, "k": 5, "max_growth_diff": 1, "min_consecutive_dbrs": 1}}}}

   - Input: "Find top 50 similar movies to Twisters with 2% diff"
     Output: {{"tool": "search_similar_movies", "parameters": {{"movie_name": "Twisters", "k": 50, "max_growth_diff": 2, "min_consecutive_dbrs": 1}}}}
   
   - Input: "Show me 20 movies like Inception with at least 5 DBR"
     Output: {{"tool": "search_similar_movies", "parameters": {{"movie_name": "Inception", "k": 20, "max_growth_diff": 1, "min_consecutive_dbrs": 5}}}}
   
   - Input: "Get top 10 movies with 5% difference"
     Output: {{"tool": "search_similar_movies", "parameters": {{"movie_name": "movies", "k": 10, "max_growth_diff": 5, "min_consecutive_dbrs": 1}}}}
   
   - Input: "Find similar movies to Twisters in range -5 to 5"
     Output: {{"tool": "search_similar_movies", "parameters": {{"movie_name": "Twisters", "min_dbr": -5, "max_dbr": 5, "k": 5, "max_growth_diff": 1, "min_consecutive_dbrs": 1}}}}
"""

        try:
            # 1. Ask LLM to decide tool
            response = self._call_ollama(system_prompt, user_query)
            
            # Check for error in initial call
            if response.startswith("Error:"):
                return {"message": "", "error": response}
            
            # 2. Check for tool call
            # Try to find JSON in response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    action = json.loads(json_match.group(0))
                    
                    if "tool" in action and "parameters" in action:
                        tool_name = action["tool"]
                        params = action["parameters"]
                        
                        print(f"🛠️  LLM Decided: {tool_name}({params})")
                        
                        # Execute Tool
                        result = None
                        table_str = ""
                        llm_context_data = []
                        
                        if tool_name == "search_similar_movies":
                            # HEURISTIC FIX: Ensure "first week" queries get correct parameters if LLM misses them
                            lower_query = user_query.lower()
                            if "first week" in lower_query or "week 1" in lower_query:
                                if "min_dbr" not in params: params["min_dbr"] = 0
                                if "max_dbr" not in params: params["max_dbr"] = 7
                                # Force lower consecutive DBRs for short range
                                if params.get("min_consecutive_dbrs", 6) > 1:
                                    params["min_consecutive_dbrs"] = 1
                                    
                            result = self.search_similar_movies(**params)
                            # Process table data
                            try:
                                res_json = json.loads(result)
                                if res_json.get("status") == "success":
                                    mode = res_json.get("mode", "consecutive")
                                    
                                    if mode == "percentage":
                                        # Percentage mode - create two tables
                                        high_sim = res_json.get('high_similarity', [])
                                        low_sim = res_json.get('low_similarity', [])
                                        total_query_dbrs = res_json.get('total_query_dbrs', 0)
                                        
                                        # Table 1: High Similarity (≥50%)
                                        if high_sim:
                                            df_high = self.finder.export_to_dataframe_with_percentage(
                                                res_json['query_movie'], 
                                                high_sim, 
                                                include_details=True
                                            )
                                            table_high = df_high.to_markdown(index=False)
                                        else:
                                            table_high = "No movies found with ≥50% match"
                                        
                                        # Table 2: Low Similarity (1-49%)
                                        if low_sim:
                                            df_low = self.finder.export_to_dataframe_with_percentage(
                                                res_json['query_movie'], 
                                                low_sim, 
                                                include_details=False
                                            )
                                            table_low = df_low.to_markdown(index=False)
                                        else:
                                            table_low = "No movies found with 1-49% match"
                                        
                                        # Combine tables
                                        table_str = f"## High Similarity (≥50% DBR Match)\n\n{table_high}\n\n## Low Similarity (1-49% DBR Match)\n\n{table_low}"
                                        
                                        # Create context for LLM with percentage info
                                        for item in high_sim:
                                            match_pct = item.get('match_percentage', 0)
                                            total_matching = item.get('total_matching_dbrs', 0)
                                            matched_dbrs = item.get('matched_dbrs', [])
                                            
                                            # Get DBR ranges
                                            dbr_ranges = []
                                            for r in item['matching_ranges']:
                                                dbr_ranges.append(f"{r['dbr_start']} to {r['dbr_end']}")
                                            
                                            llm_context_data.append({
                                                "movie": item['similar_movie'],
                                                "match_percentage": match_pct,
                                                "total_matching_dbrs": total_matching,
                                                "total_query_dbrs": total_query_dbrs,
                                                "dbr_ranges": ", ".join(dbr_ranges),
                                                "sample_matched_dbrs": str(matched_dbrs[:10]) if len(matched_dbrs) > 10 else str(matched_dbrs)
                                            })
                                    else:
                                        # Consecutive mode (original behavior)
                                        df = self.finder.export_to_dataframe(res_json['query_movie'], res_json['results'])
                                        table_str = df.to_markdown(index=False)
                                        
                                        # Create Ultra-Compact Context for LLM (Just movie names and total DBR count)
                                        for item in res_json['results']:
                                            total_dbr_count = sum(r['dbr_count'] for r in item['matching_ranges'])
                                            # Get the overall range
                                            all_dbr_starts = [r['dbr_start'] for r in item['matching_ranges']]
                                            all_dbr_ends = [r['dbr_end'] for r in item['matching_ranges']]
                                            min_dbr = min(all_dbr_starts)
                                            max_dbr = max(all_dbr_ends)
                                            
                                            llm_context_data.append({
                                                "movie": item['similar_movie'],
                                                "total_matching_dbrs": total_dbr_count,
                                                "dbr_range": f"{min_dbr} to {max_dbr}"
                                            })
                            except:
                                pass
                                
                        elif tool_name == "compare_movies":
                            result = self.compare_movies(**params)
                            # Process table data
                            try:
                                res_json = json.loads(result)
                                if res_json.get("status") == "success":
                                    # 1. Create DataFrame for User Table
                                    formatted_res = [{
                                        'similar_movie': res_json['movie2'],
                                        'matching_ranges': res_json['details']
                                    }]
                                    df = self.finder.export_to_dataframe(res_json['movie1'], formatted_res)
                                    table_str = df.to_markdown(index=False)
                                    
                                    # 2. Compact Context
                                    total_dbr_count = sum(r['dbr_count'] for r in res_json['details'])
                                    all_dbr_starts = [r['dbr_start'] for r in res_json['details']]
                                    all_dbr_ends = [r['dbr_end'] for r in res_json['details']]
                                    min_dbr = min(all_dbr_starts)
                                    max_dbr = max(all_dbr_ends)
                                    
                                    llm_context_data = [{
                                        "movie1": res_json['movie1'],
                                        "movie2": res_json['movie2'],
                                        "total_matching_dbrs": total_dbr_count,
                                        "dbr_range": f"{min_dbr} to {max_dbr}"
                                    }]
                            except:
                                pass

                        elif tool_name == "get_movie_performance":
                            result = self.get_movie_performance(**params)
                            try:
                                res_json = json.loads(result)
                                if res_json.get("status") == "success":
                                    # 1. Create DataFrame for User Table
                                    perf_data = res_json['performance']
                                    if perf_data:
                                        df = pd.DataFrame(perf_data)
                                        table_str = df.to_markdown(index=False)
                                        
                                        # 2. Context for LLM
                                        dbrs = [p['dbr'] for p in perf_data]
                                        min_dbr = min(dbrs)
                                        max_dbr = max(dbrs)
                                        avg_growth = sum(p['daily_growth'] for p in perf_data) / len(perf_data)
                                        
                                        llm_context_data = [{
                                            "movie": res_json['movie'],
                                            "dbr_range": f"{min_dbr} to {max_dbr}",
                                            "data_points": len(perf_data),
                                            "avg_daily_growth": round(avg_growth, 2)
                                        }]
                                    else:
                                        llm_context_data = []
                            except:
                                pass
                        
                        elif tool_name == "query_analytical_engine":
                            # Call analytical engine directly
                            result = self.query_analytical_engine(**params)
                            try:
                                res_json = json.loads(result)
                                
                                # Check for error
                                if "error" in res_json:
                                    return {"message": "", "error": res_json["error"]}
                                
                                # Analytical agent returns a complete response dict
                                # with 'message', 'type', 'data', etc.
                                # Return it directly without further LLM processing
                                return res_json
                                
                            except json.JSONDecodeError:
                                # If not JSON, return as error
                                return {"message": "", "error": f"Invalid response from analytical engine: {result}"}
                            
                        # 3. Send result back to LLM for final analysis
                        # Use ultra-compact context to save tokens and ensure all results are acknowledged
                        
                        # Check if percentage mode is active
                        is_percentage_mode = config.ENABLE_PERCENTAGE_MATCHING
                        
                        if is_percentage_mode:
                            final_prompt = f"""
User Query: {user_query}
Tool Result Summary: {json.dumps(llm_context_data, indent=2)}

⚠️ CRITICAL: Do NOT make up or hallucinate any movie names. ONLY use the movies listed in the Tool Result Summary above.
If the Tool Result Summary is empty [], that means NO similar movies were found. In that case, clearly state "No similar movies were found" and DO NOT list any movies.

PERCENTAGE MATCHING MODE:
The system is using percentage-based matching. Each result shows:
- match_percentage: What percentage of the query movie's DBRs matched (consecutively)
- total_matching_dbrs: How many DBRs matched
- total_query_dbrs: Total DBRs in the query movie
- dbr_ranges: Which DBR ranges matched

Please interpret these results for the user:
IMPORTANT: You MUST mention ALL movies listed in the Tool Result Summary above. Do not skip any movie.
- For each movie, mention the match percentage and total matching DBRs.
- Explain which DBR ranges matched (dbr_ranges field).
- Explain that the matching DBRs must be consecutive for similarity.
- Explicitly state that Negative DBR means "Days Before Release" and Positive DBR means "Days After Release".
- DO NOT mention Total Revenue.
- DO NOT fabricate or suggest movies that are not in the Tool Result Summary.
- Be concise but comprehensive - mention every single movie in the results.
"""
                        else:
                            final_prompt = f"""
User Query: {user_query}
Tool Result Summary: {json.dumps(llm_context_data, indent=2)}

⚠️ CRITICAL: Do NOT make up or hallucinate any movie names. ONLY use the movies listed in the Tool Result Summary above.
If the Tool Result Summary is empty [], that means NO similar movies were found. In that case, clearly state "No similar movies were found" and DO NOT list any movies.

Please interpret these results for the user:
IMPORTANT: You MUST mention ALL movies listed in the Tool Result Summary above. Do not skip any movie.
- If movies are found, list ALL the movie names from the Tool Result Summary.
- For each movie, mention the total number of matching DBRs and the overall DBR range.
- Explain that because the DBRs are similar in these ranges, the trajectory is expected to be similar.
- Explicitly state that Negative DBR means "Days Before Release" and Positive DBR means "Days After Release".
- DO NOT mention Total Revenue.
- DO NOT fabricate or suggest movies that are not in the Tool Result Summary.
- Be concise but comprehensive - mention every single movie in the results.
"""
                        final_response = self._call_ollama("You are a box office analyst.", final_prompt)
                        
                        if final_response.startswith("Error:"):
                            return {"message": "", "error": final_response}
                        
                        # Concatenate Table to Response
                        full_response = f"{final_response}\n\n{table_str}"
                            
                        return {"message": full_response, "error": ""}
                        
                except json.JSONDecodeError:
                    pass # Not valid JSON, treat as normal response
                    
            # If no tool call or JSON error, return original response
            return {"message": response, "error": ""}
            
        except Exception as e:
            return {"message": "", "error": f"Agent Error: {str(e)}"}

    def _call_ollama(self, system: str, user: str) -> str:
        """Call Ollama API"""
        try:
            payload = {
                "model": config.OLLAMA_MODEL,
                "prompt": f"System: {system}\nUser: {user}",
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 10000  # Limit output length
                }
            }
            
            response = requests.post(config.OLLAMA_URL, json=payload, timeout=30)
            if response.status_code == 200:
                resp_text = response.json()['response'].strip()
                return resp_text
            return f"Error: Ollama API failed with status {response.status_code}"
        except Exception as e:
            return f"Error: {str(e)}"
similarity_agent = MovieSimilarityAgent()

# def main():
#     agent = MovieSimilarityAgent()
#
#     print("="*80)
#     print("🤖 AGENTIC MOVIE SIMILARITY (Tool Calling)")
#     print("="*80)
#     print("💡 Example Queries:")
#     print("   1. 'Top 10 similar movies to Twisters'")
#     print("   2. 'Find strict matches for Zootopia 2 (0.5% diff)'")
#     print("   3. 'Find broadly similar movies to The Black Phone (loose match)'")
#     print("   4. 'Compare Twisters and Wish with 2% tolerance'")
#     print("   5. 'How is 3almashi similar to The Black Phone?'")
#     print("="*80)
#
#     while True:
#         try:
#             query = input("\n💬 You: ").strip()
#             if query.lower() in ['exit', 'quit']: break
#             if not query: continue
#
#             print("Thinking...")
#             result = agent.process_query(query)
#
#             if result.get('error', ''):
#                 print(f"\n❌ Error: {result['error']}")
#             else:
#                 print(f"\n🤖 Agent:\n{result['message']}")
#
#         except KeyboardInterrupt:
#             break

# if __name__ == "__main__":
#     main()
