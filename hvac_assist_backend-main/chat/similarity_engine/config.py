# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
DATA_PATH = os.path.join(BASE_DIR, "AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv")

OLLAMA_MODEL = "llama3:8b"
OLLAMA_BASE_URL = "http://localhost:11434"

N_POINTS = 101
EMBED_DIMS = 20
RANDOM_STATE = 42

os.makedirs(CACHE_DIR, exist_ok=True)