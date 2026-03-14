# -*- coding: utf-8 -*-
"""
whoscored_matchcenter_v2.py
Port fiel del flujo del notebook (match-centre) a módulo .py
- Payload robusto desde HTML (require.config.params["args"])
- Normalización: match, players, events
- Tiros (+ GoalMouthY/Z, related_pass_eventId), Pases enriquecidos (teamId,eventId)
- Defensive & GK actions (incluye gk_goal_mouth_y/z)
- Formations & player-positions timeline (con jersey numbers)
- Score timeline (desde goles reales) + merge con formations (scored)
- Guardado JSON/CSV + manifest, estructura de carpetas legible
CLI:
  python whoscored_matchcenter_v2.py --url https://es.whoscored.com/matches/1913916/live ...
  python whoscored_matchcenter_v2.py --match-id 1913916
  python whoscored_matchcenter_v2.py --from-csv fixtures.csv
"""
from __future__ import annotations
import random
import time as _time
import re, json, time, hashlib, argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import pandas as pd
from bs4 import BeautifulSoup
# === NUEVO: Selenium para renderizar y aceptar cookies ===
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from .paths import MATCHCENTER_DIR as MATCHCENTER_BASE_DIR


def _build_driver(headless: bool = True, user_agent: str = None):
    opts = ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--lang=es-ES")
    if user_agent:
        opts.add_argument(f"--user-agent={user_agent}")
    # ayuda contra bloqueos triviales
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

def _try_accept_cookies(driver, timeout=8):
    try:
        # Banner típico de Quantcast en WhoScored ES
        # Botones suelen vivir en .qc-cmp2-summary-buttons
        WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".qc-cmp2-summary-buttons button"))
        )
        buttons = driver.find_elements(By.CSS_SELECTOR, ".qc-cmp2-summary-buttons button")
        # heurística: clic al botón con texto tipo "Acepto", "Aceptar", "Agree", "Consent"
        for b in buttons:
            t = (b.text or "").strip().lower()
            if any(k in t for k in ["acepto", "aceptar", "agree", "accept", "consent"]):
                b.click()
                break
    except Exception:
        # si no aparece, seguimos
        pass

def get_html_via_selenium(url: str, driver=None, headless: bool = True, timeout: int = 20, user_agent: str = None) -> str:
    """Si pasas driver, se reutiliza y NO se cierra aquí. Si no, se crea y se cierra."""
    own_driver = False
    if driver is None:
        driver = _build_driver(headless=headless, user_agent=user_agent)
        own_driver = True
    try:
        driver.get(url)
        _try_accept_cookies(driver, timeout=8)

        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#match-header"))
        )
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//script[contains(., 'require.config.params[\"args\"]')]"))
        )
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        return driver.page_source
    finally:
        if own_driver:
            driver.quit()

# ==============================
# Utilidades básicas
# ==============================

def _safe_int(x) -> Optional[int]:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return int(x)
    except Exception:
        try:
            return int(float(str(x)))
        except Exception:
            return None

def _safe_float(x) -> Optional[float]:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return float(x)
    except Exception:
        return None

def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def _slug(s: str) -> str:
    s = s or ""
    s = s.replace(" ", "_").replace("/", "-").replace("\\", "-")
    s = re.sub(r"[^A-Za-z0-9_\-áéíóúÁÉÍÓÚñÑ]+", "", s)
    return s[:80]

def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def _sha1_of_file(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _jsonify_cell(v):
    if isinstance(v, (list, dict)):
        try:
            return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return str(v)
    return v

# ==============================
# Carga de HTML y payload
# ==============================

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def _extract_balanced_object(text: str, start_idx: int) -> str:
    """Extrae objeto {...} con llaves balanceadas empezando en start_idx."""
    i, n = start_idx, len(text)
    depth, in_str, esc = 0, False, False
    quote = None
    while i < n:
        ch = text[i]
        if in_str:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == quote: in_str = False
        else:
            if ch == '"' or ch == "'":
                in_str, quote = True, ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start_idx:i+1]
        i += 1
    raise ValueError("No se pudo balancear llaves de objeto.")

def load_payload_from_html_text(html: str) -> Dict[str, Any]:
    """
    Busca require.config.params["args"] = { ... } y devuelve dict con:
      - matchCentreData
      - matchCentreEventType  (normaliza si aparece como matchCentreEventTypeJson)
      - matchId
      - formationIdNameDictionary (si existiera)
      - scoreTimelineJson / formationsTimelineJson (si existieran embebidos)
    Fallback antiguo: var matchCentreData = {...}
    """
    payload: Dict[str, Any] = {}

    m_args = re.search(r'require\.config\.params\["args"\]\s*=\s*\{', html)
    if m_args:
        args_obj = _extract_balanced_object(html, m_args.end()-1)
        # matchId
        m_mid = re.search(r"matchId\s*:\s*(\d+)", args_obj)
        if m_mid:
            payload["matchId"] = int(m_mid.group(1))
        # matchCentreData
        m_mcd = re.search(r"matchCentreData\s*:\s*\{", args_obj)
        if m_mcd:
            raw = _extract_balanced_object(args_obj, m_mcd.end()-1)
            payload["matchCentreData"] = json.loads(raw)
        # event types
        m_evt = re.search(r"matchCentreEventType(Json)?\s*:\s*\{", args_obj)
        if m_evt:
            raw = _extract_balanced_object(args_obj, m_evt.end()-1)
            payload["matchCentreEventType"] = json.loads(raw)
        # formations dict (si existiera)
        m_formdict = re.search(r"formationIdNameDictionary\s*:\s*\{", args_obj)
        if m_formdict:
            raw = _extract_balanced_object(args_obj, m_formdict.end()-1)
            payload["formationIdNameDictionary"] = json.loads(raw)
        # timelines (si WS los expone)
        for key in ("scoreTimelineJson","formationsTimelineJson"):
            m_k = re.search(rf"{key}\s*:\s*\[", args_obj)
            if m_k:
                # extraer array balanceado [...]
                # (aprovechamos que el array no tiene llaves internas profundas)
                # más simple: cortar hasta el cierre del primer ']'
                i = m_k.end()-1
                depth, in_str, esc, quote = 0, False, False, None
                j = i
                while j < len(args_obj):
                    ch = args_obj[j]
                    if in_str:
                        if esc: esc = False
                        elif ch == "\\": esc = True
                        elif ch == quote: in_str = False
                    else:
                        if ch in ('"', "'"): in_str, quote = True, ch
                        elif ch == "[": depth += 1
                        elif ch == "]":
                            depth -= 1
                            if depth == 0:
                                arr = args_obj[i:j+1]
                                try:
                                    payload[key] = json.loads(arr)
                                except Exception:
                                    pass
                                break
                    j += 1

    # Fallback muy antiguo:
    if "matchCentreData" not in payload:
        m_old = re.search(r"var\s+matchCentreData\s*=\s*(\{.*?\});\s*var\s", html, flags=re.DOTALL)
        if m_old:
            payload["matchCentreData"] = json.loads(m_old.group(1))

    return payload

