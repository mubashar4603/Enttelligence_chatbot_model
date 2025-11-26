import pandas as pd
import numpy as np

# Input / Output
INPUT = "preprocessed_movies.csv"
OUTPUT = "movies_with_growth.csv"

# Load preprocessed data
df = pd.read_csv(INPUT)

# Ensure sorting by Title then DBR
df = df.sort_values(["Title", "DBR"]).reset_index(drop=True)

# Step 1: Compute cumulative revenue
df["cumulative_revenue"] = df.groupby("Title")["Sales Estimate"].cumsum()

# Step 2: Compute DBR-gap aware log-growth
def compute_growth_with_dbr_gap(group):
    group = group.sort_values("DBR").reset_index(drop=True)
    sales = group["Sales Estimate"].replace(0, 1e-6)  # avoid log(0)
    dbr = group["DBR"]

    # Compute log-growth
    log_sales = np.log(sales)
    log_diff = log_sales.diff().fillna(0)  # first day growth = 0

    # Compute DBR gap
    dbr_gap = dbr.diff().fillna(1)  # first day gap = 1
    # per-day normalized growth
    growth = log_diff / dbr_gap

    # Optional smoothing (rolling 3-day)
    growth = pd.Series(growth).rolling(3, min_periods=1, center=True).mean()

    group["growth"] = growth.values
    return group

# Apply per movie
df = df.groupby("Title", group_keys=False).apply(compute_growth_with_dbr_gap)

# Save output
df.to_csv(OUTPUT, index=False)
print("Saved DBR-gap aware growth CSV to:", OUTPUT)
