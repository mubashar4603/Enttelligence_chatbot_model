# llm/ollama_client.py
import requests
from config import OLLAMA_BASE_URL, OLLAMA_MODEL

def query_ollama(prompt: str) -> str:
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/generate",
                             json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                             timeout=60)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except:
        return "Explanation unavailable."