# ==============================
# Normalización base (match / players / events)
# ==============================

def to_dataframes(payload: Dict[str, Any]) -> Tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    mcd = payload.get("matchCentreData") or {}
    match_id = payload.get("matchId") or mcd.get("matchId")

    # match
    home = mcd.get("home") or {}
    away = mcd.get("away") or {}
    status = mcd.get("status") or {}

    row = {
        "match_id": match_id,
        "home_team_id": home.get("teamId"),
        "home_name": home.get("name"),
        "home_manager": home.get("managerName"),
        "away_team_id": away.get("teamId"),
        "away_name": away.get("name"),
        "away_manager": away.get("managerName"),
        "venue": (mcd.get("venueName") or "").strip() or None,
        "attendance": mcd.get("attendance"),
        "referee": (mcd.get("referee") or {}).get("name") if isinstance(mcd.get("referee"), dict) else mcd.get("referee"),
        "start_time": mcd.get("startTime"),
        "elapsed": status.get("displayStatus") or mcd.get("elapsed"),
        "score": mcd.get("score"),
        "ht_score": mcd.get("htScore"),
        "ft_score": mcd.get("ftScore"),
        "status_code": status.get("value") or mcd.get("statusCode"),
    }
    df_match = pd.DataFrame([row])

    # players
    def _players(side):
        T = mcd.get(side) or {}
        rows = []
        for p in (T.get("players") or []):
            stats = p.get("stats") or {}
            rating = None
            ratings = stats.get("ratings") or {}
            if isinstance(ratings, dict) and ratings:
                try:
                    keys = [int(k) for k in ratings.keys()]
                    last = str(max(keys))
                    rating = round(float(ratings.get(last)), 2)
                except Exception:
                    rating = None
            rows.append({
                "match_id": match_id,
                "team_side": side,
                "team_id": T.get("teamId"),
                "team_name": T.get("name"),
                "player_id": p.get("playerId"),
                "player_name": p.get("name"),
                "isFirstEleven": p.get("isFirstEleven"),
                "position": p.get("position"),
                "shirtNo": p.get("shirtNo"),
                "height": p.get("height"),
                "weight": p.get("weight"),
                "age": p.get("age"),
                "rating": rating,
                "isManOfTheMatch": p.get("isManOfTheMatch"),
            })
        return rows
    df_players = pd.DataFrame(_players("home") + _players("away"))

    # events
    ev_rows = []
    for ev in (mcd.get("events") or []):
        t = ev.get("type") or {}
        o = ev.get("outcomeType") or {}
        ev_rows.append({
            "match_id": match_id,
            "eventId": ev.get("eventId") or ev.get("id"),
            "minute": ev.get("minute"),
            "second": ev.get("second"),
            "expandedMinute": ev.get("expandedMinute"),
            "period": (ev.get("period") or {}).get("value"),
            "teamId": ev.get("teamId"),
            "playerId": ev.get("playerId"),
            "x": ev.get("x"),
            "y": ev.get("y"),
            "endX": ev.get("endX"),
            "endY": ev.get("endY"),
            "typeValue": t.get("value"),
            "typeName": t.get("displayName"),
            "outcomeValue": o.get("value"),
            "outcomeName": o.get("displayName"),
            "relatedEventId": ev.get("relatedEventId"),
            "qualifiers": ev.get("qualifiers"),
        })
    df_events = pd.DataFrame(ev_rows)

    return df_match, df_players, df_events

# ==============================
# Extractores de qualifiers
# ==============================

def _q_has(qs, name: str) -> bool:
    return any(((q.get("type") or {}).get("displayName") == name) for q in (qs or []))

def _q_get(qs, name: str):
    for q in (qs or []):
        t = q.get("type") or {}
        if t.get("displayName") == name:
            return q.get("value")
    return None

def _q_get_any(qs, names: set[str]):
    for q in (qs or []):
        t = q.get("type") or {}
        if t.get("displayName") in names:
            return q.get("value")
    return None

# ==============================
# Tiros, Pases, Defensa, Porteros
# ==============================

# Heurística de tipos de tiro (WS varía nombres según outcome)
_SHOT_TYPES = {
    "Shot","Goal","MissedShots","SavedShot","ShotOnPost","BlockedShot","OwnGoal"
}

