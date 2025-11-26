# import pandas as pd
# import numpy as np
# import faiss
# import pickle
# from tqdm import tqdm
# import warnings
# import os
# import json
# from langchain_community.llms import Ollama
# from langchain.agents import Tool, AgentExecutor, create_react_agent
# from langchain.prompts import PromptTemplate
# from langchain.callbacks.manager import CallbackManagerForToolRun
# from typing import Optional
#
# warnings.filterwarnings("ignore")
# os.makedirs("similarity_graphs", exist_ok=True)
#
# # ==================== CACHE FILES ====================
# INDEX_FILE = "movie_growth_faiss_index.faiss"
# DATA_FILE = "movie_data.pkl"
# EMBEDDINGS_FILE = "movie_embeddings.npy"
#
# # ==================== LOAD YA BUILD INDEX ====================
# if (os.path.exists(INDEX_FILE) and
#         os.path.exists(DATA_FILE) and
#         os.path.exists(EMBEDDINGS_FILE)):
#
#     print("✓ Cached files found → Loading everything (super fast)!")
#     index = faiss.read_index(INDEX_FILE)
#     embeddings = np.load(EMBEDDINGS_FILE)
#     with open(DATA_FILE, "rb") as f:
#         data = pickle.load(f)
#     valid_titles = data['titles']
#     metadata = data['metadata']
#     print(f"✓ LOADED! {len(valid_titles)} movies ready for instant search.\n")
#
# else:
#     print("⚠ Cached files not found → Building from scratch...\n")
#
#     df = pd.read_csv("AI_Data_Dump_with_Growth.csv", encoding='utf-16', sep='\t')
#     df = df.rename(columns={
#         'Title': 'title',
#         'DBR': 'dbr',
#         'Sales Estimate': 'daily_revenue',
#         'cumulative_revenue': 'cumulative_revenue'
#     })
#
#     df['title'] = df['title'].astype(str).str.strip()
#     df = df[['title', 'dbr', 'daily_revenue', 'cumulative_revenue']]
#
#     # Clean daily_revenue
#     df.loc[df['daily_revenue'].astype(str).str.contains(r'[eE]', na=False, regex=True), 'daily_revenue'] = 0
#     df['daily_revenue'] = df['daily_revenue'].astype(str).str.replace(r'[^0-9.\-]', '', regex=True).str.strip()
#     df['daily_revenue'] = pd.to_numeric(df['daily_revenue'], errors='coerce').fillna(0)
#
#     # Clean cumulative_revenue
#     df.loc[df['cumulative_revenue'].astype(str).str.contains(r'[eE]', na=False, regex=True), 'cumulative_revenue'] = 0
#     df['cumulative_revenue'] = df['cumulative_revenue'].astype(str).str.replace(r'[^0-9.\-]', '', regex=True).str.strip()
#     df['cumulative_revenue'] = pd.to_numeric(df['cumulative_revenue'], errors='coerce').fillna(0)
#
#     df['day'] = pd.to_numeric(df['dbr'], errors='coerce').fillna(0).astype(int)
#
#     print("Building growth curves for ALL movies...")
#     curves = []
#     valid_titles = []
#     metadata = []
#
#     for title, group in tqdm(df.groupby('title'), desc="Processing movies"):
#         group = group.groupby('day').agg({
#             'daily_revenue': 'sum',
#             'cumulative_revenue': 'max'
#         }).reset_index().sort_values('day')
#
#         active = group[group['daily_revenue'] > 100]
#         if len(active) < 3:
#             continue
#
#         daily = active['daily_revenue'].values
#         growth = np.diff(daily) / daily[:-1] * 100.0
#         growth = np.nan_to_num(growth, nan=0.0)
#         growth = np.clip(growth, -99, 999)
#
#         target = 60
#         if len(growth) > target:
#             growth = growth[:target]
#         else:
#             growth = np.pad(growth, (0, target - len(growth)), 'constant', constant_values=0)
#
#         total_rev = group['cumulative_revenue'].max()
#         if total_rev < 1000:
#             continue
#
#         curves.append(growth.astype(np.float32))
#         valid_titles.append(title)
#         metadata.append({
#             'title': title,
#             'total_revenue': float(total_rev),
#             'active_days': len(active)
#         })
#
#     curves = np.array(curves)
#     embeddings = curves / (np.linalg.norm(curves, axis=1, keepdims=True) + 1e-8)
#     embeddings = embeddings.astype('float32')
#
#     index = faiss.IndexFlatIP(60)
#     index.add(embeddings)
#
#     # SAVE
#     faiss.write_index(index, INDEX_FILE)
#     np.save(EMBEDDINGS_FILE, embeddings)
#     with open(DATA_FILE, "wb") as f:
#         pickle.dump({'titles': valid_titles, 'metadata': metadata}, f)
#
#     print(f"✓ DONE & CACHED! {len(valid_titles)} movies indexed.\n")
#
#
# # ==================== SIMILARITY SEARCH TOOL ====================
# def search_similar_movies(movie_title: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
#     """
#     Search for movies with similar box office performance trends.
#
#     Args:
#         movie_title: The exact or partial name of the movie to find similar movies for
#
#     Returns:
#         JSON string with similar movies and confidence scores, or error message
#     """
#     try:
#         movie_title = str(movie_title).strip()
#
#         if not movie_title:
#             return json.dumps({
#                 "status": "error",
#                 "message": "Movie title cannot be empty"
#             })
#
#         matched_title = None
#
#         # Exact match (case-insensitive)
#         for title in valid_titles:
#             if title.lower() == movie_title.lower():
#                 matched_title = title
#                 break
#
#         # Partial match
#         if not matched_title:
#             for title in valid_titles:
#                 if movie_title.lower() in title.lower():
#                     matched_title = title
#                     break
#
#         if not matched_title:
#             return json.dumps({
#                 "status": "not_found",
#                 "message": f"Movie '{movie_title}' not found in database"
#             })
#
#         # Perform similarity search
#         i = valid_titles.index(matched_title)
#         query_vec = embeddings[i:i+1]
#         D, I = index.search(query_vec, 25)
#
#         results = []
#         shown = 0
#         min_score = 0.80
#         k = 5
#
#         for j in range(1, len(D[0])):
#             score = D[0][j]
#             if score < min_score:
#                 continue
#
#             sim_idx = I[0][j]
#             sim_title = valid_titles[sim_idx]
#             results.append({
#                 'title': sim_title,
#                 'confidence': round(float(score), 3)
#             })
#             shown += 1
#
#             if shown >= k:
#                 break
#
#         if not results:
#             return json.dumps({
#                 "status": "no_matches",
#                 "query_movie": matched_title,
#                 "message": f"No similar movies found for '{matched_title}' with confidence above {min_score}"
#             })
#
#         return json.dumps({
#             "status": "success",
#             "query_movie": matched_title,
#             "similar_movies": results
#         })
#
#     except Exception as e:
#         return json.dumps({
#             "status": "error",
#             "message": f"Search error: {str(e)}"
#         })
#
#
# # ==================== HELPER FUNCTION ====================
# def format_movie_results(tool_output: str) -> str:
#     """
#     Format JSON tool output into human-readable response
#
#     Args:
#         tool_output: JSON string from tool
#
#     Returns:
#         Formatted string with movie results
#     """
#     try:
#         data = json.loads(tool_output)
#
#         if data.get('status') == 'success':
#             result = f"\n🎬 Movies similar to '{data['query_movie']}':\n\n"
#
#             for i, movie in enumerate(data['similar_movies'], 1):
#                 conf = movie['confidence']
#                 pct = int(conf * 100)
#                 result += f"{i}. {movie['title']}\n"
#                 result += f"   Similarity: {pct}% (confidence: {conf})\n"
#                 result += f"   → Similar box office revenue growth patterns\n\n"
#
#             result += "💡 These movies matched based on their revenue growth curves over time."
#             return result
#
#         elif data.get('status') == 'not_found':
#             return f"❌ Movie '{data['message'].split(\"'\")[1]}' was not found in our database.\n\n💡 This could mean:\n   • The movie name might be misspelled\n   • The movie might not be in our dataset\n   • Try checking the exact title"
#
#         elif data.get('status') == 'no_matches':
#             movie_name = data.get('query_movie', 'this movie')
#             return f"⚠️ Found '{movie_name}' in database, but no similar movies were found with high confidence (>80% similarity)."
#
#         elif data.get('status') == 'error':
#             return f"❌ {data['message']}"
#
#         # Fallback
#         return tool_output
#
#     except (json.JSONDecodeError, KeyError, TypeError) as e:
#         return f"⚠️ Could not parse results: {tool_output}"
#
#
# # ==================== OLLAMA LLM SETUP ====================
# print("🔧 Initializing OLLAMA with Llama 3 8B...")
#
# llm = Ollama(
#     model="llama3:8b",
#     temperature=0.0,  # More deterministic - less creativity
#     num_predict=250   # Shorter responses
# )
#
# # ==================== TOOL DEFINITION ====================
# similarity_tool = Tool(
#     name="movie_similarity_search",
#     func=search_similar_movies,
#     description="""Use this tool to find movies with similar box office performance trends.
#
#     Input: Movie title (string) - can be exact or partial name
#     Output: JSON with status and similar movies list
#
#     Extract the movie name from user's question and pass ONLY the movie name to this tool.
#     """
# )
#
# # ==================== REACT PROMPT TEMPLATE ====================
# react_template = """You are a movie analyst assistant with access to a similarity search tool.
#
# TOOLS:
# ------
# You have access to the following tools:
#
# {tools}
#
# Tool Names: {tool_names}
#
# INSTRUCTIONS:
# -------------
# Answer the user's question using this format:
#
# Question: the input question you must answer
# Thought: think about what to do
# Action: the action to take, should be one of [{tool_names}]
# Action Input: the input to the action (ONLY the movie name)
# Observation: the result of the action
# Thought: I now know the final answer
# Final Answer: the final answer to the original input question
#
# CRITICAL RULES:
# 1. Extract movie name from the question
# 2. Call movie_similarity_search ONLY ONCE with the movie name
# 3. After getting Observation, IMMEDIATELY write "Thought: I now know the final answer" followed by "Final Answer:"
# 4. NEVER call the tool twice - use the first Observation result
# 5. If Observation shows "not_found", accept it and inform the user in Final Answer
# 6. If Observation shows "success", present the similar movies in Final Answer
# 7. DO NOT try alternative spellings or variations - call tool only once
#
# Begin!
#
# Question: {input}
# Thought: {agent_scratchpad}"""
#
# prompt = PromptTemplate.from_template(react_template)
#
# # ==================== CREATE REACT AGENT ====================
# agent = create_react_agent(
#     llm=llm,
#     tools=[similarity_tool],
#     prompt=prompt
# )
#
# agent_executor = AgentExecutor(
#     agent=agent,
#     tools=[similarity_tool],
#     verbose=True,
#     handle_parsing_errors=True,
#     max_iterations=2,  # Reduced to 2 - one tool call only
#     early_stopping_method="force",
#     return_intermediate_steps=True
# )
#
#
# # ==================== MAIN INTERFACE ====================
# def ask(query: str):
#     """
#     Natural language interface for movie similarity search
#
#     Args:
#         query: User's natural language question
#
#     Returns:
#         Formatted response string
#     """
#     print(f"\n{'='*70}")
#     print(f"💬 USER: {query}")
#     print('='*70 + "\n")
#
#     try:
#         # Invoke agent
#         response = agent_executor.invoke({"input": query})
#
#         # Extract answer from response
#         answer = None
#
#         # Try to get output from response
#         if isinstance(response, dict):
#             if 'output' in response:
#                 answer = response['output']
#
#             # If output is empty or indicates failure, parse intermediate steps
#             if (not answer or
#                     'agent stopped' in answer.lower() or
#                     'iteration limit' in answer.lower() or
#                     len(answer.strip()) < 10):
#
#                 if 'intermediate_steps' in response and response['intermediate_steps']:
#                     # Get last tool call result
#                     for step in reversed(response['intermediate_steps']):
#                         if len(step) >= 2:
#                             tool_output = step[1]
#                             if tool_output:
#                                 answer = format_movie_results(tool_output)
#                                 break
#
#         # Final fallback
#         if not answer:
#             answer = "Sorry, I couldn't generate a response. Please try again."
#
#         # Display result
#         print(f"🤖 ASSISTANT:\n{answer}")
#         print('\n' + '='*70)
#
#         return answer
#
#     except KeyboardInterrupt:
#         print("\n⚠️ Interrupted by user")
#         raise
#     except Exception as e:
#         error_msg = f"An error occurred: {str(e)}"
#         print(f"❌ {error_msg}\n")
#         return error_msg
#
#
# # ==================== MAIN LOOP ====================
# if __name__ == "__main__":
#     print("\n" + "="*70)
#     print("🎬 MOVIE SIMILARITY SEARCH WITH OLLAMA - READY!")
#     print("="*70)
#     print(f"\n📊 Database: {len(valid_titles)} movies loaded")
#     print("\n💡 Example queries:")
#     print('   • "Which movies performed like Titanic?"')
#     print('   • "Find similar movies to Avatar"')
#     print('   • "Show me movies like The Creator"')
#     print('   • "What movies have similar performance to 6 Days?"')
#     print('   • "Movies similar to Inception"')
#     print("\n" + "="*70 + "\n")
#
#     while True:
#         try:
#             user_input = input("💬 Your question (or 'quit' to exit): ").strip()
#
#             if user_input.lower() in ['quit', 'exit', 'q']:
#                 print("\n👋 Goodbye!")
#                 break
#
#             if not user_input:
#                 print("⚠️ Please enter a question.\n")
#                 continue
#
#             ask(user_input)
#
#         except KeyboardInterrupt:
#             print("\n\n👋 Goodbye!")
#             break
#         except Exception as e:
#             print(f"\n❌ Unexpected error: {e}")
#             print("Please try again.\n")


