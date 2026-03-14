"""
player_report.py
Genera 3 visualizaciones para comparar un jugador con sus similares más cercanos.

Uso:
    python -m src.visualization.player_report --player "Lamine Yamal" --output reports/
    python -m src.visualization.player_report --player "Vinicius Junior" --output reports/ --top 5
"""

import argparse
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for saving files

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns
import plotly.graph_objects as go
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_similarity
from mplsoccer import Radar, grid

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models.similarity_model import PlayerSimilarityModel
from src.utils.feature_config import MODEL_FEATURES

# ---------------------------------------------------------------------------
# Radar: 10 features representativas (todas con datos reales tras el fix del pipeline)
# ---------------------------------------------------------------------------
RADAR_FEATURES = [
    "goals_p90",
    "shots_total_p90",
    "key_passes_p90",
    "passes_progressive_p90",
    "dribbles_won_p90",
    "carry_distance_p90",
    "ball_recoveries_p90",
    "tackles_p90",
    "pass_completion_pct",
    "dribble_success_pct",
]

RADAR_LABELS = [
    "Goals p90",
    "Shots p90",
    "Key Passes p90",
    "Progressive\nPasses p90",
    "Dribbles\nWon p90",
    "Carry\nDistance p90",
    "Ball\nRecoveries p90",
    "Tackles p90",
    "Pass\nCompletion %",
    "Dribble\nSuccess %",
]

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG_COLOR    = "#24282a"     # background for all plots
COLOR_PLAYER  = "#E63946"   # red  (query player)
COLOR_SIMILAR = "#4CC9F0"   # cyan (similar player)
COLOR_OTHERS  = "#888888"   # grey (background players)

