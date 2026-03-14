"""
shots.py — Parser de tiros desde df_events.

Extrae todos los eventos de tiro y enriquece con campos derivados:
goal_mouth_y/z, shot_outcome, is_own_goal, related_pass_event_id.

Coordenadas de salida: escala WhoScored (0–100). La normalización a UEFA
ocurre en storage/loader.py, no aquí.

Uso:

    from ws_platform.parsing.shots import build_df_shots
    df_shots = build_df_shots(df_events)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import logging

log = logging.getLogger(__name__)

# Tipos de evento que WhoScored clasifica como tiro
_SHOT_TYPE_NAMES = frozenset({
    "Shot", "Goal", "MissedShots", "SavedShot",
    "ShotOnPost", "BlockedShot", "OwnGoal",
})


# ---------------------------------------------------------------------------
# Helpers de qualifiers
# ---------------------------------------------------------------------------

def _q_has(qualifiers: list, name: str) -> bool:
    """True si el qualifier con ese displayName existe en la lista."""
    return any(
        (q.get("type") or {}).get("displayName") == name
        for q in (qualifiers or [])
    )


def _q_get(qualifiers: list, name: str) -> Any:
    """Devuelve el value del primer qualifier con ese displayName, o None."""
    for q in (qualifiers or []):
        if (q.get("type") or {}).get("displayName") == name:
            return q.get("value")
    return None


def _q_get_any(qualifiers: list, names: frozenset[str]) -> Any:
    """Devuelve el value del primer qualifier cuyo displayName esté en names."""
    for q in (qualifiers or []):
        if (q.get("type") or {}).get("displayName") in names:
            return q.get("value")
    return None


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _safe_int(x: Any) -> int | None:
    try:
        if x is None:
            return None
        return int(x)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Clasificación de tiros
# ---------------------------------------------------------------------------

def _is_shot_row(row: pd.Series) -> bool:
    """
    Determina si una fila de df_events es un tiro.
    WhoScored no siempre usa type_name consistente: también hay tiros
    detectables por la presencia de GoalMouthY o del qualifier ShotType.
    """
    if row.get("type_name") in _SHOT_TYPE_NAMES:
        return True
    qs = row.get("qualifiers") or []
    if _q_get(qs, "GoalMouthY") is not None:
        return True
    if _q_has(qs, "ShotType"):
        return True
    return False


def _shot_outcome(row: pd.Series) -> str:
    """Clasifica el resultado del tiro en una categoría canónica."""
    type_name = str(row.get("type_name") or "")
    outcome = str(row.get("outcome_name") or "")
    qs = row.get("qualifiers") or []

    if type_name == "Goal" or _q_has(qs, "Goal"):
        return "Goal"
    if type_name == "BlockedShot" or _q_has(qs, "BlockedPass"):
        return "Blocked"
    if type_name == "SavedShot" or "Saved" in outcome:
        return "Saved"
    if type_name == "ShotOnPost" or _q_has(qs, "HitWoodWork"):
        return "Post"
    if type_name == "MissedShots" or "Off Target" in outcome or "Missed" in outcome:
        return "Missed"
    return outcome or type_name or "Unknown"


# IDs de qualifiers que pueden contener el event_id del pase relacionado
_RELATED_PASS_Q_NAMES = frozenset({
    "RelatedEventId", "AssistPassId",
    "KeyPass", "Assist", "GoalAssist",
    "IntentionalGoalAssist", "IntentionalAssist",
})


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def build_df_shots(df_events: pd.DataFrame) -> pd.DataFrame:
    """
    Extrae y enriquece los tiros desde df_events.

    Args:
        df_events: DataFrame base devuelto por payload_parser.to_dataframes().
                   Coordenadas en escala WhoScored (0–100).

    Returns:
        DataFrame con una fila por tiro. Columnas principales:
            match_id, event_id, minute, second, expanded_minute, period_value,
            team_id, player_id, x, y,
            type_name, shot_outcome,
            is_own_goal, is_from_interception,
            related_pass_event_id,
            goal_mouth_y, goal_mouth_z,   ← escala WS (0–100), normalizar en loader
            q_length, q_angle,
            qualifiers                    ← lista completa para auditoría
    """
    if df_events is None or df_events.empty:
        log.warning("build_df_shots_entrada_vacia")
        return pd.DataFrame()

    # --- Filtro: solo filas de tiro ---
    mask = df_events.apply(_is_shot_row, axis=1)
    shots = df_events[mask].copy()

    if shots.empty:
        log.warning("build_df_shots_sin_tiros", n_events=len(df_events))
        return pd.DataFrame()

    # --- Outcome canónico ---
    shots["shot_outcome"] = shots.apply(_shot_outcome, axis=1)

    # --- Flags booleanos ---
    shots["is_own_goal"] = shots["qualifiers"].apply(
        lambda qs: _q_has(qs, "OwnGoal")
    )
    shots["is_from_interception"] = shots["qualifiers"].apply(
        lambda qs: _q_has(qs, "InterceptionWin")
    )

    # --- related_pass_event_id ---
    # Solo se considera asistencia válida si el evento relacionado pertenece
    # al mismo equipo que el tiro. WhoScored puede enlazar eventos de equipos
    # rivales (errores, despejes) que técnicamente preceden al gol.
    #
    # Nota: event_id NO es único en df_events (WhoScored puede repetirlos entre
    # equipos). La validación filtra por event_id + team_id del tiro, NO con un
    # mapa indexado por event_id que colapsaría duplicados.

    def _resolve_related(row: pd.Series) -> int | None:
        shot_team   = row.get("team_id")
        shot_minute = row.get("expanded_minute") or row.get("minute") or 999

        def _valid_related(rel_id: int | None) -> int | None:
            """
            Valida que el evento relacionado:
              1. Exista en df_events.
              2. Sea del mismo equipo que el tiro.
              3. Sea anterior o igual en tiempo al tiro (descarta duplicados de
                 event_id que WhoScored asigna al equipo rival en otro momento).
            """
            if rel_id is None:
                return None
            candidates = df_events[
                (df_events["event_id"] == rel_id)
                & (df_events["team_id"] == shot_team)
            ]
            if candidates.empty:
                return None
            # Si hay varios (event_id duplicado), tomamos el que sea anterior al tiro
            col_min = "expanded_minute" if "expanded_minute" in candidates.columns else "minute"
            before = candidates[candidates[col_min] <= shot_minute]
            return rel_id if not before.empty else None

        # 1. Campo directo del evento
        candidate = _valid_related(_safe_int(row.get("related_event_id")))
        if candidate is not None:
            return candidate
        # 2. Fallback: qualifiers
        return _valid_related(
            _safe_int(_q_get_any(row.get("qualifiers") or [], _RELATED_PASS_Q_NAMES))
        )

    shots["related_pass_event_id"] = (
        shots.apply(_resolve_related, axis=1)
        .astype("Int64")
    )

    # --- Coordenadas de portería (escala WS 0–100, normalizar en loader) ---
    shots["goal_mouth_y"] = shots["qualifiers"].apply(
        lambda qs: _safe_float(_q_get(qs, "GoalMouthY"))
    )
    shots["goal_mouth_z"] = shots["qualifiers"].apply(
        lambda qs: _safe_float(_q_get(qs, "GoalMouthZ"))
    )

    # --- Métricas extra de qualifier ---
    shots["q_length"] = shots["qualifiers"].apply(
        lambda qs: _safe_float(_q_get(qs, "Length"))
    )
    shots["q_angle"] = shots["qualifiers"].apply(
        lambda qs: _safe_float(_q_get(qs, "Angle"))
    )

    # --- Selección y orden de columnas ---
    cols = [
        "match_id", "event_id", "minute", "second", "expanded_minute",
        "period_value", "period_name",
        "team_id", "player_id", "x", "y",
        "type_name", "shot_outcome",
        "is_own_goal", "is_from_interception",
        "related_pass_event_id",
        "goal_mouth_y", "goal_mouth_z",
        "q_length", "q_angle",
        "qualifiers",
    ]
    shots = shots.reindex(columns=[c for c in cols if c in shots.columns])

    # --- Log de resumen ---
    total = len(shots)
    linked = shots["related_pass_event_id"].notna().sum()
    goals = (shots["shot_outcome"] == "Goal").sum()
    own_goals = shots["is_own_goal"].sum()

    log.info(
        "shots_parseados",
        match_id=shots["match_id"].iloc[0] if total else None,
        total=total,
        goals=int(goals),
        own_goals=int(own_goals),
        linked_to_pass=int(linked),
        pct_linked=round(linked / total * 100, 1) if total else 0,
    )

    return shots