import pandas as pd
import numpy as np
import faiss
import pickle
from tqdm import tqdm
import warnings
import os
import json
import requests
from typing import Dict, Any, Optional, List

warnings.filterwarnings("ignore")
os.makedirs("similarity_graphs", exist_ok=True)

# ==================== CONFIGURATION ====================
INDEX_FILE = "movie_growth_faiss_index.faiss"
DATA_FILE = "movie_data.pkl"
EMBEDDINGS_FILE = "movie_embeddings.npy"
OLLAMA_MODEL = "llama3:8b"
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_K = 5
MIN_SIMILARITY_SCORE = 0.90

# ==================== GLOBAL VARIABLES ====================
index = None
embeddings = None
valid_titles = []
metadata = []
df_full = None


# ==================== INITIALIZATION ====================
def initialize_system():
    """Initialize or load movie database"""
    global index, embeddings, valid_titles, metadata, df_full

    try:
        if (os.path.exists(INDEX_FILE) and
                os.path.exists(DATA_FILE) and
                os.path.exists(EMBEDDINGS_FILE)):

            print("✓ Cached files found → Loading everything (super fast)!")
            index = faiss.read_index(INDEX_FILE)
            embeddings = np.load(EMBEDDINGS_FILE)

            with open(DATA_FILE, "rb") as f:
                data = pickle.load(f)

            valid_titles = data['titles']
            metadata = data['metadata']
            print(f"✓ LOADED! {len(valid_titles)} movies ready for instant search.\n")

        else:
            print("⚠ Cached files not found → Building from scratch...\n")
            build_movie_database()

        # Load full dataset for metadata
        df_full = pd.read_csv("/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/similarity_engine/AI_Data_Dump_with_Growth.csv", encoding='utf-16', sep='\t')
        df_full = df_full.rename(columns={
            'Title': 'title',
            'DBR': 'dbr',
            'Sales Estimate': 'daily_revenue',
            'cumulative_revenue': 'cumulative_revenue'
        })
        df_full['title'] = df_full['title'].astype(str).str.strip()

        return True

    except FileNotFoundError as e:
        print(f"❌ Error: CSV file not found - {e}")
        return False
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        return False