LEAGUE_FLAGS = {
    "Premier League": "[ENG]",
    "La Liga": "[ESP]",
    "Bundesliga": "[GER]",
    "Serie A": "[ITA]",
    "Ligue 1": "[FRA]",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_model() -> PlayerSimilarityModel:
    model = PlayerSimilarityModel()
    model.load()
    return model


def _get_position_group(position: str) -> str:
    """Map WhoScored position codes to broad group FW / MF / DF / GK.

    WhoScored codes: DC, DR, DL, DMC, DMR, DML (defence/DM),
                     MC, ML, MR, AMC, AMR, AML (midfield/AM),
                     FW, FWR, FWL (forward), GK, Sub.
    """
    pos = str(position).strip().upper()
    # Forwards
    if pos in ("FW", "FWR", "FWL"):
        return "FW"
    # Attacking mids / wide attackers (treat as FW for radar context)
    if pos in ("AMR", "AML", "AMC"):
        return "FW"
    # Defensive mids
    if pos in ("DMC", "DMR", "DML"):
        return "MF"
    # Central / wide mids
    if pos in ("MC", "ML", "MR"):
        return "MF"
    # Defenders
    if pos in ("DC", "DR", "DL"):
        return "DF"
    if pos == "GK":
        return "GK"
    # Fallback for "Sub" or unknown
    return "MF"


def _bounds_from_data(ref_df: pd.DataFrame, features: list[str], low_pct: float = 5, high_pct: float = 95):
    """Compute low/high bounds as percentiles of the reference population."""
    low  = [float(np.percentile(ref_df[f].dropna(), low_pct))  for f in features]
    high = [float(np.percentile(ref_df[f].dropna(), high_pct)) for f in features]
    # Ensure low < high with a small epsilon
    low  = [l if l < h else h * 0.8 for l, h in zip(low, high)]
    return low, high


# ---------------------------------------------------------------------------
# 1. Radar chart (mplsoccer Radar + grid)
# ---------------------------------------------------------------------------

def plot_radar(
    model: PlayerSimilarityModel,
    player_name: str,
    output_path: Path,
) -> None:
    """Radar chart comparing player vs. top-1 similar using mplsoccer Radar."""

    df_raw = pd.read_parquet(
        PROJECT_ROOT / "data" / "features" / "features_model_raw.parquet"
    )

    # Resolve exact name & metadata
    mask = df_raw["player_name"].str.contains(player_name, case=False, na=False)
    player_row_raw = df_raw[mask].iloc[0]
    exact_name    = player_row_raw["player_name"]
    player_team   = player_row_raw["team"]
    player_league = player_row_raw["league"]
    player_pos    = player_row_raw["position"]

    # Top-1 similar
    similars  = model.find_similar_players(player_name, top_n=1)
    comp_name = similars.iloc[0]["player_name"]
    comp_row_raw = df_raw[df_raw["player_name"] == comp_name].iloc[0]
    comp_team   = comp_row_raw["team"]
    comp_league = comp_row_raw["league"]
    sim_score   = similars.iloc[0]["similarity"]

    # Reference population for bounds: same broad position group
    pos_group = _get_position_group(player_pos)
    ref_df    = df_raw[df_raw["position"].apply(_get_position_group) == pos_group]
    low, high = _bounds_from_data(ref_df, RADAR_FEATURES)

    # Round-int flags (False = show 2 decimals, True = integer)
    round_int = [False] * len(RADAR_FEATURES)

    radar = Radar(
        params=RADAR_LABELS,
        min_range=low,
        max_range=high,
        round_int=round_int,
        num_rings=4,
        ring_width=1,
        center_circle_radius=1,
    )

    # Player value arrays (raw, per-90 or ratio)
    # Clip values to [low, high] bounds so mplsoccer division is always valid
    vals_player = [float(np.clip(player_row_raw[f], lo, hi)) for f, lo, hi in zip(RADAR_FEATURES, low, high)]
    vals_comp   = [float(np.clip(comp_row_raw[f],   lo, hi)) for f, lo, hi in zip(RADAR_FEATURES, low, high)]

    # Build figure with mplsoccer grid (title + radar + endnote)
    fig, axs = grid(
        figheight=14,
        grid_height=0.82,
        title_height=0.10,
        endnote_height=0.03,
        title_space=0,
        endnote_space=0,
        grid_key="radar",
        axis=False,
    )
    fig.patch.set_facecolor(BG_COLOR)

    # --- Radar area ---
    radar.setup_axis(ax=axs["radar"], facecolor=BG_COLOR)
    axs["radar"].set_facecolor(BG_COLOR)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        rings = radar.draw_circles(
            ax=axs["radar"],
            facecolor="#2e3336",
            edgecolor="#3d4347",
            linewidth=1,
        )
        radar_output = radar.draw_radar_compare(
            vals_player,
            vals_comp,
            ax=axs["radar"],
            kwargs_radar={"facecolor": COLOR_PLAYER,  "alpha": 0.55},
            kwargs_compare={"facecolor": COLOR_SIMILAR, "alpha": 0.45},
        )
        _, _, vertices1, vertices2 = radar_output
        radar.draw_range_labels(ax=axs["radar"], fontsize=11, color="#aaaaaa")
        radar.draw_param_labels(ax=axs["radar"], fontsize=13, color="white")

    # Vertex dots
    axs["radar"].scatter(vertices1[:, 0], vertices1[:, 1],
                         c=COLOR_PLAYER,  edgecolors="#cccccc", marker="o", s=90, zorder=3)
    axs["radar"].scatter(vertices2[:, 0], vertices2[:, 1],
                         c=COLOR_SIMILAR, edgecolors="#cccccc", marker="o", s=90, zorder=3)

    # --- Title ---
    axs["title"].set_facecolor(BG_COLOR)
    flag_p = LEAGUE_FLAGS.get(player_league, "")
    flag_c = LEAGUE_FLAGS.get(comp_league, "")

    axs["title"].text(0.02, 0.70, exact_name, fontsize=22, fontweight="bold",
                      color=COLOR_PLAYER, ha="left", va="center")
    axs["title"].text(0.02, 0.22, f"{player_team}  {flag_p}",
                      fontsize=14, color="#cccccc", ha="left", va="center")

    axs["title"].text(0.98, 0.70, comp_name, fontsize=22, fontweight="bold",
                      color=COLOR_SIMILAR, ha="right", va="center")
    axs["title"].text(0.98, 0.22, f"{comp_team}  {flag_c}  |  sim {sim_score:.3f}",
                      fontsize=14, color="#cccccc", ha="right", va="center")

    # --- Endnote ---
    axs["endnote"].set_facecolor(BG_COLOR)
    axs["endnote"].text(0.99, 0.5,
                        f"Values per 90 min / ratios  |  bounds = 5th-95th pct of {pos_group} group",
                        fontsize=10, color="#888888", ha="right", va="center")

    out_file = output_path / f"radar_{exact_name.replace(' ', '_')}.png"
    plt.savefig(out_file, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    print(f"  Radar saved -> {out_file}")


# ---------------------------------------------------------------------------
# 2. PCA Scatter (Plotly interactive, saved as static PNG via kaleido)
# ---------------------------------------------------------------------------

def plot_pca_scatter(
    model: PlayerSimilarityModel,
    player_name: str,
    output_path: Path,
    top_n: int = 5,
) -> None:
    """2D PCA scatter of all players; highlights query + top-N similar."""

    df = model.df.copy()
    X = df[MODEL_FEATURES].values

    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(X)
    df["pca_1"] = coords[:, 0]
    df["pca_2"] = coords[:, 1]

    var1 = pca.explained_variance_ratio_[0] * 100
    var2 = pca.explained_variance_ratio_[1] * 100

    # Resolve player and similars
    mask = df["player_name"].str.contains(player_name, case=False, na=False)
    exact_name = df[mask].iloc[0]["player_name"]
    similars = model.find_similar_players(player_name, top_n=top_n)
    similar_names = set(similars["player_name"].tolist())

    def _category(name):
        if name == exact_name:
            return "Query Player"
        if name in similar_names:
            return "Similar Players"
        return "Others"

    df["category"] = df["player_name"].apply(_category)

    color_map = {
        "Query Player": COLOR_PLAYER,
        "Similar Players": COLOR_SIMILAR,
        "Others": "#888888",
    }
    size_map = {
        "Query Player": 16,
        "Similar Players": 11,
        "Others": 5,
    }
    opacity_map = {
        "Query Player": 1.0,
        "Similar Players": 0.9,
        "Others": 0.35,
    }

    fig = go.Figure()

    for cat in ["Others", "Similar Players", "Query Player"]:
        sub = df[df["category"] == cat]
        sim_vals = []
        for n_ in sub["player_name"]:
            if n_ == exact_name:
                sim_vals.append(1.0)
            elif n_ in similar_names:
                row = similars[similars["player_name"] == n_]
                sim_vals.append(float(row["similarity"].iloc[0]) if len(row) else 0.0)
            else:
                sim_vals.append(None)

        hover_text = [
            f"<b>{row['player_name']}</b><br>"
            f"{row['team']} · {row['league']}<br>"
            f"Position: {row['position']}<br>"
            + (f"Similarity: {s:.4f}" if s is not None else "")
            for (_, row), s in zip(sub.iterrows(), sim_vals)
        ]

        fig.add_trace(
            go.Scatter(
                x=sub["pca_1"],
                y=sub["pca_2"],
                mode="markers+text" if cat != "Others" else "markers",
                marker=dict(
                    color=color_map[cat],
                    size=size_map[cat],
                    opacity=opacity_map[cat],
                    line=dict(width=1, color="white") if cat != "Others" else dict(width=0),
                ),
                text=sub["player_name"] if cat != "Others" else None,
                textposition="top center",
                textfont=dict(size=9, color="white"),
                hovertext=hover_text,
                hoverinfo="text",
                name=cat,
            )
        )

    # Compute tight axis ranges from the data (5% padding)
    x_min, x_max = df["pca_1"].min(), df["pca_1"].max()
    y_min, y_max = df["pca_2"].min(), df["pca_2"].max()
    x_pad = (x_max - x_min) * 0.05
    y_pad = (y_max - y_min) * 0.05

    fig.update_layout(
        title=dict(
            text=f"Player Space  |  {exact_name} & top-{top_n} similar players",
            font=dict(color="white", size=14),
            x=0.5,
        ),
        xaxis=dict(
            title=f"PC1 ({var1:.1f}% var)",
            color="white", gridcolor="#3a3f42", zerolinecolor="#555555",
            range=[x_min - x_pad, x_max + x_pad],
            autorange=False,
        ),
        yaxis=dict(
            title=f"PC2 ({var2:.1f}% var)",
            color="white", gridcolor="#3a3f42", zerolinecolor="#555555",
            range=[y_min - y_pad, y_max + y_pad],
            autorange=False,
            scaleanchor="x",
            scaleratio=1,
        ),
        paper_bgcolor=BG_COLOR,
        plot_bgcolor="#2e3336",
        legend=dict(
            font=dict(color="white"),
            bgcolor="rgba(0,0,0,0.4)",
        ),
        margin=dict(l=60, r=40, t=60, b=60),
        width=950,
        height=650,
    )

    out_file = output_path / f"pca_{exact_name.replace(' ', '_')}.png"
    try:
        fig.write_image(str(out_file), scale=1.5)
        print(f"  PCA scatter saved -> {out_file}")
    except Exception:
        # kaleido not installed - save as HTML instead
        html_file = out_file.with_suffix(".html")
        fig.write_html(str(html_file))
        print(f"  kaleido not available - PCA scatter saved as HTML -> {html_file}")


# ---------------------------------------------------------------------------
# 3. Similarity Heatmap (seaborn)
# ---------------------------------------------------------------------------

def plot_similarity_heatmap(
    model: PlayerSimilarityModel,
    player_name: str,
    output_path: Path,
    top_n: int = 4,
) -> None:
    """
    Heatmap: rows = top HEATMAP_FEATURES most discriminating features,
             columns = query player + top-N similar (raw values, normalized 0-1 per feature).
    """
    HEATMAP_N_FEATURES = 12

    df_raw = pd.read_parquet(
        PROJECT_ROOT / "data" / "features" / "features_model_raw.parquet"
    )

    # Resolve query player
    mask = df_raw["player_name"].str.contains(player_name, case=False, na=False)
    exact_name = df_raw[mask].iloc[0]["player_name"]

    # Top-N similars
    similars = model.find_similar_players(player_name, top_n=top_n)
    players_ordered = [exact_name] + similars["player_name"].tolist()

    # Extract raw rows for these players
    sub = df_raw[df_raw["player_name"].isin(players_ordered)].copy()
    sub = sub.set_index("player_name").loc[players_ordered, MODEL_FEATURES]

    # Select most discriminating features: highest std across these players
    stds = sub.std(axis=0)
    top_features = stds.nlargest(HEATMAP_N_FEATURES).index.tolist()
    sub_top = sub[top_features]

    # Min-max scale each feature across all players (0-1) for display
    sub_scaled = (sub_top - sub_top.min()) / (sub_top.max() - sub_top.min() + 1e-9)
    sub_scaled = sub_scaled.T  # features as rows, players as columns

    # Human-readable feature labels
    feat_label_map = {
        "goals_p90": "Goals p90",
        "shots_total_p90": "Shots p90",
        "shots_on_target_p90": "Shots on Target p90",
        "key_passes_p90": "Key Passes p90",
        "assists_p90": "Assists p90",
        "passes_total_p90": "Passes p90",
        "passes_progressive_p90": "Progressive Passes p90",
        "passes_into_box_p90": "Passes Into Box p90",
        "crosses_p90": "Crosses p90",
        "throughballs_p90": "Through Balls p90",
        "dribbles_won_p90": "Dribbles Won p90",
        "touches_p90": "Touches p90",
        "carries_p90": "Carries p90",
        "tackles_p90": "Tackles p90",
        "interceptions_p90": "Interceptions p90",
        "ball_recoveries_p90": "Ball Recoveries p90",
        "aerials_won_p90": "Aerials Won p90",
        "shot_accuracy_pct": "Shot Accuracy %",
        "shots_from_box_pct": "Shots From Box %",
        "pass_completion_pct": "Pass Completion %",
        "passes_forward_pct": "Forward Passes %",
        "passes_progressive_pct": "Progressive Pass %",
        "passes_into_box_pct": "Passes Into Box %",
        "passes_switch_pct": "Switch Pass %",
        "avg_pass_length": "Avg Pass Length",
        "dribble_success_pct": "Dribble Success %",
        "aerial_win_pct": "Aerial Win %",
        "defensive_actions_p90": "Defensive Actions p90",
        "carry_distance_p90": "Carry Distance p90",
    }
    row_labels = [feat_label_map.get(f, f) for f in sub_scaled.index]

    # Column labels: name + similarity
    col_labels = []
    sim_dict = dict(zip(similars["player_name"], similars["similarity"]))
    for pname in players_ordered:
        if pname == exact_name:
            col_labels.append(f"{pname}\n(query)")
        else:
            s = sim_dict.get(pname, 0.0)
            col_labels.append(f"{pname}\n({s:.3f})")

    # Raw values for annotation
    annot_df = sub_top.T.copy()
    annot_df.index = row_labels
    annot_df.columns = col_labels
    # Format: 2 decimal places
    annot_vals = annot_df.map(lambda x: f"{x:.2f}")

    sub_scaled.index = row_labels
    sub_scaled.columns = col_labels

    fig, ax = plt.subplots(figsize=(max(8, len(players_ordered) * 2.2), 7))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    sns.heatmap(
        sub_scaled,
        ax=ax,
        annot=annot_vals,
        fmt="",
        cmap="RdYlGn",
        linewidths=0.4,
        linecolor=BG_COLOR,
        cbar_kws={"shrink": 0.7, "label": "Relative value (0=min, 1=max)"},
        annot_kws={"size": 8, "color": "black"},
        vmin=0,
        vmax=1,
    )

    ax.set_title(
        f"Feature Comparison — {exact_name} vs. Top-{top_n} Similar Players",
        color="white", fontsize=13, fontweight="bold", pad=12,
    )
    ax.tick_params(axis="x", colors="white", labelsize=8)
    ax.tick_params(axis="y", colors="white", labelsize=8.5, rotation=0)

    # Highlight query player column header
    ax.get_xticklabels()[0].set_color(COLOR_PLAYER)
    ax.get_xticklabels()[0].set_fontweight("bold")

    cbar = ax.collections[0].colorbar
    cbar.ax.yaxis.label.set_color("white")
    cbar.ax.tick_params(colors="white")

    plt.tight_layout()
    out_file = output_path / f"heatmap_{exact_name.replace(' ', '_')}.png"
    plt.savefig(out_file, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Heatmap saved -> {out_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate player similarity visualizations."
    )
    parser.add_argument("--player", required=True, help="Player name to query.")
    parser.add_argument(
        "--output", default="reports/", help="Output directory (default: reports/)."
    )
    parser.add_argument(
        "--top", type=int, default=5,
        help="Number of similar players to highlight in PCA/heatmap (default: 5)."
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\nLoading model...")
    model = _load_model()

    print(f"\nGenerating reports for: {args.player}")
    print("-" * 50)

    print("[1/3] Radar chart...")
    plot_radar(model, args.player, output_path)

    print("[2/3] PCA scatter plot...")
    plot_pca_scatter(model, args.player, output_path, top_n=args.top)

    print("[3/3] Similarity heatmap...")
    plot_similarity_heatmap(model, args.player, output_path, top_n=min(args.top, 4))

    print(f"\nDone. All plots saved to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
