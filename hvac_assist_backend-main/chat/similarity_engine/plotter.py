# utils/plotter.py
import matplotlib.pyplot as plt
import numpy as np
import io
import base64

def curves_to_base64(query_title, similar_list, engine):
    x = np.linspace(0, 1, engine.matrix.shape[1])
    plt.figure(figsize=(10, 6))
    q_idx = engine.titles.index(query_title)
    plt.plot(x, engine.matrix[q_idx], linewidth=4, label=query_title, color='red')

    for title, sim in similar_list:
        idx = engine.titles.index(title)
        plt.plot(x, engine.matrix[idx], linewidth=2, alpha=0.8, label=f"{title} ({sim:.3f})")

    plt.legend()
    plt.title(f"Similar to: {query_title}")
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode()
    plt.close()
    return img_base64