def build_movie_database():
    """Build movie database from CSV"""
    global index, embeddings, valid_titles, metadata

    try:
        df = pd.read_csv("/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/similarity_engine/AI_Data_Dump_with_Growth.csv", encoding='utf-16', sep='\t')
        df = df.rename(columns={
            'Title': 'title',
            'DBR': 'dbr',
            'Sales Estimate': 'daily_revenue',
            'cumulative_revenue': 'cumulative_revenue'
        })

        df['title'] = df['title'].astype(str).str.strip()
        df = df[['title', 'dbr', 'daily_revenue', 'cumulative_revenue']]

        # Clean daily_revenue
        df.loc[df['daily_revenue'].astype(str).str.contains(r'[eE]', na=False, regex=True), 'daily_revenue'] = 0
        df['daily_revenue'] = df['daily_revenue'].astype(str).str.replace(r'[^0-9.\-]', '', regex=True).str.strip()
        df['daily_revenue'] = pd.to_numeric(df['daily_revenue'], errors='coerce').fillna(0)

        # Clean cumulative_revenue
        df.loc[df['cumulative_revenue'].astype(str).str.contains(r'[eE]', na=False, regex=True), 'cumulative_revenue'] = 0
        df['cumulative_revenue'] = df['cumulative_revenue'].astype(str).str.replace(r'[^0-9.\-]', '', regex=True).str.strip()
        df['cumulative_revenue'] = pd.to_numeric(df['cumulative_revenue'], errors='coerce').fillna(0)

        df['day'] = pd.to_numeric(df['dbr'], errors='coerce').fillna(0).astype(int)

        print("Building growth curves for ALL movies...")
        curves = []
        valid_titles = []
        metadata = []

        for title, group in tqdm(df.groupby('title'), desc="Processing movies"):
            group = group.groupby('day').agg({
                'daily_revenue': 'sum',
                'cumulative_revenue': 'max'
            }).reset_index().sort_values('day')

            active = group[group['daily_revenue'] > 100]
            if len(active) < 3:
                continue

            daily = active['daily_revenue'].values
            growth = np.diff(daily) / (daily[:-1] + 1e-8) * 100.0
            growth = np.nan_to_num(growth, nan=0.0)
            growth = np.clip(growth, -99, 999)

            target = 60
            if len(growth) > target:
                growth = growth[:target]
            else:
                growth = np.pad(growth, (0, target - len(growth)), 'constant', constant_values=0)

            total_rev = group['cumulative_revenue'].max()
            if total_rev < 1000:
                continue

            curves.append(growth.astype(np.float32))
            valid_titles.append(title)
            metadata.append({
                'title': title,
                'total_revenue': float(total_rev),
                'active_days': len(active)
            })

        curves = np.array(curves)
        embeddings = curves / (np.linalg.norm(curves, axis=1, keepdims=True) + 1e-8)
        embeddings = embeddings.astype('float32')

        index = faiss.IndexFlatIP(60)
        index.add(embeddings)

        # Save cache
        faiss.write_index(index, INDEX_FILE)
        np.save(EMBEDDINGS_FILE, embeddings)
        with open(DATA_FILE, "wb") as f:
            pickle.dump({'titles': valid_titles, 'metadata': metadata}, f)

        print(f"✓ DONE & CACHED! {len(valid_titles)} movies indexed.\n")

    except Exception as e:
        raise Exception(f"Database build failed: {e}")


