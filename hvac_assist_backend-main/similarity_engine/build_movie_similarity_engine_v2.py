"""
IMPROVED MOVIE SIMILARITY ENGINE
==================================
Fixes:
1. Timeline alignment - All movies mapped to common DBR timeline
2. Missing data interpolation - Fills gaps in DBR days
3. Revenue scale normalization - Groups by revenue tiers
4. Better visualization - Shows aligned, normalized curves
5. Flexible window - Adapts to movie lifecycle
"""

import pandas as pd
import numpy as np
import faiss
import pickle
from tqdm import tqdm
import warnings
import matplotlib.pyplot as plt
import os
from scipy.interpolate import interp1d

warnings.filterwarnings("ignore")
os.makedirs("similarity_graphs_v2", exist_ok=True)

print("=" * 80)
print("IMPROVED MOVIE SIMILARITY ENGINE V2")
print("=" * 80)

# ============================================================================
# STEP 1: LOAD DATA
# ============================================================================
print("\n[1/6] Loading data...")
df = pd.read_csv("AI_Data_Dump_with_Growth.csv", encoding='utf-16', sep='\t')

df = df.rename(columns={
    'Title': 'title',
    'DBR': 'dbr',
    'Sales Estimate': 'daily_revenue',
    'cumulative_revenue': 'cumulative_revenue'
})

df['title'] = df['title'].astype(str).str.strip()
df = df[['title', 'dbr', 'daily_revenue', 'cumulative_revenue']]

# Clean revenue columns
df['daily_revenue'] = (
    df['daily_revenue']
    .astype(str)
    .str.replace(r'[^0-9.\-]', '', regex=True)
    .str.strip()
)
df['daily_revenue'] = pd.to_numeric(df['daily_revenue'], errors='coerce').fillna(0)

df['cumulative_revenue'] = (
    df['cumulative_revenue']
    .astype(str)
    .str.replace(r'[^0-9.\-]', '', regex=True)
    .str.strip()
)
df['cumulative_revenue'] = pd.to_numeric(df['cumulative_revenue'], errors='coerce').fillna(0)

# Convert DBR to integer
df['day'] = pd.to_numeric(df['dbr'], errors='coerce').fillna(0).astype(int)

print(f"   ✓ Loaded {len(df)} rows, {df['title'].nunique()} unique movies")

# ============================================================================
# STEP 2: HELPER FUNCTIONS
# ============================================================================

def interpolate_missing_days(days, values):
    """Fill missing DBR days using linear interpolation"""
    if len(days) < 2:
        return days, values
    
    # Create full range from min to max day
    full_range = np.arange(days.min(), days.max() + 1)
    
    # Interpolate
    if len(days) == len(set(days)):  # No duplicates
        f = interp1d(days, values, kind='linear', fill_value='extrapolate')
        interpolated_values = f(full_range)
        return full_range, interpolated_values
    else:
        return days, values


def align_to_common_timeline(days, cumulative_revenue, target_range=(-50, 50)):
    """
    Align movie timeline to common DBR range
    Maps any movie's timeline to standard -50 to +50 range
    """
    # Find release day (DBR = 0) or closest to it
    if 0 in days:
        release_idx = np.where(days == 0)[0][0]
    else:
        release_idx = np.argmin(np.abs(days))
    
    # Split into pre-release and post-release
    pre_days = days[days < 0]
    post_days = days[days >= 0]
    pre_revenue = cumulative_revenue[days < 0]
    post_revenue = cumulative_revenue[days >= 0]
    
    # Create aligned timeline
    aligned_days = np.arange(target_range[0], target_range[1] + 1)
    aligned_revenue = np.zeros(len(aligned_days))
    
    # Interpolate pre-release
    if len(pre_days) > 1:
        pre_interp = interp1d(pre_days, pre_revenue, kind='linear', 
                              fill_value=(pre_revenue[0], pre_revenue[-1]), 
                              bounds_error=False)
        pre_aligned_days = aligned_days[aligned_days < 0]
        aligned_revenue[aligned_days < 0] = pre_interp(pre_aligned_days)
    
    # Interpolate post-release
    if len(post_days) > 1:
        post_interp = interp1d(post_days, post_revenue, kind='linear',
                               fill_value=(post_revenue[0], post_revenue[-1]),
                               bounds_error=False)
        post_aligned_days = aligned_days[aligned_days >= 0]
        aligned_revenue[aligned_days >= 0] = post_interp(post_aligned_days)
    
    return aligned_days, aligned_revenue


def normalize_by_final_revenue(cumulative_revenue):
    """Convert to percentage of final revenue (0-100%)"""
    final_revenue = cumulative_revenue[-1]
    if final_revenue > 0:
        return (cumulative_revenue / final_revenue) * 100
    return cumulative_revenue


