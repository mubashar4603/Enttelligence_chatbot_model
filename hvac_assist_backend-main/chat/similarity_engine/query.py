# # main.py
# from pydantic import BaseModel
# from chat..similarity_engine import MovieSimilarityEngine
# from llm.ollama_client import query_ollama
# from utils.plotter import curves_to_base64
# import re
#
# app = FastAPI(title="Movie Performance Similarity API")
# engine = MovieSimilarityEngine()
#
# class QueryRequest(BaseModel):
#     query: str
#
# def explain_why(ref_title: str, sim_title: str):
#     prompt = f"""Compare "{ref_title}" and "{sim_title}" box office patterns (normalized curves).
#     In 1-2 short sentences, explain why they performed similarly in trajectory.
#     Focus only on opening, legs, word-of-mouth. No dollar amounts."""
#     return query_ollama(prompt)
#
# @app.post("/search")
# def search_movies(req: QueryRequest):
#     # Guess movie from natural language
#     guess_prompt = f"From this list of movies, which one best matches: '{req.query}'\nReturn ONLY the exact title."
#     guessed = query_ollama(guess_prompt + "\n".join(engine.titles[:100]))
#
#     title = None
#     for t in engine.titles:
#         if guessed.lower() in t.lower() or t.lower() in guessed.lower():
#             title = t
#             break
#
#     if not title:
#         return {"error": "Movie not found"}
#
#     similar = engine.find_similar(title, top_k=5)
#     results = []
#     for t, sim in similar:
#         why = explain_why(title, t)
#         results.append({"title": t, "similarity": sim, "why": why})
#
#     image = curves_to_base64(title, similar, engine)
#
#     return {
#         "reference": title,
#         "results": results,
#         "plot": f"data:image/png;base64,{image}"
#     }
#
# @app.get("/")
# def home():
#     return {"message": "Movie Similarity API Ready!"}