# ==================== TOOL: SEARCH SIMILAR MOVIES ====================
def search_similar_movies(movie_title: str, k: int = DEFAULT_K) -> Dict[str, Any]:
    """
    Tool function to search for similar movies based on box office performance.

    Args:
        movie_title: Name of the movie to find similar movies for
        k: Number of similar movies to return (default: 5)

    Returns:
        Dictionary with search results and analysis data
    """
    try:
        # Validate inputs
        if not movie_title or not isinstance(movie_title, str):
            return {
                "status": "error",
                "message": "Invalid movie title provided"
            }

        movie_title = movie_title.strip()
        k = max(1, min(int(k), 50))  # Limit between 1-50

        # Find movie in database
        matched_title = find_movie_in_database(movie_title)

        if not matched_title:
            return {
                "status": "not_found",
                "message": f"Movie '{movie_title}' not found in database",
                "suggestion": "Please check the movie name and try again"
            }

        # Get query movie metadata
        query_idx = valid_titles.index(matched_title)
        query_metadata = metadata[query_idx]
        query_growth = embeddings[query_idx] * (np.linalg.norm(embeddings[query_idx]) + 1e-8)

        # Calculate growth statistics
        query_positive_days = int(np.sum(query_growth > 0))
        query_avg_growth = float(np.mean(query_growth[query_growth > 0]) if np.any(query_growth > 0) else 0)

        # Perform similarity search (search k+1 to exclude query movie itself)
        query_vec = embeddings[query_idx:query_idx+1]
        D, I = index.search(query_vec, min(k + 10, len(valid_titles)))

        # Process results
        results = []
        for j in range(1, len(D[0])):  # Skip first result (query movie itself)
            score = float(D[0][j])

            if score < MIN_SIMILARITY_SCORE:
                continue

            sim_idx = int(I[0][j])
            sim_title = valid_titles[sim_idx]
            sim_metadata = metadata[sim_idx]
            sim_growth = embeddings[sim_idx] * (np.linalg.norm(embeddings[sim_idx]) + 1e-8)

            # Calculate detailed analysis
            growth_diff = np.abs(query_growth - sim_growth)
            avg_growth_diff = float(np.mean(growth_diff))
            max_growth_diff = float(np.max(growth_diff))

            sim_positive_days = int(np.sum(sim_growth > 0))
            sim_avg_growth = float(np.mean(sim_growth[sim_growth > 0]) if np.any(sim_growth > 0) else 0)

            results.append({
                'title': sim_title,
                'confidence': round(score, 3),
                'total_revenue': sim_metadata['total_revenue'],
                'active_days': sim_metadata['active_days'],
                'analysis': {
                    'avg_growth_difference': round(avg_growth_diff, 2),
                    'max_growth_difference': round(max_growth_diff, 2),
                    'positive_growth_days': sim_positive_days,
                    'avg_daily_growth': round(sim_avg_growth, 2),
                    'revenue_comparison': 'higher' if sim_metadata['total_revenue'] > query_metadata['total_revenue'] else 'lower'
                }
            })

            if len(results) >= k:
                break

        if not results:
            return {
                "status": "no_matches",
                "query_movie": matched_title,
                "message": f"No similar movies found with confidence above {MIN_SIMILARITY_SCORE}"
            }

        return {
            "status": "success",
            "query_movie": matched_title,
            "query_metadata": {
                "total_revenue": query_metadata['total_revenue'],
                "active_days": query_metadata['active_days'],
                "avg_daily_growth": round(query_avg_growth, 2),
                "positive_growth_days": query_positive_days
            },
            "similar_movies": results,
            "total_found": len(results)
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Search error: {str(e)}"
        }


