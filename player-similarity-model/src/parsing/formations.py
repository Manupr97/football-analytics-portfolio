"""
formations.py — Parser de formaciones y marcador desde el payload de WhoScored.

Tres funciones principales:
  - build_formations_timeline(): DataFrame con segmentos de formación por equipo.
  - build_player_positions(): DataFrame con posiciones XY de jugadores por segmento.
  - build_score_timeline(): DataFrame de goles ordenados cronológicamente.

Las coordenadas de posición (vertical/horizontal) son relativas al sistema
propio de WhoScored para las formaciones, NO en escala 0–100 de eventos.
No se normalizan a UEFA porque son posiciones de esquema táctico, no de campo.

Uso:

    from ws_platform.parsing.formations import (
        build_formations_timeline,
        build_player_positions,
        build_score_timeline,
    )

    df_formations = build_formations_timeline(payload)
    df_positions  = build_player_positions(payload)
    df_score      = build_score_timeline(payload)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import logging

log = logging.getLogger(__name__)

# Valor que WhoScored usa para el primer período (incluye pre-partido)
_PERIOD_FIRST_HALF = 16
_PERIOD_SECOND_HALF = 2


def _safe_int(x: Any) -> int | None:
    try:
        if x is None:
            return None
        return int(x)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Formaciones timeline
# ---------------------------------------------------------------------------

def build_formations_timeline(payload: dict[str, Any]) -> pd.DataFrame:
    """
    Extrae la línea temporal de formaciones de ambos equipos.

    Cada fila representa un segmento de formación: el período de tiempo
    durante el que un equipo mantuvo una formación concreta y una alineación
    concreta (puede cambiar con sustituciones sin cambiar la formación).

    Args:
        payload: Dict extraído de load_payload_from_html() o load_payload_from_file().

    Returns:
        DataFrame con columnas:
            match_id, team_id, team_side,
            formation_id, formation_name,
            period_value,
            start_minute, end_minute,
            captain_player_id,
            player_ids,         ← lista de player_id (todos en la plantilla de ese segmento)
            starting_xi,        ← lista de los 11 titulares del segmento (slots 1–11)
            jersey_numbers,     ← lista de dorsales (alineada con player_ids)
    """
    mcd = payload.get("matchCentreData") or {}
    match_id = payload.get("matchId") or mcd.get("matchId")

    rows = []
    for side in ("home", "away"):
        team = mcd.get(side) or {}
        team_id = team.get("teamId")
        formations = team.get("formations") or []

        for f in formations:
            player_ids = f.get("playerIds") or []
            slots      = f.get("formationSlots") or []

            # Los titulares son los playerIds cuyos slots ∈ 1–11
            starting_xi = [
                pid for pid, slot in zip(player_ids, slots)
                if slot is not None and 1 <= int(slot) <= 11
            ]

            rows.append({
                "match_id":          match_id,
                "team_id":           team_id,
                "team_side":         side,
                "formation_id":      f.get("formationId"),
                "formation_name":    f.get("formationName"),
                "period_value":      f.get("period"),
                "start_minute":      f.get("startMinuteExpanded"),
                "end_minute":        f.get("endMinuteExpanded"),
                "captain_player_id": f.get("captainPlayerId"),
                "player_ids":        player_ids,
                "starting_xi":       starting_xi,
                "jersey_numbers":    f.get("jerseyNumbers") or [],
            })

    if not rows:
        log.warning("build_formations_sin_datos", match_id=match_id)
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Estadísticas de log
    n_home = (df["team_side"] == "home").sum()
    n_away = (df["team_side"] == "away").sum()
    log.info(
        "formations_parseadas",
        match_id=match_id,
        segmentos_home=int(n_home),
        segmentos_away=int(n_away),
    )

    return df


# ---------------------------------------------------------------------------
# Posiciones XY por jugador y segmento
# ---------------------------------------------------------------------------

def build_player_positions(payload: dict[str, Any]) -> pd.DataFrame:
    """
    Extrae las posiciones tácticas (vertical/horizontal) de cada jugador
    en cada segmento de formación.

    Las posiciones son relativas al esquema táctico de WhoScored, NO coordenadas
    de campo en escala 0–100. Se usan para dibujar diagramas de formación.

    Args:
        payload: Dict del payload de WhoScored.

    Returns:
        DataFrame con columnas:
            match_id, team_id, team_side,
            formation_name, period_value, start_minute, end_minute,
            slot,               ← posición en el esquema (1=GK, 2–11=campo)
            player_id,
            vertical,           ← eje Y del esquema (0=abajo, 10=arriba)
            horizontal,         ← eje X del esquema (0=izq, 10=der)
    """
    mcd = payload.get("matchCentreData") or {}
    match_id = payload.get("matchId") or mcd.get("matchId")

    rows = []
    for side in ("home", "away"):
        team    = mcd.get(side) or {}
        team_id = team.get("teamId")

        for f in team.get("formations") or []:
            player_ids  = f.get("playerIds") or []
            slots       = f.get("formationSlots") or []
            positions   = f.get("formationPositions") or []
            fname       = f.get("formationName")
            period_val  = f.get("period")
            start_min   = f.get("startMinuteExpanded")
            end_min     = f.get("endMinuteExpanded")

            # formationPositions tiene una entrada por slot activo (1–11),
            # y player_ids / formationSlots tienen una entrada por jugador en la plantilla.
            # Alineamos por índice de slot activo.
            slot_idx = 0
            for pid, slot in zip(player_ids, slots):
                if slot is None:
                    continue
                slot_int = int(slot)
                if slot_int < 1 or slot_int > 11:
                    continue
                # Accedemos a la posición por el orden de aparición de slots activos
                pos = positions[slot_idx] if slot_idx < len(positions) else {}
                rows.append({
                    "match_id":      match_id,
                    "team_id":       team_id,
                    "team_side":     side,
                    "formation_name":fname,
                    "period_value":  period_val,
                    "start_minute":  start_min,
                    "end_minute":    end_min,
                    "slot":          slot_int,
                    "player_id":     pid,
                    "vertical":      pos.get("vertical"),
                    "horizontal":    pos.get("horizontal"),
                })
                slot_idx += 1

    if not rows:
        log.warning("build_player_positions_sin_datos", match_id=match_id)
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    log.info(
        "player_positions_parseadas",
        match_id=match_id,
        total_filas=len(df),
    )

    return df


# ---------------------------------------------------------------------------
# Score timeline (goles)
# ---------------------------------------------------------------------------

def build_score_timeline(payload: dict[str, Any]) -> pd.DataFrame:
    """
    Construye la línea temporal de goles del partido.

    Extrae los eventos de tipo Goal (incluyendo own goals) de los
    incidentEvents de ambos equipos y los ordena cronológicamente.

    Args:
        payload: Dict del payload de WhoScored.

    Returns:
        DataFrame con columnas:
            match_id, event_id, minute, expanded_minute, second, period_value,
            team_id, player_id,
            is_own_goal,
            home_score,   ← marcador del equipo local TRAS este gol
            away_score,   ← marcador del equipo visitante TRAS este gol
        Ordenado por expanded_minute, second (ascendente).
    """
    mcd = payload.get("matchCentreData") or {}
    match_id = payload.get("matchId") or mcd.get("matchId")

    home_team_id = (mcd.get("home") or {}).get("teamId")
    away_team_id = (mcd.get("away") or {}).get("teamId")

    # Recopilar todos los eventos de gol de incidentEvents de ambos equipos.
    # incidentEvents puede tener duplicados entre home y away; usamos event_id como dedup.
    seen_event_ids: set[int] = set()
    goal_rows = []

    for side in ("home", "away"):
        team = mcd.get(side) or {}
        for ev in team.get("incidentEvents") or []:
            ev_type = (ev.get("type") or {}).get("displayName", "")
            if ev_type != "Goal":
                continue

            eid = ev.get("eventId")
            if eid in seen_event_ids:
                continue
            seen_event_ids.add(eid)

            qs = ev.get("qualifiers") or []
            is_own_goal = any(
                (q.get("type") or {}).get("displayName") == "OwnGoal"
                for q in qs
            )

            goal_rows.append({
                "match_id":       match_id,
                "event_id":       eid,
                "minute":         ev.get("minute"),
                "second":         ev.get("second", 0),
                "expanded_minute":ev.get("expandedMinute"),
                "period_value":   (ev.get("period") or {}).get("value"),
                "team_id":        ev.get("teamId"),
                "player_id":      ev.get("playerId"),
                "is_own_goal":    is_own_goal,
            })

    if not goal_rows:
        log.warning("build_score_timeline_sin_goles", match_id=match_id)
        return pd.DataFrame()

    df = pd.DataFrame(goal_rows).sort_values(
        ["expanded_minute", "second"], ignore_index=True
    )

    # Calcular marcador acumulado tras cada gol
    home_score = 0
    away_score = 0
    home_scores, away_scores = [], []

    for _, row in df.iterrows():
        team_id    = row["team_id"]
        is_own     = row["is_own_goal"]

        # Un own goal suma al equipo contrario
        if is_own:
            if team_id == home_team_id:
                away_score += 1
            else:
                home_score += 1
        else:
            if team_id == home_team_id:
                home_score += 1
            else:
                away_score += 1

        home_scores.append(home_score)
        away_scores.append(away_score)

    df["home_score"] = home_scores
    df["away_score"] = away_scores

    log.info(
        "score_timeline_construida",
        match_id=match_id,
        total_goles=len(df),
        resultado_final=f"{home_score}-{away_score}",
    )

    return df