def build_df_shots(df_events: pd.DataFrame) -> pd.DataFrame:
    """Versión mejorada que detecta autogoles correctamente"""
    if df_events is None or df_events.empty: 
        return pd.DataFrame()

    def is_shot_row(row) -> bool:
        if str(row.get("typeName")) in _SHOT_TYPES:
            return True
        qs = row.get("qualifiers")
        if _q_get(qs, "GoalMouthY") is not None or _q_get(qs, "GoalMouthZ") is not None:
            return True
        if _q_has(qs, "ShotType"):
            return True
        return False

    shots = df_events[df_events.apply(is_shot_row, axis=1)].copy()

    def shot_outcome(row):
        t = str(row.get("typeName"))
        out = str(row.get("outcomeName") or "")
        qs = row.get("qualifiers")
        if t == "Goal" or _q_has(qs, "Goal"): 
            return "Goal"
        if t == "BlockedShot" or _q_has(qs, "BlockedPass"): 
            return "Blocked"
        if t == "SavedShot" or "Saved" in out:
            return "Saved"
        if t == "ShotOnPost" or _q_has(qs, "HitWoodWork"):
            return "Post"
        if t == "MissedShots" or "Off Target" in out or "Missed" in out:
            return "Missed"
        return out or t or "Unknown"

    shots["shot_outcome"] = shots.apply(shot_outcome, axis=1)
    
    # MEJORA: Detectar autogoles más robustamente
    shots["is_own_goal"] = shots["qualifiers"].apply(lambda qs: _q_has(qs, "OwnGoal"))
    
    # NUEVO: Detectar si el tiro viene de una interceptación rival
    shots["is_from_interception"] = shots["qualifiers"].apply(lambda qs: _q_has(qs, "InterceptionWin"))

    # related_pass_eventId con fallback mejorado
    shots["related_pass_eventId"] = shots.get("relatedEventId")
    if "related_pass_eventId" in shots.columns:
        shots["related_pass_eventId"] = shots["related_pass_eventId"].astype("Int64")

    mask_missing = shots["related_pass_eventId"].isna()
    if mask_missing.any():
        shots.loc[mask_missing, "related_pass_eventId"] = shots.loc[mask_missing, "qualifiers"].apply(
            lambda qs: _safe_int(_q_get_any(qs, {
                "RelatedEventId",
                "AssistPassId", 
                "KeyPass","Assist","GoalAssist","IntentionalGoalAssist","IntentionalAssist"
            }))
        ).astype("Int64")

    # Goal mouth coordinates
    shots["goal_mouth_y"] = shots["qualifiers"].apply(lambda qs: _safe_float(_q_get(qs, "GoalMouthY")))
    shots["goal_mouth_z"] = shots["qualifiers"].apply(lambda qs: _safe_float(_q_get(qs, "GoalMouthZ")))
    shots["q_length"] = shots["qualifiers"].apply(lambda qs: _q_get(qs, "Length"))
    shots["q_angle"]  = shots["qualifiers"].apply(lambda qs: _q_get(qs, "Angle"))

    # Estadísticas de verificación
    linked_shots = shots["related_pass_eventId"].notna().sum()
    total_shots = len(shots)
    own_goals = shots["is_own_goal"].sum()
    print(f"📊 Tiros con related_pass_eventId: {linked_shots}/{total_shots} ({linked_shots/total_shots*100:.1f}%)")
    print(f"⚽ Autogoles detectados: {own_goals}")

    cols = ["match_id","eventId","minute","second","expandedMinute","period",
            "teamId","playerId","x","y","endX","endY",
            "typeName","shot_outcome","related_pass_eventId","is_own_goal","is_from_interception",
            "goal_mouth_y","goal_mouth_z","q_length","q_angle","qualifiers"]
    return shots.reindex(columns=[c for c in cols if c in shots.columns])

from collections import defaultdict