def find_movie_in_database(movie_title: str) -> Optional[str]:
    """
    Find exact or partial match for movie in database.

    Args:
        movie_title: Movie name to search for

    Returns:
        Matched movie title or None
    """
    movie_title_lower = movie_title.lower().strip()

    # Exact match
    for title in valid_titles:
        if title.lower() == movie_title_lower:
            return title

    # Partial match
    for title in valid_titles:
        if movie_title_lower in title.lower() or title.lower() in movie_title_lower:
            return title

    return None


# ==================== LLM INTEGRATION ====================
def call_ollama_with_tools(user_query: str) -> Dict[str, Any]:
    """
    Call Ollama LLM with tool calling capability.

    Args:
        user_query: User's question

    Returns:
        Dictionary with LLM response or tool call
    """
    try:
        system_prompt = f"""You are a movie box office analysis assistant. You have access to a tool that can search for similar movies based on box office performance.

Available tool:
- search_similar_movies(movie_title: str, k: int) -> searches for k similar movies to the given movie

Your task:
1. Extract the movie name from the user's query
2. Determine how many similar movies they want (default is {DEFAULT_K})
3. Call the tool with extracted parameters
4. Respond in JSON format

Response format for tool call:
{{
    "action": "use_tool",
    "tool": "search_similar_movies",
    "parameters": {{
        "movie_title": "extracted movie name",
        "k": number_of_movies
    }}
}}

If you cannot identify a movie name, respond:
{{
    "action": "clarify",
    "message": "your clarification question"
}}

Database contains {len(valid_titles)} movies.

Examples:
- "Find similar movies to Avatar" -> movie_title="Avatar", k={DEFAULT_K}
- "Show me top 10 movies like Titanic" -> movie_title="Titanic", k=10
- "Which movies performed like Inception?" -> movie_title="Inception", k={DEFAULT_K}
- "Give me 3 similar movies to The Dark Knight" -> movie_title="The Dark Knight", k=3
"""

        prompt = f"""{system_prompt}

User query: {user_query}

Extract the movie name and number of results, then respond in JSON format:"""

        response = requests.post(
            OLLAMA_URL,
            json={
                'model': OLLAMA_MODEL,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': 0.7,
                    'num_predict': 300
                }
            },
            timeout=30
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Ollama returned status {response.status_code}"
            }

        llm_response = response.json()['response'].strip()

        # Extract JSON from response
        llm_response = extract_json_from_text(llm_response)

        try:
            parsed_response = json.loads(llm_response)
            return parsed_response
        except json.JSONDecodeError:
            return {
                "status": "error",
                "message": "Failed to parse LLM response",
                "raw_response": llm_response
            }

    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "message": "Ollama is not running. Please start it with: ollama serve"
        }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Ollama request timed out"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"LLM call failed: {str(e)}"
        }


