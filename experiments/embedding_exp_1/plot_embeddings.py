"""
Embedding Space Visualizer — Experiment 1
==========================================
Generates UMAP 2D projections for each model's embeddings.json
Colored by topic, shaped by source so you can see both dimensions at once.

Usage:
    python plot_embeddings.py

Output:
    plots/<slug>_umap.png  — one plot per model
    plots/all_models.png   — grid of all models side by side

Install:
    pip install umap-learn matplotlib numpy
"""

import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

try:
    import umap
except ImportError:
    print("Install umap-learn: pip install umap-learn")
    raise

# ── paths ─────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
MODELS_DIR = HERE / "models" / "data"
PLOTS_DIR = HERE / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# ── style ──────────────────────────────────────────────────────────────────
TOPIC_COLORS = {
    "agents":     "#4C9BE8",   # blue
    "rag":        "#E8834C",   # orange
    "multimodal": "#5CBF7A",   # green
    "finetuning": "#BF5C9E",   # purple
}

SOURCE_MARKERS = {
    "arxiv":   "o",    # circle
    "reddit":  "s",    # square
    "twitter": "^",    # triangle
    "devto":   "D",    # diamond (legacy, just in case)
}

SOURCE_LABELS = {
    "arxiv":   "arXiv",
    "reddit":  "Reddit",
    "twitter": "Twitter",
    "devto":   "DevTo",
}


def load_embeddings(model_dir: Path):
    path = model_dir / "embeddings.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def plot_model(slug: str, embeddings: dict, ax, title: str):
    vectors, labels, sources = [], [], []

    for item_id, item in embeddings.items():
        vectors.append(item["vector"])
        labels.append(item["label"])
        sources.append(item["source"])

    X = np.array(vectors, dtype=np.float32)

    # UMAP reduction to 2D
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=15,
        min_dist=0.1,
        metric="cosine",
        random_state=42,
    )
    X2 = reducer.fit_transform(X)

    # plot each topic-source combo
    for topic, color in TOPIC_COLORS.items():
        for source, marker in SOURCE_MARKERS.items():
            mask = [
                i for i, (l, s) in enumerate(zip(labels, sources))
                if l == topic and s == source
            ]
            if not mask:
                continue
            pts = X2[mask]
            ax.scatter(
                pts[:, 0], pts[:, 1],
                c=color,
                marker=marker,
                s=60,
                alpha=0.75,
                edgecolors="white",
                linewidths=0.4,
                zorder=3,
            )

    ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_facecolor("#1a1a2e")
    for spine in ax.spines.values():
        spine.set_visible(False)


def make_legend(fig):
    # topic legend
    topic_patches = [
        mpatches.Patch(color=c, label=t.capitalize())
        for t, c in TOPIC_COLORS.items()
    ]
    # source legend
    source_handles = [
        plt.Line2D([0], [0], marker=m, color="w", markerfacecolor="#aaaaaa",
                   markersize=8, label=SOURCE_LABELS[s], linestyle="None")
        for s, m in SOURCE_MARKERS.items()
        if s != "devto"
    ]
    all_handles = topic_patches + source_handles
    fig.legend(
        handles=all_handles,
        loc="lower center",
        ncol=len(all_handles),
        fontsize=9,
        frameon=False,
        labelcolor="white",
        bbox_to_anchor=(0.5, 0.01),
    )


def main():
    model_dirs = sorted([d for d in MODELS_DIR.iterdir() if d.is_dir()])
    if not model_dirs:
        print(f"No model dirs found in {MODELS_DIR}")
        return

    print(f"Found {len(model_dirs)} models: {[d.name for d in model_dirs]}")

    # ── individual plots ──────────────────────────────────────────────────
    for model_dir in model_dirs:
        slug = model_dir.name
        embeddings = load_embeddings(model_dir)
        if embeddings is None:
            print(f"  [{slug}] no embeddings.json, skipping")
            continue

        print(f"  [{slug}] plotting {len(embeddings)} items...")
        fig, ax = plt.subplots(figsize=(7, 6))
        fig.patch.set_facecolor("#0d0d1a")

        plot_model(slug, embeddings, ax, slug)
        make_legend(fig)

        plt.tight_layout(rect=[0, 0.06, 1, 1])
        out = PLOTS_DIR / f"{slug}_umap.png"
        plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close()
        print(f"  [{slug}] saved → {out}")

    # ── all models grid ───────────────────────────────────────────────────
    valid = []
    for model_dir in model_dirs:
        emb = load_embeddings(model_dir)
        if emb:
            valid.append((model_dir.name, emb))

    if not valid:
        return

    n = len(valid)
    ncols = 3
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 5 * nrows))
    fig.patch.set_facecolor("#0d0d1a")
    axes_flat = axes.flatten() if n > 1 else [axes]

    for i, (slug, embeddings) in enumerate(valid):
        print(f"  [grid] plotting {slug}...")
        plot_model(slug, embeddings, axes_flat[i], slug)

    # hide unused axes
    for j in range(len(valid), len(axes_flat)):
        axes_flat[j].set_visible(False)

    make_legend(fig)
    fig.suptitle(
        "Embedding Space — UMAP 2D Projections\nColored by topic · Shape by source",
        color="white", fontsize=13, fontweight="bold", y=1.01
    )

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    out = PLOTS_DIR / "all_models_umap.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"\n[grid] saved → {out}")
    print("\nDone. Check experiments/embedding_exp_1/plots/")


if __name__ == "__main__":
    main()
