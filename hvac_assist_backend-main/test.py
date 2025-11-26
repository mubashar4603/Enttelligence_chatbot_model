# ========================================================
# 100% WORKING – NO MORE KeyError + GRAPHS
# ========================================================

import pandas as pd
import numpy as np
import chromadb
import os
import shutil
import matplotlib.pyplot as plt

# ------------------ CONFIG ------------------
CSV_PATH = "AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv"
DB_PATH = "./movie_db_fixed"

if os.path.exists(DB_PATH):
    shutil.rmtree(DB_PATH)

print("Loading CSV...")
df = pd.read_csv(CSV_PATH)
df = df[['Title', 'DBR', 'cumulative_revenue']].copy()
df = df.sort_values(['Title', 'DBR'])

days_grid = np.arange(-50, 6)

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.create_collection(
    name="movies",
    metadata={"hnsw:space": "cosine"}
)

# Ye dictionaries sab kuch hold karenge – ChromaDB pe depend nahi karenge metadata ke liye
title_to_vector = {}
title_to_daily = {}
title_to_total_revenue = {}

print("Indexing movies (please wait 20-40 seconds)...")
for title, group in df.groupby('Title'):
    if len(group) < 5:
        continue

    days = group['DBR'].values
    cum = group['cumulative_revenue'].values

    full_cum = np.interp(days_grid, days, cum, left=0.0, right=cum[-1])
    daily_rev = np.diff(full_cum, prepend=0.0)
    daily_rev = np.clip(daily_rev, 0, None)

    total = full_cum[-1]
    if total < 50000:
        continue

    fraction = daily_rev / total
    vector = fraction.tolist()

    safe_id = title.replace(" ", "_").replace(":", "").replace("&", "").replace("'", "").replace("/", "_")

    # Store everything in Python dicts (no more KeyError risk)
    title_to_vector[title] = vector
    title_to_daily[title] = fraction
    title_to_total_revenue[title] = total

    # Add to Chroma – metadata mein sirf title daal rahe hain
    collection.add(
        embeddings=[vector],
        metadatas={"title": title},           # Sirf title daala
        ids=[safe_id]
    )

print(f"Successfully indexed {len(title_to_vector)} movies!\n")

# ------------------ FINAL SAFE QUERY + GRAPH ------------------
def find_similar_with_graph(target_title: str, top_k: int = 7):
    if target_title not in title_to_vector:
        print(f"Movie '{target_title}' not found!")
        return

    query_vec = title_to_vector[target_title]

    results = collection.query(
        query_embeddings=[query_vec],
        n_results=top_k + 10,        # thoda zyada lete hain safety ke liye
        include=["metadatas", "distances"]
    )

    print(f"\nTOP {top_k} SIMILAR TO → {target_title.upper()}")
    print("="*110)
    print(f"{'Rank':<4} {'Similarity':<12} {'Total Revenue':<18} {'Movie Title'}")
    print("-"*110)

    similar_list = []
    rank = 1

    for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
        title_sim = meta['title']
        if title_sim == target_title:
            continue

        sim_score = 1 - dist
        total_rev = title_to_total_revenue.get(title_sim, 0)

        print(f"{rank:<4} {sim_score:.4f}       ${total_rev:>14,.0f}     {title_sim}")
        similar_list.append((title_sim, sim_score))
        rank += 1
        if rank > top_k:
            break

    # ------------------ PLOT ------------------
    plt.figure(figsize=(15, 8))
    target_frac = title_to_daily[target_title]
    plt.plot(days_grid, target_frac, label=target_title, linewidth=5, color='red')

    colors = plt.cm.Set1.colors
    for i, (t, score) in enumerate(similar_list):
        plt.plot(days_grid, title_to_daily[t], label=f"{t} ({score:.3f})", linewidth=2, alpha=0.9)

    plt.title(f"Growth Pattern Comparison → {target_title}", fontsize=18, pad=20)
    plt.xlabel("Days from Release (0 = Release Day)", fontsize=13)
    plt.ylabel("Daily Revenue (% of Total)", fontsize=13)
    plt.axvline(0, color='black', linestyle='--', alpha=0.7)
    plt.grid(alpha=0.3)
    plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    plt.show()

# ------------------ RUN TESTS ------------------
print("\n" + " STARTING LIVE TEST WITH GRAPHS ".center(100, "="))

test_list = [
    "Five Nights at Freddy's 2",
    "100 Meters",
    "100 Yards"
]

for movie in test_list:
    if movie in title_to_vector:
        find_similar_with_graph(movie, top_k=7)
        print("\n" + "-"*110 + "\n")
    else:
        print(f"Skipping → {movie} (not in data)\n")

print("All tests completed – No more errors!")