def extract_json_from_text(text: str) -> str:
    """Extract JSON from text that might contain markdown or other content"""
    # Remove markdown code blocks
    text = text.replace("```json", "").replace("```", "")

    # Find JSON object
    start = text.find('{')
    end = text.rfind('}')

    if start != -1 and end != -1:
        return text[start:end+1]

    return text


def generate_analysis(search_results: Dict[str, Any], user_query: str) -> str:
    """
    Generate detailed analysis of search results using LLM.

    Args:
        search_results: Results from search_similar_movies
        user_query: Original user query

    Returns:
        Detailed analysis text
    """
    try:
        # Format context for analysis
        context = format_results_for_analysis(search_results)

        analysis_prompt = f"""You are a movie box office analyst. Analyze these similar movies and explain WHY they are similar.

{context}

Your task:
1. For each similar movie, explain specifically WHY it matches the query movie
2. Compare their growth patterns, revenue trajectories, and box office performance
3. Mention key similarities like: similar growth rates, comparable active days, matching revenue trends
4. Be specific with numbers and percentages
5. Present in a clear, professional format with proper formatting

Provide a detailed analysis:"""

        response = requests.post(
            OLLAMA_URL,
            json={
                'model': OLLAMA_MODEL,
                'prompt': analysis_prompt,
                'stream': False,
                'options': {
                    'temperature': 0.5,
                    'num_predict': 1000
                }
            },
            timeout=60
        )

        if response.status_code == 200:
            return response.json()['response'].strip()
        else:
            return f"Error generating analysis: Status {response.status_code}"

    except Exception as e:
        return f"Error generating analysis: {str(e)}"