def build_df_passes_enriched(df_events: pd.DataFrame, df_shots: pd.DataFrame) -> pd.DataFrame:
    """Versión con validación robusta de asistencias"""
    if df_events is None or df_events.empty:
        return pd.DataFrame()

    # Extraer pases
    mask_pass = df_events["typeName"].eq("Pass")
    cols = ["match_id","eventId","minute","second","expandedMinute","period",
            "teamId","playerId","x","y","endX","endY","typeName","outcomeName","qualifiers"]
    passes = df_events.loc[mask_pass, [c for c in cols if c in df_events.columns]].copy()

    passes["pass_outcome"] = passes["outcomeName"].fillna("Unknown")
    passes["is_cross"] = passes["qualifiers"].apply(lambda qs: _q_has(qs, "Cross"))
    passes["is_throughball"] = passes["qualifiers"].apply(lambda qs: _q_has(qs, "ThroughBall") or _q_has(qs, "ChippedThroughBall"))
    passes["q_length"] = passes["qualifiers"].apply(lambda qs: _q_get(qs, "Length"))
    passes["q_angle"] = passes["qualifiers"].apply(lambda qs: _q_get(qs, "Angle"))

    # NUEVO: Detectar características del pase para validación
    passes["is_backward_pass"] = passes.apply(lambda row: 
        row["x"] > row["endX"] if (pd.notna(row["x"]) and pd.notna(row["endX"])) else False, axis=1)
    
    passes["is_pass_successful"] = passes["outcomeName"].eq("Successful")
    
    # Tipado consistente
    passes["eventId"] = passes["eventId"].astype("Int64")
    passes["teamId"] = passes["teamId"].astype("Int64")

    # Construcción de índices para matching
    shot_by_related = defaultdict(list)
    shot_by_eventid = defaultdict(list)
    
    if isinstance(df_shots, pd.DataFrame) and not df_shots.empty:
        shots = df_shots[df_shots["related_pass_eventId"].notna()].copy()
        if not shots.empty:
            shots["related_pass_eventId"] = shots["related_pass_eventId"].astype("Int64")
            shots["teamId"] = shots["teamId"].astype("Int64")
            
            for _, s in shots.iterrows():
                tid = s["teamId"]
                rp = s["related_pass_eventId"]
                if pd.isna(tid) or pd.isna(rp): 
                    continue
                    
                shot_info = {
                    "shot_eventId": _safe_int(s.get("eventId")),
                    "shot_outcome": s.get("shot_outcome"),
                    "shot_teamId": _safe_int(s.get("teamId")),  # NUEVO: teamId del tiro
                    "is_own_goal": bool(s.get("is_own_goal", False)),
                    "is_from_interception": bool(s.get("is_from_interception", False)),
                    "minute": _safe_int(s.get("minute")),
                    "second": _safe_float(s.get("second")),
                }
                
                key = (int(tid), int(rp))
                shot_by_related[key].append(shot_info)
                shot_by_eventid[int(rp)].append(shot_info)

    # FUNCIÓN DE MATCHING CON VALIDACIONES
    def get_valid_related_shots(row):
        """Solo devuelve tiros que realmente deberían contar como key pass/assist"""
        tid, eid = row.get("teamId"), row.get("eventId")
        if pd.isna(eid): 
            return []
        
        eid = int(eid)
        
        # Buscar tiros relacionados
        related_shots = []
        if not pd.isna(tid):
            key = (int(tid), eid)
            if key in shot_by_related:
                related_shots = shot_by_related[key]
        
        if not related_shots and eid in shot_by_eventid:
            related_shots = shot_by_eventid[eid]
        
        if not related_shots:
            return []
        
        # VALIDACIONES para filtrar casos problemáticos
        valid_shots = []
        for shot in related_shots:
            # Validación 1: El tiro debe ser del mismo equipo (excepto autogoles legítimos)
            shot_team = shot.get("shot_teamId")
            pass_team = int(tid) if not pd.isna(tid) else None
            
            if shot_team != pass_team and not shot.get("is_own_goal", False):
                # Tiro de equipo diferente y no es autogol -> probablemente interceptación
                continue
            
            # Validación 2: Pases hacia atrás fallidos que terminan en gol rival son sospechosos
            if (row.get("is_backward_pass", False) and 
                not row.get("is_pass_successful", True) and 
                shot.get("shot_outcome") == "Goal" and
                shot_team != pass_team):
                # Pase hacia atrás fallido + gol del rival = interceptación
                continue
            
            # Validación 3: Tiempo entre pase y tiro debe ser razonable
            pass_time = (row.get("minute", 0) * 60) + (row.get("second", 0) or 0)
            shot_time = (shot.get("minute", 0) * 60) + (shot.get("second", 0) or 0)
            time_diff = abs(shot_time - pass_time)
            
            if time_diff > 10:  # Más de 10 segundos es sospechoso
                continue
            
            # Validación 4: Distancia entre final del pase e inicio del tiro
            pass_end_x, pass_end_y = row.get("endX"), row.get("endY")
            # (Para esta validación necesitaríamos las coordenadas del tiro, que están en df_shots)
            
            valid_shots.append(shot)
        
        return valid_shots

    passes["related_shots"] = passes.apply(get_valid_related_shots, axis=1)

    # Recalcular etiquetas con validaciones
    passes["is_key_pass"] = passes["related_shots"].map(lambda L: len(L) > 0)
    
    # ASISTENCIA MEJORADA: Solo si es gol del mismo equipo y no autogol
    passes["is_assist"] = passes["related_shots"].map(
        lambda shots_list: any(
            shot.get("shot_outcome") == "Goal" and 
            not shot.get("is_own_goal", False) and
            not shot.get("is_from_interception", False)
            for shot in (shots_list or [])
        )
    )

    # NUEVA: Marcar asistencias problemáticas para auditoría
    passes["problematic_assist"] = passes.apply(lambda row:
        row.get("is_backward_pass", False) and 
        not row.get("is_pass_successful", True) and
        len(row.get("related_shots", [])) > 0, axis=1
    )

    # Estadísticas de verificación mejoradas
    key_passes = passes["is_key_pass"].sum()
    assists = passes["is_assist"].sum()
    problematic = passes["problematic_assist"].sum()
    total_passes = len(passes)
    
    print(f"🎯 Key passes: {key_passes}/{total_passes} ({key_passes/total_passes*100:.1f}%)")
    print(f"⚽ Assists: {assists}/{total_passes} ({assists/total_passes*100:.1f}%)")
    if problematic > 0:
        print(f"⚠️  Asistencias problemáticas detectadas y filtradas: {problematic}")

    # Flags WhoScored para auditoría
    passes["has_ws_keypass_flag"] = passes["qualifiers"].apply(
        lambda qs: _q_has(qs, "KeyPass") or _q_has(qs, "ShotAssist")
    )
    passes["has_ws_assist_flag"] = passes["qualifiers"].apply(
        lambda qs: any((q.get("type") or {}).get("displayName") in {
            "GoalAssist","IntentionalGoalAssist","Assist","IntentionalAssist"
        } for q in (qs or []))
    )

    want = ["match_id","eventId","minute","second","expandedMinute","period",
            "teamId","playerId","x","y","endX","endY","typeName","outcomeName",
            "pass_outcome","is_key_pass","is_assist","is_cross","is_throughball",
            "is_backward_pass","is_pass_successful","problematic_assist",
            "q_length","q_angle","related_shots",
            "has_ws_keypass_flag","has_ws_assist_flag","qualifiers"]
    return passes.reindex(columns=[c for c in want if c in passes.columns])