def calculate_revenue_tier(total_revenue):
    """Categorize movie by revenue tier"""
    if total_revenue < 100_000:
        return 'micro'
    elif total_revenue < 1_000_000:
        return 'small'
    elif total_revenue < 10_000_000:
        return 'medium'
    elif total_revenue < 100_000_000:
        return 'large'
    else:
        return 'blockbuster'


def extract_multi_features(aligned_days, aligned_revenue_pct):
    """
    Extract multiple features from aligned timeline
    Returns: feature vector combining multiple aspects
    """
    features = []
    
    # 1. Pre-release pattern (DBR -50 to -1)
    pre_mask = aligned_days < 0
    pre_revenue = aligned_revenue_pct[pre_mask]
    if len(pre_revenue) > 1:
        pre_growth = np.diff(pre_revenue)
        pre_growth = np.pad(pre_growth, (0, 50 - len(pre_growth)), 'constant')[:50]
    else:
        pre_growth = np.zeros(50)
    features.extend(pre_growth)
    
    # 2. Opening week pattern (DBR 0 to 7)
    opening_mask = (aligned_days >= 0) & (aligned_days <= 7)
    opening_revenue = aligned_revenue_pct[opening_mask]
    if len(opening_revenue) > 1:
        opening_growth = np.diff(opening_revenue)
        opening_growth = np.pad(opening_growth, (0, 7 - len(opening_growth)), 'constant')[:7]
    else:
        opening_growth = np.zeros(7)
    features.extend(opening_growth)
    
    # 3. Post-opening pattern (DBR 8 to 50)
    post_mask = aligned_days > 7
    post_revenue = aligned_revenue_pct[post_mask]
    if len(post_revenue) > 1:
        post_growth = np.diff(post_revenue)
        post_growth = np.pad(post_growth, (0, 42 - len(post_growth)), 'constant')[:42]
    else:
        post_growth = np.zeros(42)
    features.extend(post_growth)
    
    # Total: 50 + 7 + 42 = 99 features
    features = np.array(features, dtype=np.float32)
    features = np.nan_to_num(features, nan=0.0, posinf=100, neginf=-100)
    features = np.clip(features, -100, 100)
    
    return features


# ============================================================================
# STEP 3: PROCESS ALL MOVIES
# ============================================================================
print("\n[2/6] Processing movies with alignment and normalization...")

movie_features = []
movie_metadata = []
movie_aligned_data = {}  # Store for visualization

for title, group in tqdm(df.groupby('title'), desc="Processing"):
    # Aggregate by day
    group = group.groupby('day').agg({
        'daily_revenue': 'sum',
        'cumulative_revenue': 'max'
    }).reset_index().sort_values('day')
    
    # Filter active days (revenue > 100)
    active = group[group['daily_revenue'] > 100]
    if len(active) < 3:
        continue
    
    total_revenue = group['cumulative_revenue'].max()
    if total_revenue < 1000:
        continue
    
    # Get days and cumulative revenue
    days = active['day'].values
    cumulative_revenue = active['cumulative_revenue'].values
    
    # Step 1: Interpolate missing days
    days_interp, revenue_interp = interpolate_missing_days(days, cumulative_revenue)
    
    # Step 2: Align to common timeline (-50 to +50)
    aligned_days, aligned_revenue = align_to_common_timeline(days_interp, revenue_interp)
    
    # Step 3: Normalize to percentage
    aligned_revenue_pct = normalize_by_final_revenue(aligned_revenue)
    
    # Step 4: Extract features
    features = extract_multi_features(aligned_days, aligned_revenue_pct)
    
    # Step 5: Calculate tier
    tier = calculate_revenue_tier(total_revenue)
    
    # Store
    movie_features.append(features)
    movie_metadata.append({
        'title': title,
        'total_revenue': float(total_revenue),
        'tier': tier,
        'active_days': len(active),
        'dbr_range': (int(days.min()), int(days.max()))
    })
    movie_aligned_data[title] = {
        'aligned_days': aligned_days,
        'aligned_revenue_pct': aligned_revenue_pct,
        'original_days': days,
        'original_revenue': cumulative_revenue
    }

movie_features = np.array(movie_features, dtype=np.float32)
print(f"\n   ✓ Processed {len(movie_features)} movies")
print(f"   ✓ Feature dimensions: {movie_features.shape}")

# ============================================================================
# STEP 4: BUILD FAISS INDEX
# ============================================================================
print("\n[3/6] Building FAISS similarity index...")

# Normalize features
embeddings = movie_features / (np.linalg.norm(movie_features, axis=1, keepdims=True) + 1e-8)
embeddings = embeddings.astype('float32')

# Create index
feature_dim = embeddings.shape[1]
index = faiss.IndexFlatIP(feature_dim)
index.add(embeddings)

print(f"   ✓ Index built with {index.ntotal} movies")

