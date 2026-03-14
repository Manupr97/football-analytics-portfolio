"""
payload_parser.py — Extracción del payload de WhoScored y normalización base.

Dos responsabilidades:
  1. load_payload_from_html(html) → dict   — extrae el JSON embebido en el HTML.
  2. to_dataframes(payload) → (df_match, df_players, df_events)  — DataFrames base.

Los DataFrames de esta capa son "raw": coordenadas en escala WhoScored (0–100),
sin flags derivados. La normalización a UEFA (105×68) ocurre en storage/loader.py.

Uso:

    from ws_platform.parsing.payload_parser import load_payload_from_html, to_dataframes

    payload = load_payload_from_html(html_text)
    df_match, df_players, df_events = to_dataframes(payload)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _safe_int(x: Any) -> int | None:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return int(x)
    except Exception:
        try:
            return int(float(str(x)))
        except Exception:
            return None


def _safe_float(x: Any) -> float | None:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return float(x)
    except Exception:
        return None


def _extract_balanced_object(text: str, start_idx: int) -> str:
    """
    Extrae el objeto {...} con llaves balanceadas empezando en start_idx.
    Necesario porque el payload no es JSON puro sino JavaScript embebido.
    """
    i, n = start_idx, len(text)
    depth, in_str, esc = 0, False, False
    quote = None
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str, quote = True, ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start_idx : i + 1]
        i += 1
    raise ValueError("No se pudo balancear llaves de objeto.")


def _extract_balanced_array(text: str, start_idx: int) -> str:
    """Extrae el array [...] con corchetes balanceados empezando en start_idx."""
    i, n = start_idx, len(text)
    depth, in_str, esc = 0, False, False
    quote = None
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str, quote = True, ch
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[start_idx : i + 1]
        i += 1
    raise ValueError("No se pudo balancear corchetes de array.")


# ---------------------------------------------------------------------------
# Extracción del payload desde HTML
# ---------------------------------------------------------------------------

def load_payload_from_html(html: str) -> dict[str, Any]:
    """
    Extrae el payload JSON embebido en el HTML del Match Centre de WhoScored.

    El payload vive en:  require.config.params["args"] = { matchId: ..., matchCentreData: {...}, ... }

    Devuelve un dict con las claves:
        - matchId               (int)
        - matchCentreData       (dict)
        - matchCentreEventType  (dict, opcional)
        - formationIdNameDictionary (dict, opcional)
        - scoreTimelineJson     (list, opcional)
        - formationsTimelineJson (list, opcional)

    Raises:
        ValueError: Si no se puede extraer matchCentreData del HTML.
    """
    payload: dict[str, Any] = {}

    # Patrón principal: require.config.params["args"] = { ... }
    m_args = re.search(r'require\.config\.params\["args"\]\s*=\s*\{', html)
    if m_args:
        args_obj = _extract_balanced_object(html, m_args.end() - 1)

        # matchId
        m_mid = re.search(r"matchId\s*:\s*(\d+)", args_obj)
        if m_mid:
            payload["matchId"] = int(m_mid.group(1))

        # matchCentreData
        m_mcd = re.search(r"matchCentreData\s*:\s*\{", args_obj)
        if m_mcd:
            try:
                raw = _extract_balanced_object(args_obj, m_mcd.end() - 1)
                payload["matchCentreData"] = json.loads(raw)
            except Exception as exc:
                log.warning("payload_mcd_parse_error", error=str(exc), hint="Posible JS no-JSON en matchCentreData")

        # matchCentreEventType (a veces se llama matchCentreEventTypeJson)
        m_evt = re.search(r"matchCentreEventType(?:Json)?\s*:\s*\{", args_obj)
        if m_evt:
            try:
                raw = _extract_balanced_object(args_obj, m_evt.end() - 1)
                payload["matchCentreEventType"] = json.loads(raw)
            except Exception:
                pass

        # formationIdNameDictionary (opcional)
        m_formdict = re.search(r"formationIdNameDictionary\s*:\s*\{", args_obj)
        if m_formdict:
            try:
                raw = _extract_balanced_object(args_obj, m_formdict.end() - 1)
                payload["formationIdNameDictionary"] = json.loads(raw)
            except Exception:
                pass

        # Arrays opcionales: scoreTimelineJson, formationsTimelineJson
        for key in ("scoreTimelineJson", "formationsTimelineJson"):
            m_k = re.search(rf"{key}\s*:\s*\[", args_obj)
            if m_k:
                try:
                    arr = _extract_balanced_array(args_obj, m_k.end() - 1)
                    payload[key] = json.loads(arr)
                except Exception:
                    pass

    # Fallback antiguo: var matchCentreData = {...};
    if "matchCentreData" not in payload:
        m_old = re.search(
            r"var\s+matchCentreData\s*=\s*(\{.*?\});\s*var\s",
            html,
            flags=re.DOTALL,
        )
        if m_old:
            payload["matchCentreData"] = json.loads(m_old.group(1))
            log.warning("payload_extraido_via_fallback_antiguo")

    if "matchCentreData" not in payload:
        raise ValueError(
            "No se pudo extraer matchCentreData del HTML. "
            "WhoScored puede haber cambiado la estructura del payload."
        )

    match_id = payload.get("matchId", "?")
    n_events = len(payload.get("matchCentreData", {}).get("events", []))
    log.info("payload_extraido", match_id=match_id, n_events=n_events)

    return payload


def load_payload_from_file(path: str | Path) -> dict[str, Any]:
    """
    Carga un payload ya guardado en disco (JSON).
    Útil para re-parsear sin volver a scrapear.

    Args:
        path: Ruta al archivo payload.json guardado por el scraper.
    """
    path = Path(path)
    log.info("cargando_payload_desde_archivo", path=str(path))
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Normalización base: payload → DataFrames
# ---------------------------------------------------------------------------

def to_dataframes(
    payload: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Convierte el payload en los tres DataFrames base del pipeline.

    Args:
        payload: Dict extraído de load_payload_from_html() o load_payload_from_file().

    Returns:
        (df_match, df_players, df_events)

        df_match   — 1 fila con metadatos del partido.
        df_players — 1 fila por jugador (ambos equipos combinados).
        df_events  — 1 fila por evento raw. Coordenadas en escala WS (0–100).
                     La normalización a UEFA ocurre en storage/loader.py.
    """
    mcd = payload.get("matchCentreData") or {}
    match_id = payload.get("matchId") or mcd.get("matchId")

    # ------------------------------------------------------------------
    # df_match
    # ------------------------------------------------------------------
    home = mcd.get("home") or {}
    away = mcd.get("away") or {}

    referee = mcd.get("referee")
    referee_name = (
        referee.get("name") if isinstance(referee, dict) else referee
    )

    df_match = pd.DataFrame([{
        "match_id":       match_id,
        "home_team_id":   home.get("teamId"),
        "home_name":      home.get("name"),
        "home_manager":   home.get("managerName"),
        "away_team_id":   away.get("teamId"),
        "away_name":      away.get("name"),
        "away_manager":   away.get("managerName"),
        "venue":          (mcd.get("venueName") or "").strip() or None,
        "attendance":     mcd.get("attendance"),
        "referee":        referee_name,
        # startDate = "YYYY-MM-DDT00:00:00"  → solo la fecha
        # startTime = "YYYY-MM-DDTHH:MM:SS" → solo la hora
        "start_date":     (mcd.get("startDate") or "")[:10] or None,
        "start_time":     (mcd.get("startTime") or "")[11:16] or None,
        "score":          mcd.get("score"),
        "ht_score":       mcd.get("htScore"),
        "ft_score":       mcd.get("ftScore"),
        "status_code":    mcd.get("statusCode"),
        "elapsed":        mcd.get("elapsed"),
        "competition_name": mcd.get("competitionName") or mcd.get("tournamentName"),
        "season_name":    mcd.get("seasonName"),
    }])

    # ------------------------------------------------------------------
    # df_players
    # ------------------------------------------------------------------
    def _extract_players(side: str) -> list[dict]:
        team = mcd.get(side) or {}
        rows = []
        for p in team.get("players") or []:
            # Rating: WS guarda un dict {minuto: valor}, tomamos el último
            stats = p.get("stats") or {}
            ratings = stats.get("ratings") or {}
            rating = None
            if isinstance(ratings, dict) and ratings:
                try:
                    last_key = str(max(int(k) for k in ratings))
                    rating = round(float(ratings[last_key]), 2)
                except Exception:
                    pass

            rows.append({
                "match_id":        match_id,
                "team_side":       side,
                "team_id":         team.get("teamId"),
                "team_name":       team.get("name"),
                "player_id":       p.get("playerId"),
                "player_name":     p.get("name"),
                "is_first_eleven": p.get("isFirstEleven"),
                "position":        p.get("position"),
                "shirt_no":        p.get("shirtNo"),
                "height":          p.get("height"),
                "weight":          p.get("weight"),
                "age":             p.get("age"),
                "rating":          rating,
                "is_man_of_match": p.get("isManOfTheMatch"),
            })
        return rows

    df_players = pd.DataFrame(
        _extract_players("home") + _extract_players("away")
    )

    # ------------------------------------------------------------------
    # df_events
    # ------------------------------------------------------------------
    ev_rows = []
    for ev in mcd.get("events") or []:
        t = ev.get("type") or {}
        o = ev.get("outcomeType") or {}
        period = ev.get("period") or {}

        ev_rows.append({
            "match_id":       match_id,
            "event_id":       ev.get("eventId") or ev.get("id"),
            "minute":         ev.get("minute"),
            "second":         ev.get("second"),
            "expanded_minute": ev.get("expandedMinute"),
            "period_value":   period.get("value"),
            "period_name":    period.get("displayName"),
            "team_id":        ev.get("teamId"),
            "player_id":      ev.get("playerId"),
            # Coordenadas en escala WS (0-100). NO normalizar aquí.
            "x":              _safe_float(ev.get("x")),
            "y":              _safe_float(ev.get("y")),
            "end_x":          _safe_float(ev.get("endX")),
            "end_y":          _safe_float(ev.get("endY")),
            "type_value":     t.get("value"),
            "type_name":      t.get("displayName"),
            "outcome_value":  o.get("value"),
            "outcome_name":   o.get("displayName"),
            "related_event_id": ev.get("relatedEventId"),
            "is_touch":       ev.get("isTouch"),
            # qualifiers se guarda como lista de dicts (→ JSONB en DB)
            "qualifiers":     ev.get("qualifiers") or [],
        })

    df_events = pd.DataFrame(ev_rows)

    log.info(
        "dataframes_construidos",
        match_id=match_id,
        n_players=len(df_players),
        n_events=len(df_events),
    )

    return df_match, df_players, df_events
