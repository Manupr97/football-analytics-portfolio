"""
passes.py — Parser de pases desde df_events.

Extrae todos los eventos de pase y enriquece con campos derivados:
end_x/end_y reales (desde qualifiers PassEndX/PassEndY), flags is_key_pass,
is_assist, is_cross, is_throughball, is_progressive, switch, corner_taken,
free_kick_taken, y longitud/ángulo de cada pase.

Coordenadas de salida: escala WhoScored (0–100). La normalización a UEFA
ocurre en storage/loader.py, no aquí.

Uso:

    from ws_platform.parsing.passes import build_df_passes_enriched
    df_passes = build_df_passes_enriched(df_events)
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

import logging

log = logging.getLogger(__name__)

# Tipos de evento que WhoScored clasifica como pase
_PASS_TYPE_NAMES = frozenset({
    "Pass", "OffsidPass",
})

# Qualifiers que indican que fue asistencia de gol
_ASSIST_Q_NAMES = frozenset({
    "GoalAssist", "Assist",
    "IntentionalGoalAssist", "IntentionalAssist",
})

# Qualifiers que indican pase clave (generó oportunidad sin resultar en gol)
_KEY_PASS_Q_NAMES = frozenset({
    "KeyPass",
})


# ---------------------------------------------------------------------------
# Helpers de qualifiers (mismos patrones que shots.py)
# ---------------------------------------------------------------------------

def _q_has(qualifiers: list, name: str) -> bool:
    """True si el qualifier con ese displayName existe en la lista."""
    return any(
        (q.get("type") or {}).get("displayName") == name
        for q in (qualifiers or [])
    )


def _q_has_any(qualifiers: list, names: frozenset[str]) -> bool:
    """True si algún qualifier tiene su displayName en names."""
    return any(
        (q.get("type") or {}).get("displayName") in names
        for q in (qualifiers or [])
    )


def _q_get(qualifiers: list, name: str) -> Any:
    """Devuelve el value del primer qualifier con ese displayName, o None."""
    for q in (qualifiers or []):
        if (q.get("type") or {}).get("displayName") == name:
            return q.get("value")
    return None


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cálculo de longitud y ángulo
# ---------------------------------------------------------------------------

def _pass_length(x: float | None, y: float | None,
                 end_x: float | None, end_y: float | None) -> float | None:
    """Longitud del pase en escala WS (0–100). Euclidiana."""
    if any(v is None for v in (x, y, end_x, end_y)):
        return None
    try:
        return math.sqrt((end_x - x) ** 2 + (end_y - y) ** 2)
    except Exception:
        return None


def _pass_angle(x: float | None, y: float | None,
                end_x: float | None, end_y: float | None) -> float | None:
    """
    Ángulo del pase en grados, medido desde el eje positivo X (hacia adelante).
    Rango: (-180, 180]. Positivo = hacia la izquierda del campo (y creciente).
    """
    if any(v is None for v in (x, y, end_x, end_y)):
        return None
    try:
        return math.degrees(math.atan2(end_y - y, end_x - x))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pase progresivo
# ---------------------------------------------------------------------------

# Umbral de reducción de distancia al arco rival (en escala WS 0–100).
# En UEFA: 9.11m. Conversión: 9.11/1.05 ≈ 8.68 en WS.
_PROGRESSIVE_MIN_REDUCTION_WS = 8.68

# Centro del arco rival en escala WS (x=100, y=50)
_GOAL_X_WS = 100.0
_GOAL_Y_WS = 50.0

# x mínima de origen para considerarse pase progresivo (no en tercio defensivo).
# En UEFA: x < 35m → en WS: 35/1.05 ≈ 33.33
_PROGRESSIVE_MIN_X_WS = 33.33


def _is_progressive(
    x: float | None, y: float | None,
    end_x: float | None, end_y: float | None,
    qs: list,
) -> bool:
    """
    True si el pase es progresivo según la definición del proyecto:
      - Reduce distancia al centro del arco rival ≥ 9.11m (8.68 en WS).
      - No empieza en el tercio defensivo (x_ws < 33.33).
      - No es corner ni falta directa.
    """
    if any(v is None for v in (x, y, end_x, end_y)):
        return False
    if x < _PROGRESSIVE_MIN_X_WS:
        return False
    if _q_has(qs, "CornerTaken") or _q_has(qs, "FreekickTaken"):
        return False

    dist_origin = math.sqrt((_GOAL_X_WS - x) ** 2 + (_GOAL_Y_WS - y) ** 2)
    dist_dest   = math.sqrt((_GOAL_X_WS - end_x) ** 2 + (_GOAL_Y_WS - end_y) ** 2)
    return (dist_origin - dist_dest) >= _PROGRESSIVE_MIN_REDUCTION_WS


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def build_df_passes_enriched(df_events: pd.DataFrame) -> pd.DataFrame:
    """
    Extrae y enriquece los pases desde df_events.

    Args:
        df_events: DataFrame base devuelto por payload_parser.to_dataframes().
                   Coordenadas en escala WhoScored (0–100).

    Returns:
        DataFrame con una fila por pase. Columnas principales:
            match_id, event_id, minute, second, expanded_minute, period_value,
            team_id, player_id, x, y,
            end_x, end_y,               ← desde qualifiers PassEndX/PassEndY
            length, angle,              ← calculados en WS scale
            outcome_name,
            is_completed,
            is_key_pass, is_assist,
            is_cross, is_throughball,
            is_progressive,
            is_switch,
            is_corner, is_freekick,
            is_offside_pass,
            receiver_player_id,         ← qualifier PassRecipientId (cuando existe)
            qualifiers                  ← lista completa para auditoría
    """
    if df_events is None or df_events.empty:
        log.warning("build_df_passes_entrada_vacia")
        return pd.DataFrame()

    # --- Filtro: solo filas de pase ---
    mask = df_events["type_name"].isin(_PASS_TYPE_NAMES)
    passes = df_events[mask].copy()

    if passes.empty:
        log.warning("build_df_passes_sin_pases", n_events=len(df_events))
        return pd.DataFrame()

    # --- end_x / end_y desde qualifiers (PassEndX / PassEndY) ---
    # Los campos end_x/end_y del evento están mayoritariamente vacíos.
    passes["end_x"] = passes["qualifiers"].apply(
        lambda qs: _safe_float(_q_get(qs, "PassEndX"))
    )
    passes["end_y"] = passes["qualifiers"].apply(
        lambda qs: _safe_float(_q_get(qs, "PassEndY"))
    )

    # Fallback: usar end_x/end_y del evento base si el qualifier está vacío
    # (en algunos payloads más recientes WS los rellena directamente)
    if "end_x" in df_events.columns:
        no_endx = passes["end_x"].isna()
        if no_endx.any():
            passes.loc[no_endx, "end_x"] = passes.loc[no_endx, "end_x"].fillna(
                passes.loc[no_endx, df_events.columns.get_loc("end_x") if "end_x" in df_events.columns else "end_x"]
            )

    # --- Longitud y ángulo ---
    passes["length"] = passes.apply(
        lambda r: _pass_length(r["x"], r["y"], r["end_x"], r["end_y"]), axis=1
    )
    passes["angle"] = passes.apply(
        lambda r: _pass_angle(r["x"], r["y"], r["end_x"], r["end_y"]), axis=1
    )

    # --- is_completed ---
    passes["is_completed"] = passes["outcome_name"].apply(
        lambda o: str(o).lower() == "successful"
    )

    # --- Flags desde qualifiers ---
    passes["is_key_pass"] = passes["qualifiers"].apply(
        lambda qs: _q_has_any(qs, _KEY_PASS_Q_NAMES)
    )
    passes["is_assist"] = passes["qualifiers"].apply(
        lambda qs: _q_has_any(qs, _ASSIST_Q_NAMES)
    )
    passes["is_cross"] = passes["qualifiers"].apply(
        lambda qs: _q_has(qs, "Cross")
    )
    passes["is_throughball"] = passes["qualifiers"].apply(
        lambda qs: _q_has(qs, "Throughball")
    )
    passes["is_switch"] = passes["qualifiers"].apply(
        lambda qs: _q_has(qs, "Chipped") or _q_has(qs, "LongBall")
    )
    passes["is_corner"] = passes["qualifiers"].apply(
        lambda qs: _q_has(qs, "CornerTaken")
    )
    passes["is_freekick"] = passes["qualifiers"].apply(
        lambda qs: _q_has(qs, "FreekickTaken")
    )
    passes["is_offside_pass"] = passes["type_name"] == "OffsidPass"

    # --- is_progressive ---
    passes["is_progressive"] = passes.apply(
        lambda r: _is_progressive(
            r["x"], r["y"], r["end_x"], r["end_y"], r["qualifiers"]
        ),
        axis=1,
    )

    # --- Receptor del pase ---
    passes["receiver_player_id"] = passes["qualifiers"].apply(
        lambda qs: _safe_float(_q_get(qs, "PassRecipientId"))
    )
    # Convertir a Int64 nullable
    passes["receiver_player_id"] = pd.array(
        passes["receiver_player_id"].tolist(), dtype="Int64"
    )

    # --- Selección y orden de columnas ---
    cols = [
        "match_id", "event_id", "minute", "second", "expanded_minute",
        "period_value", "period_name",
        "team_id", "player_id",
        "x", "y", "end_x", "end_y",
        "length", "angle",
        "type_name", "outcome_name",
        "is_completed",
        "is_key_pass", "is_assist",
        "is_cross", "is_throughball",
        "is_progressive",
        "is_switch",
        "is_corner", "is_freekick",
        "is_offside_pass",
        "receiver_player_id",
        "qualifiers",
    ]
    passes = passes.reindex(columns=[c for c in cols if c in passes.columns])

    # --- Log de resumen ---
    total       = len(passes)
    completed   = passes["is_completed"].sum()
    key_passes  = passes["is_key_pass"].sum()
    assists     = passes["is_assist"].sum()
    progressive = passes["is_progressive"].sum()
    crosses     = passes["is_cross"].sum()
    no_end_xy   = passes["end_x"].isna().sum()

    log.info(
        "passes_parseados",
        match_id=passes["match_id"].iloc[0] if total else None,
        total=total,
        completed=int(completed),
        pct_completed=round(completed / total * 100, 1) if total else 0,
        key_passes=int(key_passes),
        assists=int(assists),
        progressive=int(progressive),
        crosses=int(crosses),
        sin_end_xy=int(no_end_xy),
    )

    return passes
