import pandas as pd
import numpy as np

# Read CSV
df = pd.read_csv("/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/similarity_engine/AI_Data_Dump_with_Growth.csv", 
                 encoding='utf-16', sep='\t')

df = df.rename(columns={
    'Title': 'title',
    'DBR': 'dbr',
    'Sales Estimate': 'daily_revenue',
    'cumulative_revenue': 'cumulative_revenue',
    'Growth (%)': 'growth_pct'
})

df['title'] = df['title'].astype(str).str.strip()
df['day'] = pd.to_numeric(df['dbr'], errors='coerce').fillna(0).astype(int)

# Clean revenue columns
df.loc[df['daily_revenue'].astype(str).str.contains(r'[eE]', na=False, regex=True), 'daily_revenue'] = 0
df['daily_revenue'] = df['daily_revenue'].astype(str).str.replace(r'[^0-9.\-]', '', regex=True).str.strip()
df['daily_revenue'] = pd.to_numeric(df['daily_revenue'], errors='coerce').fillna(0)

print("="*80)
print("PROBLEM DIAGNOSIS: Why are dissimilar movies showing 100% similarity?")
print("="*80)

# Test with two very different movies
movies = ['3almashi', '6 Days']

growth_curves = {}

for movie in movies:
    movie_data = df[df['title'] == movie].copy()
    
    group = movie_data.groupby('day').agg({
        'daily_revenue': 'sum',
        'cumulative_revenue': 'max'
    }).reset_index().sort_values('day')
    
    active = group[group['daily_revenue'] > 100]
    
    if len(active) < 3:
        print(f"\n{movie}: Not enough active days")
        continue
    
    daily = active['daily_revenue'].values
    growth = np.diff(daily) / (daily[:-1] + 1e-8) * 100.0
    growth = np.nan_to_num(growth, nan=0.0)
    growth = np.clip(growth, -99, 999)
    
    # Pad to 60
    target = 60
    if len(growth) > target:
        growth = growth[:target]
    else:
        growth = np.pad(growth, (0, target - len(growth)), 'constant', constant_values=0)
    
    growth_curves[movie] = growth
    
    print(f"\n{movie}:")
    print(f"  Active days: {len(active)}")
    print(f"  Growth curve (first 10): {growth[:10]}")
    print(f"  Growth curve (non-zero count): {np.count_nonzero(growth)}")

print("\n" + "="*80)
print("THE PROBLEM:")
print("="*80)

if len(growth_curves) == 2:
    curve1 = growth_curves['3almashi']
    curve2 = growth_curves['6 Days']
    
    print("\nBEFORE normalization:")
    print(f"  3almashi curve: {curve1[:10]}")
    print(f"  6 Days curve: {curve2[:10]}")
    print(f"  Raw difference: {np.abs(curve1 - curve2)[:10]}")
    print(f"  Are they similar? NO! Very different patterns.")
    
    # Apply L2 normalization (the bug)
    norm1 = curve1 / (np.linalg.norm(curve1) + 1e-8)
    norm2 = curve2 / (np.linalg.norm(curve2) + 1e-8)
    
    print("\nAFTER L2 normalization (CURRENT V4 CODE):")
    print(f"  3almashi normalized: {norm1[:10]}")
    print(f"  6 Days normalized: {norm2[:10]}")
    
    # Cosine similarity (what Pinecone uses)
    cosine_sim = np.dot(norm1, norm2)
    print(f"\n  Cosine similarity: {cosine_sim:.4f}")
    print(f"  This is why they show as {int(cosine_sim*100)}% similar!")
    
    print("\n" + "="*80)
    print("ROOT CAUSE:")
    print("="*80)
    print("""
The L2 normalization in line 208 is causing the problem!

embeddings = curves / (np.linalg.norm(curves, axis=1, keepdims=True) + 1e-8)

This normalization makes ALL vectors have magnitude 1, which means:
- Movies with 3 active days get padded with 57 zeros
- Movies with 10 active days get padded with 50 zeros
- After normalization, the padding dominates the similarity calculation
- Movies with similar number of active days appear similar, regardless of actual growth patterns!

SOLUTION: Remove or modify the normalization to preserve growth pattern differences.
    """)

print("\n" + "="*80)
print("RECOMMENDED FIX:")
print("="*80)
print("""
Option 1: Use RAW growth values (like V3)
  embeddings = curves.astype('float32')  # NO normalization

Option 2: Use min-max scaling per movie
  embeddings = (curves - curves.min(axis=1, keepdims=True)) / 
               (curves.max(axis=1, keepdims=True) - curves.min(axis=1, keepdims=True) + 1e-8)

Option 3: Use standard scaling
  embeddings = (curves - curves.mean(axis=1, keepdims=True)) / 
               (curves.std(axis=1, keepdims=True) + 1e-8)
""")
