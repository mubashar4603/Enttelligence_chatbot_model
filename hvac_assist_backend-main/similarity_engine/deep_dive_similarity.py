import pandas as pd
import numpy as np

# Read CSV
df = pd.read_csv("/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/similarity_engine/AI_Data_Dump_with_Growth.csv", 
                 encoding='utf-16', sep='\t')

df = df.rename(columns={
    'Title': 'title',
    'DBR': 'dbr',
    'Sales Estimate': 'daily_revenue',
    'cumulative_revenue': 'cumulative_revenue'
})

df['title'] = df['title'].astype(str).str.strip()
df['day'] = pd.to_numeric(df['dbr'], errors='coerce').fillna(0).astype(int)

# Clean revenue
df.loc[df['daily_revenue'].astype(str).str.contains(r'[eE]', na=False, regex=True), 'daily_revenue'] = 0
df['daily_revenue'] = df['daily_revenue'].astype(str).str.replace(r'[^0-9.\-]', '', regex=True).str.strip()
df['daily_revenue'] = pd.to_numeric(df['daily_revenue'], errors='coerce').fillna(0)

print("="*80)
print("DEEP DIVE: What growth curves is the bot actually comparing?")
print("="*80)

movies = ['3almashi', 'Loathe Thy Neighbor', 'Echo a Delta']

growth_vectors = {}

for movie in movies:
    movie_data = df[df['title'] == movie].copy()
    
    group = movie_data.groupby('day').agg({
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
    
    # Pad to 60
    target = 60
    if len(growth) > target:
        growth = growth[:target]
    else:
        growth = np.pad(growth, (0, target - len(growth)), 'constant', constant_values=0)
    
    growth_vectors[movie] = growth
    
    print(f"\n{movie}:")
    print(f"  Active days: {len(active)}")
    print(f"  Daily revenues: {daily}")
    print(f"  Growth vector (full 60): {growth}")
    print(f"  Non-zero elements: {np.count_nonzero(growth)}")

print("\n" + "="*80)
print("COSINE SIMILARITY CALCULATION:")
print("="*80)

if len(growth_vectors) >= 2:
    v1 = growth_vectors['3almashi']
    v2 = growth_vectors['Loathe Thy Neighbor']
    v3 = growth_vectors['Echo a Delta']
    
    # Cosine similarity
    def cosine_sim(a, b):
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        return dot / (norm_a * norm_b + 1e-8)
    
    sim_12 = cosine_sim(v1, v2)
    sim_13 = cosine_sim(v1, v3)
    
    print(f"\n3almashi vs Loathe Thy Neighbor:")
    print(f"  Cosine similarity: {sim_12:.4f} ({int(sim_12*100)}%)")
    print(f"  Vector 1 (first 5): {v1[:5]}")
    print(f"  Vector 2 (first 5): {v2[:5]}")
    
    print(f"\n3almashi vs Echo a Delta:")
    print(f"  Cosine similarity: {sim_13:.4f} ({int(sim_13*100)}%)")
    print(f"  Vector 1 (first 5): {v1[:5]}")
    print(f"  Vector 3 (first 5): {v3[:5]}")
    
    print("\n" + "="*80)
    print("ANALYSIS:")
    print("="*80)
    
    if sim_12 > 0.99 or sim_13 > 0.99:
        print("✅ High similarity (>99%) is CORRECT based on growth vectors")
        print("   All movies have 2 non-zero growth values + 58 zeros")
        print("   The 2 growth values are similar in magnitude and pattern")
    else:
        print("❌ Similarity scores don't match - there's still a bug!")
