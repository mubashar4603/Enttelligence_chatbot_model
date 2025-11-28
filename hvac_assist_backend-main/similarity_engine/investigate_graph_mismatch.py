import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

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
df['dbr'] = pd.to_numeric(df['dbr'], errors='coerce').fillna(0).astype(int)
df['daily_revenue'] = df['daily_revenue'].astype(str).str.replace(',', '').str.replace(r'[^0-9.\-]', '', regex=True)
df['daily_revenue'] = pd.to_numeric(df['daily_revenue'], errors='coerce').fillna(0)
df['growth_pct'] = pd.to_numeric(df['growth_pct'], errors='coerce').fillna(0)

# Movies from the test
movies = ['3almashi', 'Loathe Thy Neighbor', 'Echo a Delta', 'Anweshippin Kandethum']

print("="*80)
print("INVESTIGATING: Why do graphs look different but similarity is high?")
print("="*80)

for movie in movies:
    movie_data = df[df['title'] == movie].copy()
    movie_data = movie_data.sort_values('dbr')
    
    print(f"\n{movie}:")
    print("-" * 80)
    
    # Show ALL data (including negative DBR)
    print("\nALL DATA (including pre-release):")
    print(movie_data[['dbr', 'daily_revenue', 'growth_pct']].to_string(index=False))
    
    # Show only active days (DBR >= 1, revenue > 100)
    active = movie_data[(movie_data['dbr'] >= 1) & (movie_data['daily_revenue'] > 100)]
    print(f"\nACTIVE DAYS ONLY (DBR >= 1, revenue > 100):")
    print(active[['dbr', 'daily_revenue', 'growth_pct']].to_string(index=False))
    
    # Calculate growth curve as the bot does
    if len(active) >= 3:
        daily = active['daily_revenue'].values
        growth = np.diff(daily) / (daily[:-1] + 1e-8) * 100.0
        growth = np.nan_to_num(growth, nan=0.0)
        growth = np.clip(growth, -99, 999)
        
        print(f"\nGROWTH CURVE (as calculated by bot):")
        print(f"  {growth[:10]}")

print("\n" + "="*80)
print("PROBLEM IDENTIFIED:")
print("="*80)
print("""
The GRAPH is plotting 'Growth (%)' column from CSV (which includes ALL days)
But the BOT is calculating growth from ACTIVE days only (revenue > 100)!

This is why they look different!

The graph should plot the SAME growth values that the bot uses for similarity.
""")
