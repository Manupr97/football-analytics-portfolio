"""
defensive.py — Parser de acciones defensivas y de portero desde df_events.

Dos DataFrames de salida:
  - build_df_defensive_actions(): tackles, interceptions, clearances, blocks,
    ball recoveries, aerials ganados/perdidos.
  - build_df_gk_actions(): saves, claims, punches, sweeper actions del portero.

Coordenadas de salida: escala WhoScored (0–100). La normalización a UEFA
ocurre en storage/loader.py, no aquí.

Uso:

    from ws_platform.parsing.defensive import build_df_defensive_actions, build_df_gk_actions
    df_def = build_df_defensive_actions(df_events)
    df_gk  = build_df_gk_actions(df_events)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Catálogo de tipos de acción defensiva (jugadores de campo)
# ---------------------------------------------------------------------------

# Acciones que siempre son defensivas por su type_name
_DEF_TYPE_NAMES = frozenset({
    "Tackle",
    "Interception",
    "Clearance",
    "BlockedPass",       # bloqueo de pase
    "Save",              # save también puede ser de jugador de campo (line clearance)
    "BallRecovery",
    "Aerial",
    "Challenge",
    "Foul",              # se incluye para análisis de presión; puede filtrarse después
    "Error",
})

# Acciones exclusivas de portero
_GK_TYPE_NAMES = frozenset({
    "Save",
    "Claim",
    "Punch",
    "Keeper Sweeper",
    "KeeperSweeper",
    "KeeperPickup",
    "SavedShot",         # portero para; de cara al gol
})

# Para determinar si una acción defensiva es "high turnover":
# recuperación a ≤ 40m del arco rival (en WS: 40/1.05 ≈ 38.1)
_HIGH_TURNOVER_MIN_X_WS = 61.9   # x ≥ 61.9 → en campo rival (100 - 38.1)

# Acciones de recuperación que pueden ser High Turnover
_RECOVERY_TYPE_NAMES = frozenset({
    "BallRecovery",
    "Interception",
})


# ---------------------------------------------------------------------------
# Helpers de qualifiers
# ---------------------------------------------------------------------------

def _q_has(qualifiers: list, name: str) -> bool:
    return any(
        (q.get("type") or {}).get("displayName") == name
        for q in (qualifiers or [])
    )


def _q_get(qualifiers: list, name: str) -> Any:
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
# Acciones defensivas de jugadores de campo
# ---------------------------------------------------------------------------

def build_df_defensive_actions(df_events: pd.DataFrame) -> pd.DataFrame:
    """
    Extrae las acciones defensivas de jugadores de campo desde df_events.

    Incluye: Tackle, Interception, Clearance, BlockedPass, BallRecovery,
    Aerial, Challenge, Foul, Error.

    Args:
        df_events: DataFrame base devuelto por payload_parser.to_dataframes().
                   Coordenadas en escala WhoScored (0–100).

    Returns:
        DataFrame con una fila por acción defensiva. Columnas principales:
            match_id, event_id, minute, second, expanded_minute, period_value,
            team_id, player_id, x, y,
            type_name, outcome_name,
            is_success,           ← outcome == 'Successful'
            is_tackle,
            is_interception,
            is_clearance,
            is_blocked_pass,
            is_ball_recovery,
            is_aerial,            ← Aerial (ganado o perdido)
            is_aerial_won,        ← Aerial Successful
            is_foul,
            is_high_turnover,     ← recuperación a ≤ 40m del arco rival
            qualifiers
    """
    if df_events is None or df_events.empty:
        log.warning("build_df_defensive_actions_entrada_vacia")
        return pd.DataFrame()

    mask = df_events["type_name"].isin(_DEF_TYPE_NAMES)
    def_actions = df_events[mask].copy()

    if def_actions.empty:
        log.warning("build_df_defensive_sin_acciones", n_events=len(df_events))
        return pd.DataFrame()

    # --- Flags de tipo ---
    def_actions["is_tackle"]       = def_actions["type_name"] == "Tackle"
    def_actions["is_interception"] = def_actions["type_name"] == "Interception"
    def_actions["is_clearance"]    = def_actions["type_name"] == "Clearance"
    def_actions["is_blocked_pass"] = def_actions["type_name"] == "BlockedPass"
    def_actions["is_ball_recovery"]= def_actions["type_name"] == "BallRecovery"
    def_actions["is_aerial"]       = def_actions["type_name"] == "Aerial"
    def_actions["is_foul"]         = def_actions["type_name"] == "Foul"

    # --- is_success ---
    def_actions["is_success"] = def_actions["outcome_name"].apply(
        lambda o: str(o).lower() == "successful"
    )

    # --- is_aerial_won ---
    def_actions["is_aerial_won"] = (
        def_actions["is_aerial"] & def_actions["is_success"]
    )

    # --- is_high_turnover ---
    # Recuperación (BallRecovery o Interception) a ≤ 40m del arco rival,
    # es decir, x ≥ 61.9 en escala WS.
    def_actions["is_high_turnover"] = (
        def_actions["type_name"].isin(_RECOVERY_TYPE_NAMES)
        & def_actions["is_success"]
        & (def_actions["x"].fillna(0) >= _HIGH_TURNOVER_MIN_X_WS)
    )

    # --- Selección y orden de columnas ---
    cols = [
        "match_id", "event_id", "minute", "second", "expanded_minute",
        "period_value", "period_name",
        "team_id", "player_id", "x", "y",
        "type_name", "outcome_name",
        "is_success",
        "is_tackle", "is_interception", "is_clearance",
        "is_blocked_pass", "is_ball_recovery",
        "is_aerial", "is_aerial_won",
        "is_foul",
        "is_high_turnover",
        "qualifiers",
    ]
    def_actions = def_actions.reindex(columns=[c for c in cols if c in def_actions.columns])

    # --- Log de resumen ---
    total        = len(def_actions)
    tackles      = def_actions["is_tackle"].sum()
    interceptions= def_actions["is_interception"].sum()
    clearances   = def_actions["is_clearance"].sum()
    recoveries   = def_actions["is_ball_recovery"].sum()
    aerials      = def_actions["is_aerial"].sum()
    aerials_won  = def_actions["is_aerial_won"].sum()
    high_to      = def_actions["is_high_turnover"].sum()

    log.info(
        "defensive_actions_parseadas",
        match_id=def_actions["match_id"].iloc[0] if total else None,
        total=total,
        tackles=int(tackles),
        interceptions=int(interceptions),
        clearances=int(clearances),
        recoveries=int(recoveries),
        aerials=int(aerials),
        aerials_won=int(aerials_won),
        high_turnovers=int(high_to),
    )

    return def_actions


# ---------------------------------------------------------------------------
# Acciones de portero
# ---------------------------------------------------------------------------

def build_df_gk_actions(df_events: pd.DataFrame) -> pd.DataFrame:
    """
    Extrae las acciones de portero desde df_events.

    Incluye: Save, Claim, Punch, KeeperSweeper, KeeperPickup, SavedShot.
    Las guardadas de jugadores de campo (bloques en la línea) se identifican
    por el qualifier 'GoalMouthY' y se excluyen aquí (pertenecen a def_actions).

    Args:
        df_events: DataFrame base devuelto por payload_parser.to_dataframes().

    Returns:
        DataFrame con una fila por acción de portero. Columnas principales:
            match_id, event_id, minute, second, expanded_minute, period_value,
            team_id, player_id, x, y,
            type_name, outcome_name,
            is_save,
            is_claim,
            is_punch,
            is_sweeper,
            is_save_success,      ← guardó el tiro (outcome Successful)
            goal_mouth_y,         ← posición en portería (WS scale)
            goal_mouth_z,
            qualifiers
    """
    if df_events is None or df_events.empty:
        log.warning("build_df_gk_actions_entrada_vacia")
        return pd.DataFrame()

    mask = df_events["type_name"].isin(_GK_TYPE_NAMES)
    gk_actions = df_events[mask].copy()

    if gk_actions.empty:
        log.warning("build_df_gk_sin_acciones", n_events=len(df_events))
        return pd.DataFrame()

    # --- Flags de tipo ---
    gk_actions["is_save"]    = gk_actions["type_name"].isin({"Save", "SavedShot"})
    gk_actions["is_claim"]   = gk_actions["type_name"] == "Claim"
    gk_actions["is_punch"]   = gk_actions["type_name"] == "Punch"
    gk_actions["is_sweeper"] = gk_actions["type_name"].isin(
        {"Keeper Sweeper", "KeeperSweeper", "KeeperPickup"}
    )

    # --- is_save_success ---
    gk_actions["is_save_success"] = (
        gk_actions["is_save"]
        & gk_actions["outcome_name"].apply(lambda o: str(o).lower() == "successful")
    )

    # --- Coordenadas de portería desde qualifiers ---
    gk_actions["goal_mouth_y"] = gk_actions["qualifiers"].apply(
        lambda qs: _safe_float(_q_get(qs, "GoalMouthY"))
    )
    gk_actions["goal_mouth_z"] = gk_actions["qualifiers"].apply(
        lambda qs: _safe_float(_q_get(qs, "GoalMouthZ"))
    )

    # --- Selección y orden de columnas ---
    cols = [
        "match_id", "event_id", "minute", "second", "expanded_minute",
        "period_value", "period_name",
        "team_id", "player_id", "x", "y",
        "type_name", "outcome_name",
        "is_save", "is_claim", "is_punch", "is_sweeper",
        "is_save_success",
        "goal_mouth_y", "goal_mouth_z",
        "qualifiers",
    ]
    gk_actions = gk_actions.reindex(columns=[c for c in cols if c in gk_actions.columns])

    # --- Log de resumen ---
    total    = len(gk_actions)
    saves    = gk_actions["is_save"].sum()
    claims   = gk_actions["is_claim"].sum()
    punches  = gk_actions["is_punch"].sum()
    sweepers = gk_actions["is_sweeper"].sum()

    log.info(
        "gk_actions_parseadas",
        match_id=gk_actions["match_id"].iloc[0] if total else None,
        total=total,
        saves=int(saves),
        claims=int(claims),
        punches=int(punches),
        sweepers=int(sweepers),
    )

    return gk_actions
