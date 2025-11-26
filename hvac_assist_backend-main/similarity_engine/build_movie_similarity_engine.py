import pandas as pd
import numpy as np
import faiss
import pickle
from tqdm import tqdm
import warnings
import matplotlib.pyplot as plt
import os

warnings.filterwarnings("ignore")
os.makedirs("similarity_graphs", exist_ok=True)

# ==================== CACHE FILES ====================
INDEX_FILE = "movie_growth_faiss_index.faiss"
DATA_FILE = "movie_data.pkl"
EMBEDDINGS_FILE = "movie_embeddings.npy"

# Check karo agar saari files already hain to load, warna banaye
if (os.path.exists(INDEX_FILE) and
        os.path.exists(DATA_FILE) and
        os.path.exists(EMBEDDINGS_FILE)):

    print("Cached files found → Loading everything (super fast)!")
    index = faiss.read_index(INDEX_FILE)
    embeddings = np.load(EMBEDDINGS_FILE)
    with open(DATA_FILE, "rb") as f:
        data = pickle.load(f)
        valid_titles = data['titles']
        metadata = data['metadata']
    print(f"LOADED! {len(valid_titles)} movies ready for instant search.\n")

else:
    print("Cached files not found or incomplete → Building from scratch...\n")
    print("Loading your full data...")
    df = pd.read_csv("AI_Data_Dump_with_Growth.csv", encoding='utf-16', sep='\t')

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
        growth = np.diff(daily) / daily[:-1] * 100.0
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
    print("Curves shape:", curves.shape)
    print("Valid titles:", len(valid_titles))

    # Normalize for cosine similarity
    embeddings = curves / (np.linalg.norm(curves, axis=1, keepdims=True) + 1e-8)
    embeddings = embeddings.astype('float32')

    # Build FAISS index
    index = faiss.IndexFlatIP(60)
    index.add(embeddings)

    # SAVE EVERYTHING
    faiss.write_index(index, INDEX_FILE)
    np.save(EMBEDDINGS_FILE, embeddings)
    with open(DATA_FILE, "wb") as f:
        pickle.dump({'titles': valid_titles, 'metadata': metadata}, f)

    print(f"\nDONE & CACHED! {len(valid_titles)} movies indexed and saved successfully.\n")

# =============================================
#            SEARCH FUNCTION
# =============================================

def find(title, k=5, make_graph=True, min_score=0.80):
    if title not in valid_titles:
        print(f"'{title}' → not in index")
        return []

    i = valid_titles.index(title)
    query_vec = embeddings[i:i+1]
    D, I = index.search(query_vec, k + 20)

    print(f"\n{title} → Top Similar Movies (score ≥ {min_score}):")
    result = []
    similar_data = []
    shown = 0

    for j in range(1, len(D[0])):
        score = D[0][j]
        if score < min_score:
            continue
        sim_idx = I[0][j]
        sim_title = valid_titles[sim_idx]
        print(f"   → {sim_title} ({score:.3f})")
        result.append(sim_title)
        similar_data.append((sim_title, score))
        shown += 1
        if shown >= k:
            break

    if shown == 0:
        print("   (No matches above threshold)")

    return result

# print("\n" + "="*80)
# print("TESTING WITH GRAPH GENERATION")
# print("="*80)
#
# for i in valid_titles[:100]:
#     find(i)
#     print("="*80)


# find("Five Nights at Freddy's")
# find("Avatar: Fire and Ash")
# find("Five Nights at Freddy's")


# find("Dead of Winter")
# find("Dead to Rights")
# find("Deadpool & Wolverine")
# find("Deadpool & Wolverine Opening Day Fan Event")
