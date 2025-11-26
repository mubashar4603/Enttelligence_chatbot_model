"""
Quick Test Script - Compare V1 vs V2 Results
=============================================
Run this to see the difference between original and improved versions
"""

import pickle
import numpy as np

print("="*80)
print("COMPARING V1 vs V2 SIMILARITY ENGINE")
print("="*80)

# Load V1 data
print("\n[1/4] Loading V1 data...")
try:
    with open("movie_data.pkl", "rb") as f:
        v1_data = pickle.load(f)
    v1_titles = v1_data['titles']
    v1_metadata = v1_data['metadata']
    print(f"   ✓ V1: {len(v1_titles)} movies indexed")
except:
    print("   ❌ V1 data not found. Run build_movie_similarity_engine.py first")
    v1_titles = []

# Load V2 data
print("\n[2/4] Loading V2 data...")
try:
    with open("movie_metadata_v2.pkl", "rb") as f:
        v2_data = pickle.load(f)
    v2_metadata = v2_data['metadata']
    v2_aligned = v2_data['aligned_data']
    v2_titles = [m['title'] for m in v2_metadata]
    print(f"   ✓ V2: {len(v2_titles)} movies indexed")
except:
    print("   ❌ V2 data not found. Run build_movie_similarity_engine_v2.py first")
    v2_titles = []

# Compare
print("\n[3/4] Comparison:")
print("-"*80)

if v1_titles and v2_titles:
    print(f"Movies in V1: {len(v1_titles)}")
    print(f"Movies in V2: {len(v2_titles)}")
    print(f"Difference: {abs(len(v1_titles) - len(v2_titles))} movies")
    
    # Check a sample movie
    if len(v2_titles) > 0:
        sample_movie = v2_titles[0]
        print(f"\n[4/4] Sample Movie Analysis: {sample_movie}")
        print("-"*80)
        
        if sample_movie in v2_aligned:
            data = v2_aligned[sample_movie]
            print(f"\nOriginal DBR Range: {data['original_days'].min()} to {data['original_days'].max()}")
            print(f"Original Data Points: {len(data['original_days'])}")
            print(f"\nAligned DBR Range: {data['aligned_days'].min()} to {data['aligned_days'].max()}")
            print(f"Aligned Data Points: {len(data['aligned_days'])}")
            print(f"\nRevenue Normalization:")
            print(f"  Original Final Revenue: ${data['original_revenue'][-1]:,.2f}")
            print(f"  Normalized Final: {data['aligned_revenue_pct'][-1]:.1f}%")
            
            # Find metadata
            meta = next((m for m in v2_metadata if m['title'] == sample_movie), None)
            if meta:
                print(f"\nMetadata:")
                print(f"  Total Revenue: ${meta['total_revenue']:,.2f}")
                print(f"  Tier: {meta['tier']}")
                print(f"  Active Days: {meta['active_days']}")
                print(f"  DBR Range: {meta['dbr_range']}")

print("\n" + "="*80)
print("KEY IMPROVEMENTS IN V2:")
print("="*80)
print("✅ Timeline Alignment: All movies aligned to -50 to +50 DBR")
print("✅ Missing Data: Interpolated for smooth curves")
print("✅ Revenue Normalization: Converted to 0-100% scale")
print("✅ Better Features: 99 dimensions vs 60")
print("✅ Better Visualization: Aligned curves, easy comparison")
print("="*80)

print("\n💡 To test similarity search:")
print("   V1: Run build_movie_similarity_engine.py and use find()")
print("   V2: Run build_movie_similarity_engine_v2.py and use find_similar_v2()")
print("\n📊 To compare graphs:")
print("   V1 graphs: similarity_graphs/")
print("   V2 graphs: similarity_graphs_v2/")
print("="*80)
