"""
LLM Interface for DBR-Specific Similarity Search
Handles natural language queries and generates detailed analysis using Ollama
"""

import re
import requests
import json
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dbr_specific_search import DBRSpecificSimilarity
from core.data_loader import DataLoader
from core.preprocessor import MoviePreprocessor
from core.vector_builder import VectorBuilder
import pickle
import os
import config

class LLMSearchInterface:
    """
    Interface that behaves like an LLM-powered bot.
    Parses natural language queries and returns formatted results with analysis.
    """
    
    def __init__(self):
        self.finder = None
        self._initialize()
        
    def _initialize(self):
        """Initialize the system"""
        print("🔧 Initializing LLM Search Interface...")
        
        # Check cache
        if os.path.exists(config.CACHE_FILES['movies_db']) and os.path.exists(config.CACHE_FILES['metadata']):
            # print("📦 Loading from cache...")
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
        print("✅ System Ready!\n")

    def parse_query(self, query: str) -> Dict[str, Any]:
        """
        Parse natural language query to extract:
        - Target movie
        - Intent (search vs compare)
        - K (number of results)
        - Comparison targets (if any)
        """
        query_lower = query.lower().strip()
        
        # Default values
        result = {
            "intent": "search",
            "target_movie": None,
            "compare_movies": [],
            "k": config.DEFAULT_K,
            "max_diff": 1.0,  # Default as requested
            "min_dbrs": 3     # Default as requested
        }
        
        # 1. Extract K (e.g., "top 10", "5 similar")
        k_match = re.search(r'top\s+(\d+)', query_lower)
        if k_match:
            result["k"] = int(k_match.group(1))
        else:
            k_match = re.search(r'(\d+)\s+(?:similar|movies)', query_lower)
            if k_match:
                result["k"] = int(k_match.group(1))
                
        # 2. Check for Comparison Intent
        # "compare X and Y", "how is X similar to Y"
        if "compare" in query_lower or "difference between" in query_lower or " vs " in query_lower:
            result["intent"] = "compare"
            
            # Extract movies for comparison
            # Remove "compare", "vs", "and" to isolate names
            clean_query = query_lower.replace("compare", "").replace("difference between", "")
            
            if " with " in clean_query:
                parts = clean_query.split(" with ")
            elif " to " in clean_query:
                parts = clean_query.split(" to ")
            elif " and " in clean_query:
                parts = clean_query.split(" and ")
            elif " vs " in clean_query:
                parts = clean_query.split(" vs ")
            else:
                parts = [clean_query]
                
            # Clean up parts
            parts = [p.strip() for p in parts if p.strip()]
            
            if len(parts) >= 1:
                result["target_movie"] = self._find_best_match(parts[0])
            if len(parts) >= 2:
                # Handle comma-separated list in second part
                others = parts[1].replace(" and ", ",").split(",")
                result["compare_movies"] = [self._find_best_match(m.strip()) for m in others if m.strip()]
                
        else:
            # 3. Search Intent
            # "similar to X", "movies like X"
            
            # Remove common phrases to isolate movie name
            patterns = [
                r'which\s+movies?\s+is\s+similar\s+to\s+',
                r'what\s+movies?\s+are\s+similar\s+to\s+',
                r'find\s+similar\s+movies?\s+to\s+',
                r'show\s+me\s+movies?\s+like\s+',
                r'top\s+\d+\s+similar\s+movies?\s+to\s+',
                r'top\s+\d+\s+movies?\s+like\s+',
                r'similar\s+to\s+',
                r'movies?\s+like\s+',
                r'search\s+for\s+'
            ]
            
            clean_query = query_lower
            for p in patterns:
                clean_query = re.sub(p, '', clean_query)
            
            # Remove trailing punctuation
            clean_query = clean_query.strip('?.!')
            
            result["target_movie"] = self._find_best_match(clean_query)
            
        return result

    def _find_best_match(self, partial_name: str) -> str:
        """Find best matching movie title in database"""
        if not partial_name:
            return None
            
        # 1. Exact match (case insensitive)
        titles = list(self.finder.movies_db.keys())
        for t in titles:
            if t.lower() == partial_name.lower():
                return t
                
        # 2. Contains match
        matches = [t for t in titles if partial_name.lower() in t.lower()]
        if matches:
            # Return shortest match (likely the exact title if it's a substring)
            return min(matches, key=len)
            
        return partial_name  # Return original if no match found (will fail gracefully later)

    def process_query(self, user_query: str) -> str:
        """Process a user query and return the response"""
        parsed = self.parse_query(user_query)
        
        if not parsed["target_movie"]:
            return "❌ Could not identify the movie name. Please try 'similar to [Movie Name]'."
            
        target = parsed["target_movie"]
        
        # Check if movie exists
        if target not in self.finder.movies_db:
            return f"❌ Movie '{target}' not found in database."
            
        output = []
        
        if parsed["intent"] == "compare" and parsed["compare_movies"]:
            # Comparison Mode
            output.append(f"🔍 Comparing '{target}' with {', '.join(parsed['compare_movies'])}...")
            
            # Get all matches
            all_results = self.finder.find_dbr_specific_matches(
                target,
                max_growth_diff=parsed["max_diff"],
                min_consecutive_dbrs=1  # Show all details for comparison
            )
            
            # Filter
            results = [r for r in all_results if r['similar_movie'] in parsed["compare_movies"]]
            
            if not results:
                output.append("❌ No matching DBR ranges found between these movies (within 1% growth difference).")
            else:
                df = self.finder.export_to_dataframe(target, results)
                output.append(self._format_table(df))
                
        else:
            # Search Mode
            k = parsed["k"]
            output.append(f"🔍 Searching for top {k} movies similar to '{target}'...")
            output.append(f"(Criteria: Max Diff {parsed['max_diff']}%, Min {parsed['min_dbrs']} Consecutive DBRs)")
            
            results = self.finder.find_dbr_specific_matches(
                target,
                max_growth_diff=parsed["max_diff"],
                min_consecutive_dbrs=parsed["min_dbrs"]
            )
            
            if not results:
                output.append("❌ No similar movies found matching the criteria.")
            else:
                # Sort by number of matching ranges or total days
                results.sort(key=lambda x: sum(r['dbr_count'] for r in x['matching_ranges']), reverse=True)
                
                # Take top K
                top_results = results[:k]
                
                df = self.finder.export_to_dataframe(target, top_results)
                output.append(f"✅ Found {len(top_results)} similar movies:\n")
                output.append(self._format_table(df))
                
                # Generate LLM Analysis
                if config.ENABLE_LLM_ANALYSIS:
                    output.append("\n" + "="*80)
                    output.append("🤖 AI ANALYSIS")
                    output.append("="*80)
                    analysis = self._generate_analysis(target, top_results)
                    output.append(analysis)
        
        return "\n".join(output)

    def _format_table(self, df: pd.DataFrame) -> str:
        """Format DataFrame as a string table"""
        if df.empty:
            return ""
            
        lines = []
        lines.append(f"{'Target Title':<20} {'Similar Title':<30} {'DBR':<6} {'Target Growth':<15} {'Similar Growth':<15}")
        lines.append("-" * 100)
        
        for similar_movie in df['Similar Title'].unique():
            movie_df = df[df['Similar Title'] == similar_movie].sort_values('DBR')
            for idx, row in movie_df.iterrows():
                lines.append(f"{str(row['Target Title'])[:19]:<20} {str(row['Similar Title'])[:29]:<30} {row['DBR']:<6} {row['Target Growth']:<15.2f} {row['Similar Growth']:<15.2f}")
            lines.append("") # Empty line between movies
            
        return "\n".join(lines)

    def _generate_analysis(self, target_movie: str, results: List[Dict]) -> str:
        """Generate analysis using Ollama"""
        try:
            # Prepare context
            context = f"Target Movie: {target_movie}\n\nSimilar Movies found based on Daily Box Office Growth (DBR):\n"
            
            for res in results:
                movie = res['similar_movie']
                ranges = res['matching_ranges']
                total_days = sum(r['dbr_count'] for r in ranges)
                avg_diff = sum(r['avg_difference'] for r in ranges) / len(ranges)
                
                context += f"- {movie}: Matches on {total_days} days across {len(ranges)} periods. Avg growth difference: {avg_diff:.2f}%\n"
                
            prompt = f"""
            You are a box office analyst. Analyze these similarity results for the movie "{target_movie}".
            
            Data:
            {context}
            
            Task:
            1. Summarize which movies are most similar and why (based on matching days).
            2. Explain what this implies about the movie's performance trajectory.
            3. Keep it concise (max 4-5 sentences).
            """
            
            response = requests.post(
                config.OLLAMA_URL,
                json={
                    'model': config.OLLAMA_MODEL,
                    'prompt': prompt,
                    'stream': False,
                    'options': {'temperature': 0.7}
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['response'].strip()
            else:
                return "⚠️ Analysis unavailable (LLM error)"
                
        except Exception as e:
            return f"⚠️ Analysis unavailable: {str(e)}"

def main():
    """Interactive CLI"""
    interface = LLMSearchInterface()
    
    print("="*80)
    print("🤖 MOVIE SIMILARITY AI AGENT")
    print("="*80)
    print("Examples:")
    print(" - 'Which movie is similar to 3almashi?'")
    print(" - 'Top 10 similar movies to Twisters'")
    print(" - 'Compare Zootopia 2 and The Black Phone'")
    print("="*80 + "\n")
    
    while True:
        try:
            query = input("💬 You: ").strip()
            if query.lower() in ['exit', 'quit', 'q']:
                break
            if not query:
                continue
                
            print("\nThinking...\n")
            response = interface.process_query(query)
            print(response)
            print("\n" + "-"*80 + "\n")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
