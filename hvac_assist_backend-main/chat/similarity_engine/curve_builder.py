import numpy as np
import pandas as pd
from config import N_POINTS

def build_resampled_matrix(df: pd.DataFrame):
    titles = []
    vectors = []
    meta = []

    for title, g in df.groupby("Title"):
        g = g.sort_values("DBR")
        x = g["DBR"].values
        y = g["cumulative_revenue"].values
        y = np.nan_to_num(y, nan=0.0)

        if len(x) < 2 or (x[-1] - x[0]) == 0:
            xp = np.linspace(0, 1, N_POINTS)
            yp = np.full(N_POINTS, y[-1] if len(y) > 0 else 0.0)
        else:
            x_norm = (x - x[0]) / (x[-1] - x[0])
            x_norm_unique, unique_idx = np.unique(x_norm, return_index=True)
            y_unique = y[unique_idx]
            xp = np.linspace(0, 1, N_POINTS)
            yp = np.interp(xp, x_norm_unique, y_unique)

        peak = np.max(yp)
        yp_norm = yp / peak if peak > 0 else yp
        yp_norm = np.nan_to_num(yp_norm, nan=0.0, posinf=1.0, neginf=0.0)

        titles.append(title)
        vectors.append(yp_norm)
        meta.append({
            "Title": title,
            "total_revenue": peak,
            "points": len(x)
        })

    return np.vstack(vectors), titles, pd.DataFrame(meta)