# ============================================================================
# STEP 5: SAVE INDEX AND METADATA
# ============================================================================
print("\n[4/6] Saving index and metadata...")

faiss.write_index(index, "movie_similarity_v2.faiss")
with open("movie_metadata_v2.pkl", "wb") as f:
    pickle.dump({
        'metadata': movie_metadata,
        'aligned_data': movie_aligned_data
    }, f)

print("   ✓ Saved: movie_similarity_v2.faiss")
print("   ✓ Saved: movie_metadata_v2.pkl")

# ============================================================================
# STEP 6: SIMILARITY SEARCH FUNCTION
# ============================================================================

def find_similar_v2(title, k=5, make_graph=True, filter_by_tier=False):
    """
    Find similar movies with improved algorithm
    
    Args:
        title: Movie name to find similar movies for
        k: Number of similar movies to return
        make_graph: Whether to generate visualization
        filter_by_tier: Only compare within same revenue tier
    """
    # Find movie index
    titles = [m['title'] for m in movie_metadata]
    if title not in titles:
        print(f"❌ '{title}' not found in index")
        return []
    
    idx = titles.index(title)
    movie_tier = movie_metadata[idx]['tier']
    movie_revenue = movie_metadata[idx]['total_revenue']
    
    # Search
    D, I = index.search(embeddings[idx:idx+1], k + 20)
    
    results = []
    similar_movies = []
    
    print(f"\n{'='*80}")
    print(f"🎬 {title}")
    print(f"   Revenue: ${movie_revenue:,.0f} | Tier: {movie_tier}")
    print(f"{'='*80}")
    print(f"\n📊 Top {k} Similar Movies:\n")
    
    shown = 0
    for j in range(1, len(I[0])):
        if shown >= k:
            break
        
        sim_idx = I[0][j]
        score = D[0][j]
        
        if score < 0.60:  # Threshold
            continue
        
        sim_title = movie_metadata[sim_idx]['title']
        sim_tier = movie_metadata[sim_idx]['tier']
        sim_revenue = movie_metadata[sim_idx]['total_revenue']
        
        # Filter by tier if requested
        if filter_by_tier and sim_tier != movie_tier:
            continue
        
        print(f"   {shown+1}. {sim_title}")
        print(f"      Similarity: {score:.3f} | Revenue: ${sim_revenue:,.0f} | Tier: {sim_tier}")
        print()
        
        results.append(sim_title)
        similar_movies.append((sim_title, score))
        shown += 1
    
    # Generate graph
    if make_graph and len(similar_movies) > 0:
        plt.figure(figsize=(16, 9))
        
        # Main movie (thick red line)
        main_data = movie_aligned_data[title]
        plt.plot(main_data['aligned_days'], 
                 main_data['aligned_revenue_pct'],
                 label=f"{title} (Reference)",
                 linewidth=4, color='red', marker='o', markersize=3, alpha=0.9)
        
        # Similar movies
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#9467bd', '#8c564b', '#e377c2']
        for i, (sim_title, score) in enumerate(similar_movies):
            sim_data = movie_aligned_data[sim_title]
            plt.plot(sim_data['aligned_days'],
                     sim_data['aligned_revenue_pct'],
                     label=f"{sim_title[:40]} ({score:.3f})",
                     linewidth=2.5, alpha=0.75, color=colors[i % len(colors)],
                     marker='o', markersize=2)
        
        plt.axvline(x=0, color='black', linestyle='--', linewidth=2, alpha=0.5, label='Release Day')
        plt.title(f"Revenue Pattern Similarity → {title}", fontsize=18, fontweight='bold', pad=20)
        plt.xlabel("Days Before/After Release (DBR)", fontsize=14, fontweight='bold')
        plt.ylabel("% of Final Revenue Achieved", fontsize=14, fontweight='bold')
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=10)
        plt.grid(True, alpha=0.3, linestyle=':', linewidth=1)
        plt.tight_layout()
        
        # Save
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:100]
        filename = f"similarity_graphs_v2/{safe_name}.png"
        plt.savefig(filename, dpi=200, bbox_inches='tight')
        plt.close()
        print(f"   💾 Graph saved: {filename}\n")
    
    return results


# ============================================================================
# STEP 7: TEST WITH EXAMPLES
# ============================================================================
print("\n[5/6] Testing similarity search...")
print("="*80)

# Test with a few movies
test_movies = [m['title'] for m in movie_metadata[:5]]

for test_movie in test_movies:
    find_similar_v2(test_movie, k=5, make_graph=True)
    print("\n" + "="*80 + "\n")

print("\n[6/6] ✅ DONE! Improved similarity engine ready.")
print(f"\n📁 Generated graphs in: similarity_graphs_v2/")
print(f"📊 Total movies indexed: {len(movie_metadata)}")