# FUNCIÓN AUXILIAR: Auditoría post-procesamiento
def audit_assists_and_key_passes(df_passes: pd.DataFrame, df_shots: pd.DataFrame, df_events: pd.DataFrame):
    """
    Función para auditar asistencias después del procesamiento
    Identifica casos sospechosos para revisión manual
    """
    print("\n=== AUDITORÍA DE ASISTENCIAS ===")
    
    if df_passes is None or df_passes.empty:
        print("No hay pases para auditar")
        return
    
    # Analizar asistencias detectadas
    assists = df_passes[df_passes["is_assist"] == True].copy()
    key_passes = df_passes[df_passes["is_key_pass"] == True].copy()
    
    print(f"Asistencias detectadas: {len(assists)}")
    print(f"Key passes detectados: {len(key_passes)}")
    
    # Revisar cada asistencia
    for _, assist in assists.iterrows():
        print(f"\n--- ASISTENCIA EventId {assist['eventId']} ---")
        print(f"Jugador: {assist['playerId']} (Team {assist['teamId']})")
        print(f"Coords: ({assist['x']:.1f}, {assist['y']:.1f}) -> ({assist['endX']:.1f}, {assist['endY']:.1f})")
        print(f"Outcome: {assist['pass_outcome']}")
        print(f"Pase hacia atrás: {assist.get('is_backward_pass', False)}")
        print(f"Pase exitoso: {assist.get('is_pass_successful', True)}")
        
        # Analizar tiros relacionados
        related_shots = assist.get("related_shots", [])
        if isinstance(related_shots, str):
            try:
                import json
                related_shots = json.loads(related_shots)
            except:
                related_shots = []
        
        for shot in related_shots:
            if shot.get("shot_outcome") == "Goal":
                shot_team = shot.get("shot_teamId")
                pass_team = assist["teamId"]
                print(f"  -> GOL: EventId {shot['shot_eventId']}, Team {shot_team}")
                if shot_team != pass_team:
                    print(f"     ⚠️  PROBLEMA: Gol de equipo diferente al pase")
                if shot.get("is_own_goal"):
                    print(f"     ⚠️  PROBLEMA: Es autogol")
    
    # Buscar casos problemáticos específicos
    print(f"\n=== CASOS PROBLEMÁTICOS ===")
    
    # Caso 1: Pases hacia atrás con goles
    backward_assists = df_passes[
        (df_passes["is_backward_pass"] == True) & 
        (df_passes["is_assist"] == True)
    ]
    print(f"Asistencias en pases hacia atrás: {len(backward_assists)}")
    
    # Caso 2: Pases fallidos con key passes
    failed_keypasses = df_passes[
        (df_passes["is_pass_successful"] == False) & 
        (df_passes["is_key_pass"] == True)
    ]
    print(f"Key passes en pases fallidos: {len(failed_keypasses)}")
    
    # Caso 3: Comparar con flags de WhoScored
    ws_assists = df_passes[df_passes["has_ws_assist_flag"] == True]
    our_assists = df_passes[df_passes["is_assist"] == True]
    
    print(f"WhoScored marca {len(ws_assists)} asistencias")
    print(f"Nuestro algoritmo detecta {len(our_assists)} asistencias")
    
    # Discrepancias
    only_ws = ws_assists[~ws_assists["eventId"].isin(our_assists["eventId"])]
    only_ours = our_assists[~our_assists["eventId"].isin(ws_assists["eventId"])]
    
    if len(only_ws) > 0:
        print(f"⚠️  {len(only_ws)} asistencias marcadas por WS pero NO por nosotros:")
        for _, p in only_ws.iterrows():
            print(f"   EventId {p['eventId']}: {p['playerId']} (Team {p['teamId']})")
    
    if len(only_ours) > 0:
        print(f"⚠️  {len(only_ours)} asistencias detectadas por nosotros pero NO por WS:")
        for _, p in only_ours.iterrows():
            print(f"   EventId {p['eventId']}: {p['playerId']} (Team {p['teamId']})")


# FUNCIÓN DE CORRECCIÓN POST-HOC (para casos ya procesados)
def fix_problematic_assists(df_passes: pd.DataFrame, df_shots: pd.DataFrame) -> pd.DataFrame:
    """
    Corrige asistencias problemáticas ya procesadas aplicando filtros adicionales
    """
    if df_passes is None or df_passes.empty:
        return df_passes
    
    df = df_passes.copy()
    original_assists = df["is_assist"].sum()
    
    # Aplicar correcciones
    for idx, row in df.iterrows():
        if not row.get("is_assist", False):
            continue
            
        # Parsear related_shots si es string
        related_shots = row.get("related_shots", [])
        if isinstance(related_shots, str):
            try:
                import json
                related_shots = json.loads(related_shots)
            except:
                related_shots = []
        
        # Verificar cada tiro relacionado
        valid_goals = []
        for shot in related_shots:
            if shot.get("shot_outcome") != "Goal":
                continue
                
            shot_team = shot.get("shot_teamId")
            pass_team = row["teamId"]
            
            # Filtro 1: Mismo equipo (excepto autogoles legítimos del rival)
            if shot_team != pass_team:
                continue
                
            # Filtro 2: No autogoles
            if shot.get("is_own_goal", False):
                continue
                
            # Filtro 3: Pases hacia atrás fallidos
            if (row.get("is_backward_pass", False) and 
                not row.get("is_pass_successful", True)):
                continue
                
            valid_goals.append(shot)
        
        # Actualizar is_assist basado en goles válidos
        df.at[idx, "is_assist"] = len(valid_goals) > 0
        
        # Actualizar is_key_pass si no hay tiros válidos
        if len(related_shots) == 0:
            df.at[idx, "is_key_pass"] = False
    
    corrected_assists = df["is_assist"].sum()
    print(f"Asistencias corregidas: {original_assists} -> {corrected_assists} (eliminadas: {original_assists - corrected_assists})")
    
    return df

# Heurística básica de acciones defensivas
_DEF_TYPES = {"Tackle","Interception","Clearance","BlockedShot","Aerial","BallRecovery","Challenge"}

