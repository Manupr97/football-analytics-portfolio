"""
build_features.py
Pipeline completo: carga WhoScored → calcula features per-90 y ratios → guarda parquet.

Uso:
  python -m src.pipeline.build_features
  python -m src.pipeline.build_features --season 2025-2026 --min-minutes 450
  python -m src.pipeline.build_features --matchcenter-dir /ruta/alternativa/data/raw/matchcenter
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.load_whoscored import aggregate_players, _DEFAULT_MATCHCENTER_DIR
from src.utils.feature_config import ID_COLUMNS, MODEL_FEATURES

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = _PROJECT_ROOT / "data" / "features" / "features_model_raw.parquet"
DEFAULT_SEASON = "2025-2026"


def _safe_ratio(num: pd.Series, den: pd.Series, fill: float = 0.0) -> pd.Series:
    return np.where(den > 0, num / den, fill)


def build_features(
    matchcenter_dir: Path = _DEFAULT_MATCHCENTER_DIR,
    season: str = DEFAULT_SEASON,
    min_minutes: int = 450,
    out_path: Path = DEFAULT_OUT,
) -> pd.DataFrame:

    # 1. Cargar y agregar eventos
    df = aggregate_players(matchcenter_dir, season, min_minutes=min_minutes)

    minutes_90 = df["minutes"] / 90

    # 2. Features de volumen (per 90)
    df["goals_p90"]               = df["goals"]             / minutes_90
    df["shots_total_p90"]         = df["shots_total"]       / minutes_90
    df["shots_on_target_p90"]     = df["shots_on_target"]   / minutes_90
    df["key_passes_p90"]          = df["key_passes"]        / minutes_90
    df["assists_p90"]             = df["assists_pass"]      / minutes_90
    df["passes_total_p90"]        = df["passes_total"]      / minutes_90
    df["passes_progressive_p90"]  = df["passes_progressive"]/ minutes_90
    df["passes_into_box_p90"]     = df["passes_into_box"]   / minutes_90
    df["crosses_p90"]             = df["crosses"]           / minutes_90
    df["throughballs_p90"]        = df["throughballs"]      / minutes_90
    df["dribbles_won_p90"]        = df["dribbles_won"]      / minutes_90
    df["touches_p90"]             = df["touches"]           / minutes_90
    df["carries_p90"]             = df["carries"]           / minutes_90
    df["tackles_p90"]             = df["tackles"]           / minutes_90
    df["interceptions_p90"]       = df["interceptions"]     / minutes_90
    df["ball_recoveries_p90"]     = df["ball_recoveries"]   / minutes_90
    df["aerials_won_p90"]         = df["aerials_won"]       / minutes_90

    # 3. Features de estilo (ratios)
    df["shot_accuracy_pct"]       = _safe_ratio(df["shots_on_target"],    df["shots_total"])
    df["shots_from_box_pct"]      = _safe_ratio(df["shots_from_box"],     df["shots_total"])
    df["pass_completion_pct"]     = _safe_ratio(df["passes_completed"],   df["passes_total"])
    df["passes_forward_pct"]      = _safe_ratio(df["passes_forward"],     df["passes_total"])
    df["passes_progressive_pct"]  = _safe_ratio(df["passes_progressive"], df["passes_total"])
    df["passes_into_box_pct"]     = _safe_ratio(df["passes_into_box"],    df["passes_total"])
    df["passes_switch_pct"]       = _safe_ratio(df["passes_switch"],      df["passes_total"])
    df["avg_pass_length"]         = _safe_ratio(df["pass_length_sum"],    df["passes_total"])
    df["dribble_success_pct"]     = _safe_ratio(df["dribbles_won"],       df["dribbles_attempted"])
    df["aerial_win_pct"]          = _safe_ratio(df["aerials_won"],        df["aerials_total"])
    df["defensive_actions_p90"]   = (df["tackles"] + df["interceptions"] + df["ball_recoveries"]) / minutes_90
    df["carry_distance_p90"]      = df["carry_distance"] / minutes_90

    # 4. Seleccionar y ordenar columnas
    out = df[ID_COLUMNS + MODEL_FEATURES].copy()

    # Reemplazar inf por 0
    out.replace([np.inf, -np.inf], 0, inplace=True)
    num_cols = out.select_dtypes(include="number").columns
    out[num_cols] = out[num_cols].fillna(0)

    # 5. Guardar
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    print(f"\nGuardado: {out_path.name} — {len(out)} jugadores, {len(MODEL_FEATURES)} features")
    print(f"Ligas: {out['league'].value_counts().to_dict()}")

    return out


def main():
    parser = argparse.ArgumentParser(description="Construye el dataset de features desde WhoScored.")
    parser.add_argument("--season",           default=DEFAULT_SEASON)
    parser.add_argument("--min-minutes",      type=int, default=450)
    parser.add_argument("--matchcenter-dir",  type=Path, default=_DEFAULT_MATCHCENTER_DIR,
                        help="Ruta a data/raw/matchcenter/ con los parquets de WhoScored.")
    parser.add_argument("--out",              type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    build_features(args.matchcenter_dir, args.season, args.min_minutes, args.out)


if __name__ == "__main__":
    main()
