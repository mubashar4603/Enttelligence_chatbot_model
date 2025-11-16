import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os


df = pd.read_csv("AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv")
df = df[["Title", "DBR", "Sales Estimate"]]
df = df[(df['DBR'] != 0) & (df['DBR'].notna())]
df = df[(df['Sales Estimate'].notna())]

df['Sales Estimate'] = df['Sales Estimate'].astype(str).str.replace(",","").astype(float)


# min_day = int(df['DBR'].min())
min_day = int(df[df['Sales Estimate'] > 0]['DBR'].min())
max_day = int(df['DBR'].max())

print(f"Global day range: {min_day} to {max_day}")

# Create a complete day range
global_days = np.arange(min_day, max_day+1)

# Create a dataframe with all combinations of movie x day
movies = df['Title'].unique()
full_index = pd.MultiIndex.from_product([movies, global_days], names=['Title','DBR'])
full_df = pd.DataFrame(index=full_index).reset_index()

# Merge with original data
full_df = full_df.merge(df, on=['Title','DBR'], how='left')

# Fill missing revenue with 0
full_df['Sales Estimate'] = full_df['Sales Estimate'].fillna(0)


# Step 1: Sort by movie & day
full_df = full_df.sort_values(by=["Title","DBR"])


# Step 2: Group by movie and do cumulative sum
full_df['cum_revenue'] = full_df.groupby('Title')['Sales Estimate'].cumsum()


plt.figure(figsize=(12,6))
sns.set_style("whitegrid")

grouped = full_df.groupby('Title')  # pre-group once

for count, (movie, movie_data) in enumerate(grouped, start=1):
    plt.plot(movie_data['DBR'], movie_data['cum_revenue'], alpha=0.5)  # remove marker for speed
    print(count)
    if count % 100 == 0:
        print(f"Plotted {count} movies")  # progress indicator

plt.title("Cumulative Revenue Curve per Movie")
plt.xlabel("Days relative to release")
plt.ylabel("Cumulative Revenue")


# out = "plots/movie_curves.pdf"
# plt.savefig(out, bbox_inches="tight")
# plt.close()
# print("Saved vector:", out)

plt.show()

print("yes")