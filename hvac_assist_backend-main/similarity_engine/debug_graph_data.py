import pandas as pd
import numpy as np

# Read CSV
df = pd.read_csv("/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/similarity_engine/AI_Data_Dump_with_Growth.csv", 
                 encoding='utf-16', sep='\t')

df = df.rename(columns={
    'Title': 'title',
    'DBR': 'dbr',
    'Sales Estimate': 'daily_revenue'
})

df['title'] = df['title'].astype(str).str.strip()
df['dbr'] = pd.to_numeric(df['dbr'], errors='coerce').fillna(0).astype(int)
df['daily_revenue'] = df['daily_revenue'].astype(str).str.replace(',', '').str.replace(r'[^0-9.\-]', '', regex=True)
df['daily_revenue'] = pd.to_numeric(df['daily_revenue'], errors='coerce').fillna(0)

def analyze_movie(title):
    print(f"\nANALYSIS FOR: {title}")
    print("-" * 50)
    
    # Get raw data
    data = df[df['title'].str.lower() == title.lower()].sort_values('dbr')
    
    if data.empty:
        print("Movie not found!")
        return
        
    print("RAW DATA (Active Days only):")
    active = data[data['daily_revenue'] > 100].copy()
    print(active[['dbr', 'daily_revenue']].to_string(index=False))
    
    if len(active) < 2:
        print("Not enough active days for growth calculation")
        return

    # Calculate growth exactly as bot does
    daily = active['daily_revenue'].values
    growth = np.diff(daily) / (daily[:-1] + 1e-8) * 100.0
    
    print("\nCALCULATED GROWTH:")
    for i, g in enumerate(growth):
        dbr_from = active.iloc[i]['dbr']
        dbr_to = active.iloc[i+1]['dbr']
        print(f"  DBR {dbr_from} -> {dbr_to}: {g:.2f}%")
        
    print(f"\nVECTOR USED FOR SIMILARITY (First 5 values):")
    # Pad to 60
    vec = np.pad(growth, (0, max(0, 60 - len(growth))), 'constant')[:60]
    print(vec[:5])
    
    print(f"\nGRAPH POINTS:")
    days = np.arange(1, len(growth) + 1)
    for d, g in zip(days, growth):
        print(f"  X={d}, Y={g:.2f}")

print("="*80)
print("DEBUGGING DATA AND GRAPH LOGIC")
print("="*80)

analyze_movie("3almashi")
analyze_movie("Echo a Delta")
analyze_movie("Nowhere Special")