def format_results_for_analysis(search_results: Dict[str, Any]) -> str:
    """Format search results for LLM analysis"""
    query_movie = search_results['query_movie']
    query_meta = search_results['query_metadata']

    context = f"""Query Movie: {query_movie}
Total Revenue: ${query_meta['total_revenue']:,.0f}
Active Days: {query_meta['active_days']}
Average Daily Growth: {query_meta['avg_daily_growth']}%
Positive Growth Days: {query_meta['positive_growth_days']}

Similar Movies Found ({search_results['total_found']}):
"""

    for i, movie in enumerate(search_results['similar_movies'], 1):
        context += f"\n{i}. {movie['title']}\n"
        context += f"   - Similarity Confidence: {movie['confidence']} ({int(movie['confidence']*100)}%)\n"
        context += f"   - Total Revenue: ${movie['total_revenue']:,.0f}\n"
        context += f"   - Active Days: {movie['active_days']}\n"
        context += f"   - Average Daily Growth: {movie['analysis']['avg_daily_growth']}%\n"
        context += f"   - Positive Growth Days: {movie['analysis']['positive_growth_days']}\n"
        context += f"   - Revenue vs Query Movie: {movie['analysis']['revenue_comparison']}\n"
        context += f"   - Growth Pattern Difference: {movie['analysis']['avg_growth_difference']}%\n"

    return context


