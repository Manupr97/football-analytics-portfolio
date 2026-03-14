"""
whoscored_features.py
Fase 1 de enriquecimiento con datos de eventos WhoScored.

Agrega por player_id las siguientes features sobre toda la temporada:

  pct_passes_forward  — % de pases hacia adelante (end_x > x)
  avg_pass_length     — longitud media de pases completados (metros)
  shot_zone_box_pct   — % de tiros desde dentro del área (x > 83)

Fuentes:
  events_passes.parquet  →  pct_passes_forward, avg_pass_length
  events_shots.parquet   →  shot_zone_box_pct

Nota sobre q_length / q_angle en events_shots:
  Estas columnas están 100% nulas en el dataset (confirmado en auditoría).
  La distancia de tiro se calcula desde las coordenadas x/y directas.

Nota sobre la escala de coordenadas WhoScored:
  x: 0 = portería propia, 100 = portería rival
  y: 0 = banda izquierda, 100 = banda derecha
  end_x > x  →  el pase avanza hacia la portería rival (hacia adelante)
  x > 83     →  el tiro se origina dentro del área grande aproximada
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Umbral de coordenada x para considerar un tiro como "dentro del área"
# En la escala WhoScored (0-100), el área grande comienza ~en x=83
SHOT_BOX_THRESHOLD = 83.0


def _read_parquet_safe(path: Path) -> pd.DataFrame | None:
    """
    Lee un archivo parquet de forma segura.
    Devuelve None si el archivo no existe, está vacío o está corrupto.
    """
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        return df if not df.empty else None
    except Exception as e:
        logger.warning(f"No se pudo leer {path}: {e}")
        return None


def _aggregate_passes(passes_df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega eventos de pase por player_id para un partido.

    Devuelve DataFrame con columnas:
      player_id, n_passes, n_forward, length_sum, length_count
    """
    # Excluir filas sin player_id (eventos de equipo, corners sin asignación, etc.)
    df = passes_df.dropna(subset=["player_id"]).copy()
    if df.empty:
        return pd.DataFrame(columns=["player_id", "n_passes", "n_forward",
                                     "length_sum", "length_count"])

    df["player_id"] = df["player_id"].astype(np.int64)

    # Pases hacia adelante: el punto final está más cerca de la portería rival que el origen
    df["is_forward"] = (df["end_x"] > df["x"]).astype(int)

    # Pases completados con longitud válida (para avg_pass_length)
    completed = df[df["is_completed"] == True].copy()
    completed_valid = completed.dropna(subset=["length"])

    # Agregaciones por jugador
    agg_all = df.groupby("player_id").agg(
        n_passes=("is_forward", "count"),
        n_forward=("is_forward", "sum"),
    )

    agg_length = completed_valid.groupby("player_id").agg(
        length_sum=("length", "sum"),
        length_count=("length", "count"),
    )

    result = agg_all.join(agg_length, how="left").reset_index()
    result["length_sum"] = result["length_sum"].fillna(0.0)
    result["length_count"] = result["length_count"].fillna(0).astype(int)

    return result


