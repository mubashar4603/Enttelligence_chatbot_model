# """
# Script to verify First Weekend Revenue calculations from my_export.csv

# This script calculates First Weekend Revenue using DIR -1, 1, 2, 3
# and compares with expected values.
# """

# import csv
# from collections import defaultdict

# def calculate_first_weekend_revenue(csv_file='my_export.csv'):
#     """
#     Calculate First Weekend Revenue (DIR -1, 1, 2, 3) for each movie.
    
#     Note: First Weekend uses DIR values -1, 1, 2, 3 because:
#     - SQL: (date_sh - release_date) BETWEEN -1 AND 2
#     - This translates to DIR: -1, 1, 2, 3 (DIR = diff + 1 when diff >= 0)
#     """
    
#     # Expected values from client
#     expected_values = {
#         'Dune: Part Two': 64817042,
#         'Twisters': 57050877,
#         'Joker': 28692416,
#         'Monkey Man': 8962509
#     }
    
#     # Group revenue by movie and DIR
#     movie_revenue = defaultdict(lambda: defaultdict(float))
    
#     with open(csv_file, 'r', encoding='utf-8') as f:
#         reader = csv.DictReader(f)
        
#         for row in reader:
#             if not row['dir_value'] or not row['dir_value'].strip():
#                 continue
            
#             try:
#                 dir_value = int(float(row['dir_value']))
#                 title = row['title'].strip()
                
#                 # Only include DIR -1, 1, 2, 3 for first weekend
#                 if dir_value in [-1, 1, 2, 3]:
#                     revenue = float(row['total_revenue']) if row['total_revenue'] else 0.0
#                     movie_revenue[title][dir_value] += revenue
#             except (ValueError, KeyError):
#                 continue
    
#     print("="*80)
#     print("FIRST WEEKEND REVENUE VERIFICATION (DIR -1, 1, 2, 3)")
#     print("="*80)
#     print("\nNote: First Weekend Revenue = Sum of total_revenue for DIR -1, 1, 2, 3")
#     print("SQL Logic: (date_sh - release_date) BETWEEN -1 AND 2")
#     print("This translates to DIR values: -1, 1, 2, 3\n")
    
#     print(f"{'Movie':<30} {'Expected':>15} {'Actual':>15} {'Difference':>15} {'Match':>10}")
#     print("-"*80)
    
#     all_match = True
#     for movie_name, expected in expected_values.items():
#         # Find matching movie (case-insensitive)
#         actual_title = None
#         for title in movie_revenue.keys():
#             if movie_name.lower() in title.lower() or title.lower() in movie_name.lower():
#                 actual_title = title
#                 break
        
#         if not actual_title:
#             print(f"{movie_name:<30} ${expected:>14,.2f} {'NOT FOUND':>15} {'N/A':>15} {'NO':>10}")
#             all_match = False
#             continue
        
#         # Calculate total for DIR -1, 1, 2, 3
#         total = sum([movie_revenue[actual_title][dir_val] for dir_val in [-1, 1, 2, 3]])
#         difference = expected - total
#         match = "YES" if abs(difference) < 1000 else "NO"  # Allow $1000 tolerance
        
#         if abs(difference) >= 1000:
#             all_match = False
        
#         print(f"{movie_name:<30} ${expected:>14,.2f} ${total:>14,.2f} ${difference:>14,.2f} {match:>10}")
        
#         # Show breakdown
#         print(f"  Breakdown:")
#         for dir_val in sorted([-1, 1, 2, 3]):
#             rev = movie_revenue[actual_title][dir_val]
#             print(f"    DIR {dir_val:>3}: ${rev:>14,.2f}")
#         print()
    
#     print("="*80)
#     if all_match:
#         print("✅ All values match within tolerance!")
#     else:
#         print("⚠️  Some values don't match. Check data aggregation.")
#     print("="*80)
    
#     # Show explanation
#     print("\n📝 EXPLANATION:")
#     print("-"*80)
#     print("""
# IMPORTANT DISTINCTION:

# 1. CUMULATIVE PRESALES (DBR-based):
#    - This is presales BEFORE release (DBR -60 to -1)
#    - Shows how many tickets were sold before release
#    - Example: Dune: Part Two cumulative presales = $8.75M (before release)

# 2. FIRST WEEKEND REVENUE (DIR -1, 1, 2, 3):
#    - This is revenue AFTER release during first weekend
#    - DIR -1 = day before release
#    - DIR 1, 2, 3 = first 3 days after release
#    - Example: Dune: Part Two first weekend = $64.8M (after release)

# These are DIFFERENT metrics:
# - Cumulative presales = tickets sold BEFORE release
# - First weekend revenue = tickets sold DURING first weekend (after release)

# The CSV contains BOTH:
# - Records with DBR values = presales data (before release)
# - Records with DIR values = post-release data (after release)
#     """)

# if __name__ == "__main__":
#     calculate_first_weekend_revenue()


# import pandas as pd

# # Load CSV
# df = pd.read_csv("AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv")

# # Replace DBR values below -50 with -50
# df['DBR'] = df['DBR'].apply(lambda x: -50 if x < -50 else x)

# # Fill NaN with a value (e.g., -50 or any default) before converting to int
# df['DBR'] = df['DBR'].fillna(-50).astype(int)

# # Save back
# df.to_csv("AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv", index=False)

# print("DBR values updated and converted to integers!")



import pandas as pd
import numpy as np

# Load CSV
df = pd.read_csv("AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv")

# Convert Sales Estimate to numeric
df['Sales Estimate'] = (
    df['Sales Estimate']
    .astype(str)
    .str.replace(",", "", regex=False)
    .replace("", 0)
    .astype(float)
)

# Sort by Title then DBR
df = df.sort_values(by=["Title", "DBR"], ascending=[True, True])

# 1️⃣ Cumulative Revenue per Title
df["cumulative_revenue"] = df.groupby("Title")["Sales Estimate"].cumsum()

# 2️⃣ Growth Rate using transform (prevents index mismatch)
df["growth_rate"] = (
    df.groupby("Title")["cumulative_revenue"]
      .transform(lambda x: x.pct_change())
      .replace([np.inf, -np.inf], np.nan)
      * 100
)

# Replace NaN (first row or division by zero) with 0
df["growth_rate"] = df["growth_rate"].fillna(0)

# Round both to 2 decimals
df["cumulative_revenue"] = df["cumulative_revenue"].round(2)
df["growth_rate"] = df["growth_rate"].round(2)

# Save
df.to_csv("AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv", index=False)

print("Done! No index errors, no inf, 2 decimals.")