# ==================== MAIN INTERFACE ====================
def ask(user_query: str) -> Optional[json]:
    """
    Main interface function - processes user query with LLM tool calling.

    Args:
        user_query: User's question

    Returns:
        Analysis text or None if error
    """
    print(f"\n{'='*70}")
    print(f"💬 USER: {user_query}")
    print('='*70 + "\n")
    error = ""
    try:
        # Step 1: LLM extracts movie name and k
        print("🤖 Processing query with AI...\n")
        llm_response = call_ollama_with_tools(user_query)

        if llm_response.get("status") == "error":
            print(f"❌ {llm_response['message']}\n")
            return {"error": llm_response["message"]}

        if llm_response.get("action") == "clarify":
            print(f"🤔 {llm_response['message']}\n")
            return {"error": llm_response["message"]}

        if llm_response.get("action") != "use_tool":
            print(f"❌ Unexpected response from AI\n")
            return {"error": llm_response["message"]}

        # Step 2: Extract parameters
        params = llm_response.get("parameters", {})
        movie_title = params.get("movie_title", "")
        k = params.get("k", DEFAULT_K)

        print(f"🔍 Searching for {k} movies similar to: '{movie_title}'\n")

        # Step 3: Call tool
        search_results = search_similar_movies(movie_title, k)

        if search_results["status"] != "success":
            print(f"❌ {search_results.get('message', 'Search failed')}\n")
            if search_results.get("suggestion"):
                print(f"💡 {search_results['suggestion']}\n")
            return {"error": search_results['suggestion']}

        # Step 4: Generate analysis
        print("🤖 Generating detailed analysis...\n")
        analysis = generate_analysis(search_results, user_query)

        # Step 5: Display results
        print(f"{'='*70}")
        print(f"🎬 ANALYSIS FOR: {search_results['query_movie']}")
        print(f"📊 Found {search_results['total_found']} similar movies")
        print(f"{'='*70}\n")
        print(analysis)
        print('\n' + '='*70)

        return {"message": analysis, "error": error}

    except KeyboardInterrupt:
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}\n")
        return {"error": error_msg}

initialize_system()
print(ask("top  similar movie to 6 Days"))
# ==================== MAIN LOOP ====================
# def main():
#     """Main entry point"""
#     print("\n" + "="*70)
#     print("🎬 MOVIE SIMILARITY SEARCH WITH AI TOOL CALLING")
#     print("="*70)
#
#     # Initialize system
#     if not initialize_system():
#         print("\n❌ System initialization failed. Exiting.")
#         return
#
#     # print(f"\n📊 Database: {len(valid_titles)} movies loaded")
#     # print(f"🤖 AI Model: {OLLAMA_MODEL}")
#     # print("\n💡 Example queries:")
#     # print('   • "Find similar movies to Avatar"')
#     # print('   • "Show me top 10 movies like Titanic"')
#     # print('   • "Which 3 movies performed like Inception?"')
#     # print('   • "Give me similar movies to The Dark Knight"')
#     # print("\n" + "="*70 + "\n")
#
#     while True:
#         try:
#             user_input = input("💬 Your question (or 'quit' to exit): ").strip()
#
#             if user_input.lower() in ['quit', 'exit', 'q']:
#                 print("\n👋 Goodbye!")
#                 break
#
#             if not user_input:
#                 print("⚠️ Please enter a question.\n")
#                 continue
#
#             ask(user_input)
#
#         except KeyboardInterrupt:
#             print("\n\n👋 Goodbye!")
#             break
#         except Exception as e:
#             print(f"\n❌ Unexpected error: {e}\n")


# if __name__ == "__main__":
#     main()