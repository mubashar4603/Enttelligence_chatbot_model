"""
LLM Agent with Tool Calling for DBR Similarity Search
Uses Ollama (Llama 3) to dynamically select tools and parameters
"""

import json
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

class MovieSimilarityAgent:
    """
    Agent that uses LLM tool calling to interact with the similarity engine.
    """
    
    def __init__(self):
        self.finder = None
        self._initialize_system()
        
    def _initialize_system(self):
        """Initialize the underlying similarity engine"""
        print("🔧 Initializing Similarity Engine...")
        
        # Check cache
        if os.path.exists(config.CACHE_FILES['movies_db']) and os.path.exists(config.CACHE_FILES['metadata']):
            with open(config.CACHE_FILES['movies_db'], 'rb') as f:
                movies_db = pickle.load(f)
            with open(config.CACHE_FILES['metadata'], 'rb') as f:
                metadata = pickle.load(f)
        else:
            print("🔨 Building from scratch...")
            loader = DataLoader()
            df = loader.load()
            preprocessor = MoviePreprocessor(df)
            movies_db = preprocessor.process_all_movies()
            builder = VectorBuilder(movies_db)
            _, metadata = builder.build_embeddings()
        
        self.finder = DBRSpecificSimilarity(movies_db, metadata)
        print("✅ Engine Ready!\n")

    # ==================== TOOLS ====================
    
    def search_similar_movies(self, movie_name: str, k: int = 5, max_growth_diff: float = 1.0, min_consecutive_dbrs: int = 3) -> str:
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
        formatted = []
        for res in top_results:
            ranges = res['matching_ranges']
            total_days = sum(r['dbr_count'] for r in ranges)
            avg_diff = sum(r['avg_difference'] for r in ranges) / len(ranges)
            
            formatted.append({
                "title": res['similar_movie'],
                "total_revenue": res['total_revenue'],
                "matching_days": total_days,
                "avg_growth_diff": round(avg_diff, 2),
                "ranges_count": len(ranges)
            })
            
        return json.dumps({
            "status": "success",
            "query_movie": target,
            "count": len(formatted),
            "results": formatted
        })

    def compare_movies(self, movie1: str, movie2: str, max_growth_diff: float = 1.0) -> str:
        """
        Tool to compare two specific movies.
        """
        target1 = self._find_best_match(movie1)
        target2 = self._find_best_match(movie2)
        
        if not target1: return json.dumps({"error": f"Movie '{movie1}' not found"})
        if not target2: return json.dumps({"error": f"Movie '{movie2}' not found"})
        
        results = self.finder.find_dbr_specific_matches(
            target1,
            max_growth_diff=float(max_growth_diff),
            min_consecutive_dbrs=1 # Show all overlaps
        )
        
        match = next((r for r in results if r['similar_movie'] == target2), None)
        
        if not match:
            return json.dumps({
                "status": "no_overlap",
                "message": f"No overlapping DBRs found between '{target1}' and '{target2}' within {max_growth_diff}% difference."
            })
            
        ranges = match['matching_ranges']
        total_days = sum(r['dbr_count'] for r in ranges)
        
        return json.dumps({
            "status": "success",
            "movie1": target1,
            "movie2": target2,
            "matching_days": total_days,
            "details": ranges
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
        1. Send query + tool definitions to LLM
        2. LLM decides tool call
        3. Execute tool
        4. Send result back to LLM for final answer
        
        Returns:
            Dict with 'message' and 'error' keys
        """
        
        tools_def = [
            {
                "name": "search_similar_movies",
                "description": "Finds movies with similar box office growth patterns. Use this for queries like 'similar to X', 'top 10 like X'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "movie_name": {"type": "string", "description": "Name of the movie to search for"},
                        "k": {"type": "integer", "description": "Number of movies to return (default 5)"},
                        "max_growth_diff": {"type": "number", "description": "Max allowed difference in growth percentage (default 1.0)"},
                        "min_consecutive_dbrs": {"type": "integer", "description": "Min consecutive matching days (default 3)"}
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

DYNAMIC PARAMETERS:
- You have full control over `max_growth_diff` and `min_consecutive_dbrs`.
- If user asks for "strict" or "exact" matches, reduce `max_growth_diff` (e.g., 0.5) and increase `min_consecutive_dbrs` (e.g., 5).
- If user asks for "broad" or "loose" matches, increase `max_growth_diff` (e.g., 2.0 or 3.0) and decrease `min_consecutive_dbrs` (e.g., 2).
- Default parameters: max_growth_diff=1.0, min_consecutive_dbrs=3.
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
                        if tool_name == "search_similar_movies":
                            result = self.search_similar_movies(**params)
                        elif tool_name == "compare_movies":
                            result = self.compare_movies(**params)
                            
                        # 3. Send result back to LLM for final analysis
                        final_prompt = f"""
User Query: {user_query}
Tool Result: {result}

Please interpret these results for the user.
- Mention movies name, mention how many DBRs they have similar and do show other information. Don't miss the movie name.
- Summarize the findings.
- Explain why the movies are similar (based on matching days and growth difference).
- Be concise and professional.
"""
                        final_response = self._call_ollama("You are a box office analyst.", final_prompt)
                        
                        if final_response.startswith("Error:"):
                            return {"message": "", "error": final_response}
                            
                        return {"message": final_response, "error": ""}
                        
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
                    "temperature": 0.1,
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
#             if result['error']:
#                 print(f"\n❌ Error: {result['error']}")
#             else:
#                 print(f"\n🤖 Agent:\n{result['message']}")
#
#         except KeyboardInterrupt:
#             break
#
# if __name__ == "__main__":
#     main()