def build_df_defensive_actions(df_events: pd.DataFrame) -> pd.DataFrame:
    if df_events is None or df_events.empty: 
        return pd.DataFrame()
    mask = df_events["typeName"].isin(_DEF_TYPES)
    cols = ["match_id","eventId","minute","second","expandedMinute","period",
            "teamId","playerId","x","y","typeName","outcomeName","qualifiers"]
    return df_events.loc[mask, [c for c in cols if c in df_events.columns]].copy()

# Acciones de portero (paradas, blocajes, despejes de puños, etc.)
_GK_TYPES = {"Save","Claim","KeeperPickup","Punch","Smother","KeeperSweeper"}

def build_df_gk_actions(df_events: pd.DataFrame) -> pd.DataFrame:
    if df_events is None or df_events.empty: 
        return pd.DataFrame()

    def is_gk_row(row) -> bool:
        if str(row.get("typeName")) in _GK_TYPES:
            return True
        qs = row.get("qualifiers")
        # En WS muchas paradas vienen como eventos de tiro + outcome Saved; aquí solo recogemos “acciones GK” explícitas
        # Si quieres capturar también el “SavedShot” vía tiro -> ya lo tienes en df_shots
        return False

    gk = df_events[df_events.apply(is_gk_row, axis=1)].copy()

    # Extracción de GoalMouthY/Z si aparecieran en la acción del GK (algunas veces WS lo adosa en la acción de tiro únicamente)
    gk["gk_goal_mouth_y"] = gk["qualifiers"].apply(lambda qs: _safe_float(_q_get(qs, "GoalMouthY")))
    gk["gk_goal_mouth_z"] = gk["qualifiers"].apply(lambda qs: _safe_float(_q_get(qs, "GoalMouthZ")))

    cols = ["match_id","eventId","minute","second","expandedMinute","period",
            "teamId","playerId","x","y","typeName","outcomeName","gk_goal_mouth_y","gk_goal_mouth_z","qualifiers"]
    return gk.reindex(columns=[c for c in cols if c in gk.columns])

# ==============================
# Formaciones y posiciones + Score timeline
# ==============================

def _slot_player_map(f: dict) -> dict:
    mapping = {}

    slots = f.get("formationSlots") or f.get("slots") or []
    pids  = f.get("playerIds") or []
    if isinstance(slots, list) and isinstance(pids, list) and len(slots) == len(pids) and len(slots) > 0:
        for s, pid in zip(slots, pids):
            try: s = int(s)
            except: continue
            if s > 0 and pid is not None:
                mapping[s] = int(pid)

    for key in ("formationSlotToPlayerIdMap","slotToPlayerIdMap"):
        d = f.get(key)
        if isinstance(d, dict):
            for k, v in d.items():
                try: s = int(k)
                except: continue
                if s > 0 and v is not None:
                    mapping[s] = int(v)

    for key in ("playerIdToFormationSlotMap","playerToSlotMap"):
        d = f.get(key)
        if isinstance(d, dict):
            for pid, s in d.items():
                try: s = int(s)
                except: continue
                if s > 0 and pid is not None:
                    mapping[s] = int(pid)

    slots_list = f.get("slots")
    if isinstance(slots_list, list) and not mapping:
        for it in slots_list:
            if not isinstance(it, dict): 
                continue
            s = it.get("slot"); pid = it.get("playerId")
            try: s = int(s)
            except: continue
            if s > 0 and pid is not None:
                mapping[s] = int(pid)
    return mapping

def _positions_list(f: dict) -> list:
    pos = f.get("formationPositions") or f.get("positions") or f.get("formationCoordinates") or []
    out = []
    for p in (pos or []):
        if not isinstance(p, dict):
            out.append({"horizontal": None, "vertical": None}); continue
        h = p.get("horizontal", p.get("x", p.get("centerX")))
        v = p.get("vertical",   p.get("y", p.get("centerY")))
        out.append({"horizontal": h, "vertical": v})
    return out

def build_formations_timelines(payload: Dict[str,Any], df_players: pd.DataFrame):
    mcd = payload.get("matchCentreData") or {}
    match_id = payload.get("matchId") or mcd.get("matchId")
    all_events = mcd.get("events") or []
    max_exp = 0
    for ev in all_events:
        try: max_exp = max(max_exp, int(ev.get("expandedMinute") or 0))
        except: pass
    max_exp += 1

    jersey_by_pid = {}
    for _, r in df_players.iterrows():
        pid = _safe_int(r.get("player_id"))
        if pid is not None:
            jersey_by_pid[pid] = r.get("shirtNo")

    rows_form, rows_pos = [], []
    for side in ("home","away"):
        team = (mcd.get(side) or {})
        team_id = team.get("teamId")
        team_name = team.get("name")
        forms = sorted(team.get("formations") or [], key=lambda f: (f.get("period", 0), f.get("startMinuteExpanded", -1)))

        for f in forms:
            period = f.get("period")
            if period not in (1,2,16): 
                continue
            start = _safe_int(f.get("startMinuteExpanded")) or 0
            end   = _safe_int(f.get("endMinuteExpanded")) or max_exp
            name  = (f.get("formationName") or "").strip() or None

            rows_form.append({
                "match_id": match_id,
                "team_side": side,
                "team_id": team_id,
                "team_name": team_name,
                "formation_name": name,
                "period": period,
                "start_expanded": start,
                "end_expanded": end,
                "duration_expanded": end - start,
            })

            slot2pid = _slot_player_map(f)
            pos_list = _positions_list(f)

            for s, pid in slot2pid.items():
                x = y = None
                if 1 <= s <= len(pos_list):
                    x = pos_list[s-1].get("horizontal")
                    y = pos_list[s-1].get("vertical")
                rows_pos.append({
                    "match_id": match_id,
                    "team_side": side,
                    "team_id": team_id,
                    "period": period,
                    "start_minute": start,
                    "end_minute": end,
                    "formation_name": name,
                    "slot": int(s),
                    "player_id": int(pid),
                    "jersey_number": jersey_by_pid.get(int(pid)),
                    "x": _safe_float(x),
                    "y": _safe_float(y),
                })

    df_form = pd.DataFrame(rows_form).sort_values(["team_side","start_expanded"]).reset_index(drop=True)
    df_pos  = pd.DataFrame(rows_pos).sort_values(["team_side","start_minute","slot"]).reset_index(drop=True)
    return df_form, df_pos

