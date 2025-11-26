# preprocess_step1.py
import pandas as pd
import numpy as np

INPUT_CSV = "AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv"
OUTPUT_CSV = "preprocessed_movies.csv"
CHUNK_SIZE = 200_000  # adjust based on memory

def clean_chunk(df):
    # keep only relevant columns (safety)
    cols = [c for c in ["Title", "DBR", "Sales Estimate", "cumulative_revenue"] if c in df.columns]
    df = df[cols].copy()

    # drop rows where DBR or Sales Estimate is NaN
    df = df.dropna(subset=["DBR", "Sales Estimate"])

    # ensure types
    df["DBR"] = df["DBR"].astype(int)
    df["Sales Estimate"] = pd.to_numeric(df["Sales Estimate"], errors="coerce")

    # drop rows where Sales Estimate failed to convert (NaN)
    df = df.dropna(subset=["Sales Estimate"])
    return df

# Step A: Read in chunks and aggregate Title+DBR duplicates across chunks
agg_parts = []  # will collect partial aggregated frames

reader = pd.read_csv(INPUT_CSV, chunksize=CHUNK_SIZE)
for i, chunk in enumerate(reader):
    chunk_clean = clean_chunk(chunk)
    # aggregate duplicates within chunk by summing Sales Estimate
    part = chunk_clean.groupby(["Title", "DBR"], as_index=False)["Sales Estimate"].sum()
    agg_parts.append(part)
    print(f"Chunk {i+1} processed, rows -> {len(part)}")

# combine partial aggregates and re-aggregate to ensure global dedupe
df_agg = pd.concat(agg_parts, ignore_index=True)
df_agg = df_agg.groupby(["Title", "DBR"], as_index=False)["Sales Estimate"].sum()
print("Global aggregation done. Unique (Title,DBR) rows:", len(df_agg))

# Step B: remove consecutive-zero runs (per movie) of length >= 2
def remove_long_zero_runs(movie_df, min_run_len=2):
    # movie_df assumed sorted by DBR
    movie_df = movie_df.sort_values("DBR").reset_index(drop=True)
    sales = movie_df["Sales Estimate"].values

    # identify runs of zeros
    is_zero = (sales == 0)
    # compute run ids
    run_id = (np.diff(np.concatenate(([0], is_zero.astype(int)))) != 0).cumsum()
    # For each run where is_zero==True and run length >= min_run_len -> mark to drop
    to_drop = np.zeros(len(sales), dtype=bool)
    for rid in np.unique(run_id):
        idxs = np.where(run_id == rid)[0]
        if is_zero[idxs[0]]:  # this run is zeros
            if len(idxs) >= min_run_len:
                to_drop[idxs] = True
    # keep rows that are not marked for drop
    return movie_df.loc[~to_drop].reset_index(drop=True)

# apply per movie
out_parts = []
titles = df_agg["Title"].unique()
for t in titles:
    sub = df_agg[df_agg["Title"] == t].copy()
    cleaned = remove_long_zero_runs(sub, min_run_len=2)
    if len(cleaned) > 0:
        out_parts.append(cleaned)
    # if after removal movie has zero rows -> it's dropped entirely
print("Applied consecutive-zero-run removal.")

# final concatenate
if out_parts:
    df_cleaned = pd.concat(out_parts, ignore_index=True)
else:
    df_cleaned = pd.DataFrame(columns=["Title", "DBR", "Sales Estimate"])

# For clarity, sort by Title then DBR
df_cleaned = df_cleaned.sort_values(["Title", "DBR"]).reset_index(drop=True)

# Optionally drop movies with too few data points (e.g., < 3 records)
MIN_POINTS = 3
counts = df_cleaned.groupby("Title").size()
good_titles = counts[counts >= MIN_POINTS].index
df_final = df_cleaned[df_cleaned["Title"].isin(good_titles)].reset_index(drop=True)
print(f"Movies with >= {MIN_POINTS} points: {len(good_titles)}. Final rows: {len(df_final)}")

# Save cleaned file
df_final.to_csv(OUTPUT_CSV, index=False)
print("Preprocessed CSV written to:", OUTPUT_CSV)