def _aggregate_shots(shots_df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega eventos de tiro por player_id para un partido.

    Devuelve DataFrame con columnas:
      player_id, n_shots, n_shots_in_box
    """
    df = shots_df.dropna(subset=["player_id"]).copy()
    if df.empty:
        return pd.DataFrame(columns=["player_id", "n_shots", "n_shots_in_box"])

    df["player_id"] = df["player_id"].astype(np.int64)

    # Excluir autogoles (coordenadas en campo propio, sesgarían la distribución)
    df = df[df.get("is_own_goal", False) != True].copy()

    df["is_in_box"] = (df["x"] > SHOT_BOX_THRESHOLD).astype(int)

    result = df.groupby("player_id").agg(
        n_shots=("is_in_box", "count"),
        n_shots_in_box=("is_in_box", "sum"),
    ).reset_index()

    return result


def aggregate_season(
    ws_platform_dir: str | Path,
    leagues: list[str] | None = None,
    season: str = "2025-2026",
) -> pd.DataFrame:
    """
    Recorre recursivamente ws-analytics-platform y agrega las features
    de evento por player_id sobre toda la temporada.

    Parameters
    ----------
    ws_platform_dir : str | Path
        Ruta raíz de ws-analytics-platform.
    leagues : list[str] | None
        Ligas a procesar. Si es None, procesa todas las disponibles.
        Nombres esperados: 'laliga', 'premier_league', 'bundesliga', 'ligue_1', 'serie_a'
    season : str
        Carpeta de temporada (default: '2025-2026').

    Returns
    -------
    pd.DataFrame
        Una fila por player_id con columnas:
          player_id, n_passes, n_forward, length_sum, length_count,
          n_shots, n_shots_in_box
        Listo para calcular los ratios finales con compute_features().
    """
    root = Path(ws_platform_dir) / "data" / "raw" / "matchcenter"
    if not root.exists():
        raise FileNotFoundError(f"Directorio de matchcenter no encontrado: {root}")

    available_leagues = [d.name for d in root.iterdir() if d.is_dir()]
    target_leagues = leagues if leagues is not None else available_leagues

    passes_chunks: list[pd.DataFrame] = []
    shots_chunks: list[pd.DataFrame] = []
    n_matches = 0
    n_errors = 0

    for league in target_leagues:
        season_dir = root / league / season
        if not season_dir.exists():
            logger.warning(f"Liga/temporada no encontrada: {league}/{season}")
            continue

        match_dirs = [d for d in season_dir.iterdir() if d.is_dir()]
        logger.info(f"{league}: {len(match_dirs)} partidos")

        for match_dir in match_dirs:
            parquet_dir = match_dir / "parquet"

            # Passes
            passes_df = _read_parquet_safe(parquet_dir / "events_passes.parquet")
            if passes_df is not None:
                try:
                    passes_chunks.append(_aggregate_passes(passes_df))
                except Exception as e:
                    logger.warning(f"Error en passes {match_dir.name}: {e}")
                    n_errors += 1

            # Shots
            shots_df = _read_parquet_safe(parquet_dir / "events_shots.parquet")
            if shots_df is not None:
                try:
                    shots_chunks.append(_aggregate_shots(shots_df))
                except Exception as e:
                    logger.warning(f"Error en shots {match_dir.name}: {e}")
                    n_errors += 1

            n_matches += 1

    if n_errors > 0:
        logger.warning(f"Total errores de lectura: {n_errors}")

    print(f"Partidos procesados: {n_matches}")
    print(f"Errores de lectura:  {n_errors}")

    if not passes_chunks and not shots_chunks:
        raise RuntimeError("No se encontraron datos de eventos. Revisa la ruta de ws-analytics-platform.")

    # --- Combinar todos los partidos ---
    passes_season = (
        pd.concat(passes_chunks, ignore_index=True)
        .groupby("player_id")
        .agg(
            n_passes=("n_passes", "sum"),
            n_forward=("n_forward", "sum"),
            length_sum=("length_sum", "sum"),
            length_count=("length_count", "sum"),
        )
        .reset_index()
    ) if passes_chunks else pd.DataFrame(columns=["player_id","n_passes","n_forward","length_sum","length_count"])

    shots_season = (
        pd.concat(shots_chunks, ignore_index=True)
        .groupby("player_id")
        .agg(
            n_shots=("n_shots", "sum"),
            n_shots_in_box=("n_shots_in_box", "sum"),
        )
        .reset_index()
    ) if shots_chunks else pd.DataFrame(columns=["player_id","n_shots","n_shots_in_box"])

    season_agg = passes_season.merge(shots_season, on="player_id", how="outer")
    season_agg["player_id"] = season_agg["player_id"].astype(np.int64)

    return season_agg


def compute_features(season_agg: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula los ratios finales a partir de los acumulados por temporada.

    Las divisiones por cero se manejan con np.nan (no con 0),
    para distinguir "no hubo eventos" de "el ratio fue cero".

    Parameters
    ----------
    season_agg : pd.DataFrame
        Output de aggregate_season().

    Returns
    -------
    pd.DataFrame
        Columnas: player_id, pct_passes_forward, avg_pass_length, shot_zone_box_pct
    """
    df = season_agg.copy()

    # pct_passes_forward: % de pases con dirección hacia adelante
    df["pct_passes_forward"] = np.where(
        df["n_passes"] > 0,
        df["n_forward"] / df["n_passes"],
        np.nan,
    )

    # avg_pass_length: longitud media de pases completados (metros)
    df["avg_pass_length"] = np.where(
        df["length_count"] > 0,
        df["length_sum"] / df["length_count"],
        np.nan,
    )

    # shot_zone_box_pct: % de tiros desde dentro del área
    df["shot_zone_box_pct"] = np.where(
        df["n_shots"] > 0,
        df["n_shots_in_box"] / df["n_shots"],
        np.nan,   # jugadores sin ningún tiro → NaN, no 0
    )

    return df[["player_id", "pct_passes_forward", "avg_pass_length", "shot_zone_box_pct"]]