def build_score_timeline(df_shots: pd.DataFrame, home_team_id: int, away_team_id: int) -> pd.DataFrame:
    """
    Score timeline a partir de df_shots (solo filas de gol).
    Controla autogoles: si qualifier OwnGoal está presente → suma al rival.
    """
    if df_shots is None or df_shots.empty:
        return pd.DataFrame()

    goals = df_shots[df_shots["shot_outcome"]=="Goal"].copy()
    if goals.empty: 
        return pd.DataFrame()

    def is_own_goal(qs) -> bool:
        return _q_has(qs, "OwnGoal")

    rows = []
    h, a = 0, 0
    for _, g in goals.sort_values("expandedMinute").iterrows():
        tid = _safe_int(g.get("teamId"))
        own = is_own_goal(g.get("qualifiers"))
        # suma al rival si own goal
        if tid == home_team_id:
            if own: a += 1
            else:   h += 1
        elif tid == away_team_id:
            if own: h += 1
            else:   a += 1
        else:
            # si por lo que sea el teamId no coincide
            pass
        rows.append({
            "expandedMinute": _safe_int(g.get("expandedMinute")),
            "scorer_teamId": tid,
            "own_goal": bool(own),
            "score_home": h,
            "score_away": a
        })
    return pd.DataFrame(rows)

def attach_score_to_formations(df_form: pd.DataFrame, df_score: pd.DataFrame, home_team_id: int, away_team_id: int) -> pd.DataFrame:
    """
    Hace merge_asof del marcador vigente al inicio de cada segmento de formación.
    También etiqueta quién iba por delante al empezar el segmento.
    """
    if df_form is None or df_form.empty:
        return pd.DataFrame()
    if df_score is None or df_score.empty:
        df = df_form.copy()
        df["score_home"] = 0
        df["score_away"] = 0
        df["leader_at_start"] = "draw"
        return df

    key = "start_expanded"
    left = df_form.sort_values(key).copy()
    right = df_score.sort_values("expandedMinute").copy()

    merged = pd.merge_asof(
        left, right, left_on=key, right_on="expandedMinute",
        direction="backward"
    )

    merged["score_home"] = merged["score_home"].fillna(0).astype(int)
    merged["score_away"] = merged["score_away"].fillna(0).astype(int)

    def leader(r):
        if r["score_home"] > r["score_away"]: return "home"
        if r["score_home"] < r["score_away"]: return "away"
        return "draw"

    merged["leader_at_start"] = merged.apply(leader, axis=1)
    merged.drop(columns=["expandedMinute","scorer_teamId","own_goal"], inplace=True, errors="ignore")
    return merged

# ==============================
# Guardado (idéntico al notebook)
# ==============================

def _ensure_match_id_col(df: pd.DataFrame, match_id: int) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame): 
        return df
    df = df.copy()
    if "match_id" not in df.columns:
        df["match_id"] = match_id
    else:
        if df["match_id"].isna().any():
            df.loc[df["match_id"].isna(), "match_id"] = match_id
    return df

def _write_df_pair(df: pd.DataFrame, base: str, out_json: Path, out_csv: Path, match_id: int) -> int:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return 0
    df = _ensure_match_id_col(df, match_id)
    out_json.write_text(df.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    df_csv = df.copy()
    for col in df_csv.columns:
        if any(df_csv[col].map(lambda x: isinstance(x, (list, dict))).fillna(False)):
            df_csv[col] = df_csv[col].map(_jsonify_cell)
    df_csv.to_csv(out_csv, index=False, encoding="utf-8-sig")
    return len(df)

def save_all_tables(payload: Dict[str,Any], out_root: Path) -> Dict[str, Any]:
    mcd = payload.get("matchCentreData") or {}
    match_id = payload.get("matchId") or mcd.get("matchId")
    home = (mcd.get("home") or {}).get("name") or "Home"
    away = (mcd.get("away") or {}).get("name") or "Away"
    comp = (mcd.get("competitionName") or mcd.get("tournamentName") or "Competition")
    season = (mcd.get("seasonName") or "Season")
    start_time = (mcd.get("startTime") or "")[:10].replace("-", "")
    comp_slug = _slug(comp)
    season_slug = _slug(season)
    match_slug = f"{start_time}_{_slug(home)}_vs_{_slug(away)}_{match_id}"

    # Estructura de salida
    base_dir = out_root / "MatchCenter" / comp_slug / season_slug / match_slug
    norm_dir = base_dir / "normalized"
    csv_dir  = base_dir / "csv"
    _ensure_dir(norm_dir); _ensure_dir(csv_dir)

    # Normalización base
    df_match, df_players, df_events = to_dataframes(payload)

    # Derivados
    df_shots   = build_df_shots(df_events)
    df_passes  = build_df_passes_enriched(df_events, df_shots)
    df_def     = build_df_defensive_actions(df_events)
    df_gk      = build_df_gk_actions(df_events)
    df_form, df_pos = build_formations_timelines(payload, df_players)

    home_id = _safe_int(df_match.iloc[0]["home_team_id"]) if not df_match.empty else None
    away_id = _safe_int(df_match.iloc[0]["away_team_id"]) if not df_match.empty else None
    df_score = build_score_timeline(df_shots, home_id, away_id) if (home_id and away_id) else pd.DataFrame()
    df_form_scored = attach_score_to_formations(df_form, df_score, home_id, away_id)

    # Guardado + manifest
    manifest = {
        "match_id": match_id,
        "created_at": _now_iso(),
        "normalized_dir": str(norm_dir.resolve()),
        "csv_dir": str(csv_dir.resolve()),
        "tables": {}
    }

    def _save(name: str, df: pd.DataFrame):
        j = norm_dir / f"{name}.json"
        c = csv_dir  / f"{name}.csv"
        n = _write_df_pair(df, name, j, c, match_id)
        manifest["tables"][name] = {
            "rows": int(n),
            "json": j.name, "csv": c.name,
            "json_sha1": _sha1_of_file(j) if j.exists() else None,
            "csv_sha1": _sha1_of_file(c) if c.exists() else None,
        }

    _save("match_meta", df_match)
    _save("players", df_players)
    _save("events", df_events)
    _save("events_shots", df_shots)
    _save("events_passes", df_passes)
    _save("events_defensive", df_def)
    _save("events_gk_actions", df_gk)
    _save("formations_timeline", df_form)
    _save("player_positions_timeline", df_pos)
    _save("score_timeline", df_score)
    _save("formations_timeline_scored", df_form_scored)

    # payload + diccionario de eventos
    payload_path = norm_dir / "payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["payload"] = {"file": payload_path.name, "sha1": _sha1_of_file(payload_path)}

    evt_dict = payload.get("matchCentreEventType")
    if evt_dict:
        evt_path = norm_dir / "event_types.json"
        evt_path.write_text(json.dumps(evt_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["event_types"] = {"file": evt_path.name, "sha1": _sha1_of_file(evt_path)}

    man_path = norm_dir / "manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "out_dir": str(base_dir.resolve()),
        "manifest": manifest
    }

# ==============================
# Pipeline principal
# ==============================

def process_one_match(
    url: str | None = None,
    match_id: int | None = None,
    html_path: Path | None = None,
    out_root: Path = Path("."),
    use_selenium: bool = True,
    headless: bool = True,
    driver=None,   # ← se reutiliza
):
    # 1) HTML: Live o Show/Match-Centre, ambas valen
    if html_path and Path(html_path).exists():
        html = Path(html_path).read_text(encoding="utf-8")
    else:
        if not url and match_id:
            url = f"https://es.whoscored.com/Matches/{match_id}/Show/Match-Centre"
        if not url:
            raise ValueError("Debes pasar --url, --match-id o --html.")
        if use_selenium:
            html = get_html_via_selenium(url, driver=driver, headless=headless)
        else:
            raise RuntimeError("use_selenium=False no soportado. Usa Selenium o HTML local.")

    payload = load_payload_from_html_text(html)
    if not payload or "matchCentreData" not in payload:
        raise RuntimeError("No se pudo extraer matchCentreData del HTML.")

    return save_all_tables(payload, out_root=out_root)


def process_from_csv(
    csv_file: Path,
    out_root: Path = Path("."),
    driver=None,                         # ← OBLIGATORIO si navegas muchas URLs
    pause_range: tuple[float,float] = (1.2, 2.8),
    cooldown_every: int = 8,
    cooldown_secs: int = 20,
    limit: int | None = None,
):
    import random, time as _time
    import pandas as pd

    df = pd.read_csv(csv_file)
    results = []
    n = len(df) if limit is None else min(limit, len(df))

    for i, row in df.head(n).iterrows():
        url = (
            row.get("match_centre_url")
            or row.get("match_center_url")
            or row.get("match__centre_url")   # por si viene con doble underscore
        )
        mid = _safe_int(row.get("match_id"))
        try:
            res = process_one_match(
                url=url,           # admite /Live sin problema
                match_id=mid,
                out_root=out_root,
                use_selenium=True,
                headless=False,    # visible = más fácil cookies/consent
                driver=driver,     # reusar sesión ⇢ menos 403
            )
            print(f"✅ OK [{i+1}/{n}] match_id={mid} → {res['out_dir']}")
            results.append(res)
        except Exception as e:
            print(f"❌ ERROR [{i+1}/{n}] match_id={mid} url={url}: {e}")

        _time.sleep(random.uniform(*pause_range))
        if cooldown_every and (i+1) % cooldown_every == 0:
            print(f"… cooldown {cooldown_secs}s")
            _time.sleep(cooldown_secs)

    return results

# ==============================
# CLI
# ==============================

def main():
    ap = argparse.ArgumentParser(description="WhoScored Match Centre scraper (payload→JSON/CSV)")
    ap.add_argument("--url", type=str, help="URL completa del Match Centre de WhoScored")
    ap.add_argument("--match-id", type=int, help="match_id (construye URL Show)")
    ap.add_argument("--html", type=str, help="Ruta a HTML ya guardado del Match Centre")
    ap.add_argument("--from-csv", type=str, help="CSV con columna match_centre_url o match_id")
    ap.add_argument("--out", type=str, default=str(MATCHCENTER_BASE_DIR), help="Directorio base de salida  (por defecto: data/raw/matchcenter)")
    ap.add_argument("--limit", type=int, default=None, help="Máximo de filas a procesar desde --from-csv")
    ap.add_argument("--use-selenium", action="store_true", default=True, help="Usar Selenium para obtener HTML (evita 403)")
    ap.add_argument("--no-headless", action="store_true", help="Lanza navegador visible (debug)")
    args = ap.parse_args()

    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    _ensure_dir(out_root)

    if args.from_csv:
        process_from_csv(Path(args.from_csv), out_root=out_root, limit=args.limit)
        return

    html_path = Path(args.html) if args.html else None
    res = process_one_match(
        url=args.url,
        match_id=args.match_id,
        html_path=html_path,
        out_root=out_root,
        use_selenium=args.use_selenium,
        headless=(not args.no_headless)
    )
    print("\n✅ Partido procesado exitosamente")
    print(f"  → {res['out_dir']}")

if __name__ == "__main__":
    main()