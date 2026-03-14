"""
load_whoscored.py
Carga los parquets de WhoScored (matchcenter) de las 5 grandes ligas
y agrega todas las métricas a nivel jugador para la temporada indicada.

Fuente: ws-analytics-platform/data/raw/matchcenter/{liga}/{temporada}/{partido}/parquet/
"""

import unicodedata
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd


def _normalize_name(name: str) -> str:
    """Normaliza nombres de jugadores: quita tildes y caracteres corruptos."""
    if not isinstance(name, str):
        return name
    # Intentar decodificar latin-1 mal interpretado como ascii
    try:
        fixed = name.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        fixed = name
    # Strip acentos
    return unicodedata.normalize("NFD", fixed).encode("ascii", "ignore").decode("ascii")

# Ruta por defecto: data/raw/matchcenter/ dentro de este mismo proyecto
# El scraper (src/scraping/ingest.py) guarda los parquets aquí.
_DEFAULT_MATCHCENTER_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "matchcenter"

LEAGUES = ["laliga", "premier_league", "bundesliga", "serie_a", "ligue_1"]
LEAGUE_DISPLAY = {
    "laliga": "La Liga",
    "premier_league": "Premier League",
    "bundesliga": "Bundesliga",
    "serie_a": "Serie A",
    "ligue_1": "Ligue 1",
}


# =============================================================================
# CARGA DE PARQUETS
# =============================================================================

def _iter_matches(matchcenter_dir: Path, season: str):
    """Itera sobre todas las carpetas de partido disponibles."""
    for league in LEAGUES:
        season_dir = matchcenter_dir / league / season
        if not season_dir.exists():
            continue
        for match_dir in season_dir.iterdir():
            if match_dir.is_dir():
                yield league, match_dir


def _read(match_dir: Path, filename: str) -> Optional[pd.DataFrame]:
    path = match_dir / "parquet" / filename
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def load_raw(matchcenter_dir: Path, season: str) -> dict:
    """
    Carga todos los parquets de todos los partidos y los concatena por tipo.
    Devuelve dict con claves: players, events, passes, shots, defensive, meta.
    """
    buckets = {k: [] for k in ["players", "events", "passes", "shots", "defensive", "meta"]}
    file_map = {
        "players":   "players.parquet",
        "events":    "events.parquet",
        "passes":    "events_passes.parquet",
        "shots":     "events_shots.parquet",
        "defensive": "events_defensive.parquet",
        "meta":      "match_meta.parquet",
    }

    for league, match_dir in _iter_matches(matchcenter_dir, season):
        for key, fname in file_map.items():
            df = _read(match_dir, fname)
            if df is not None:
                df["_league"] = league
                # Normalizar nombres de jugadores y equipos (fix encoding latin-1/utf-8)
                if key == "players":
                    if "player_name" in df.columns:
                        df["player_name"] = df["player_name"].apply(_normalize_name)
                    if "team_name" in df.columns:
                        df["team_name"] = df["team_name"].apply(_normalize_name)
                buckets[key].append(df)

    return {k: pd.concat(v, ignore_index=True) if v else pd.DataFrame()
            for k, v in buckets.items()}


# =============================================================================
# MINUTOS JUGADOS
# =============================================================================

def _compute_minutes(raw: dict) -> pd.DataFrame:
    """
    Calcula minutos jugados por jugador por partido usando match_meta.
    players.parquet no tiene minutos, así que usamos el minuto final del partido
    (score_timeline o el máximo de expanded_minute en events) como duración.
    Para starters: minutos = duración del partido (aprox 90 o más).
    Para suplentes: minutos = duración - minuto de entrada (sin datos exactos usamos 45).
    """
    players = raw["players"]
    if players.empty:
        return pd.DataFrame()

    # Duración aproximada por partido: max expanded_minute de events
    events = raw["events"]
    if not events.empty:
        match_duration = (
            events.groupby("match_id")["expanded_minute"]
            .max()
            .reset_index()
            .rename(columns={"expanded_minute": "match_minutes"})
        )
    else:
        match_duration = pd.DataFrame(columns=["match_id", "match_minutes"])

    df = players.merge(match_duration, on="match_id", how="left")
    df["match_minutes"] = df["match_minutes"].fillna(90)

    # Starters juegan el partido completo; suplentes ~45 min (estimación conservadora)
    df["minutes"] = np.where(df["is_first_eleven"], df["match_minutes"], 45)
    return df[["match_id", "player_id", "player_name", "team_id", "team_name",
               "position", "_league", "minutes", "is_first_eleven"]]


# =============================================================================
# INFERENCIA DE CONDUCCIONES (CARRIES)
# =============================================================================

def _infer_carries(
    events: pd.DataFrame,
    min_carry_length: float = 3.0,
    max_carry_length: float = 60.0,
    max_carry_duration: float = 10.0,
) -> pd.DataFrame:
    """
    Infiere conducciones de balón a partir de los eventos WhoScored.

    WhoScored no genera eventos de tipo 'Carry'. Se detectan como el espacio
    entre dos eventos consecutivos del mismo equipo donde:
      - El evento anterior tiene coordenadas de destino (end_x, end_y).
      - La distancia desde end_x/end_y del evento anterior hasta x/y del
        siguiente está entre min_carry_length y max_carry_length metros.
      - El tiempo entre eventos es < max_carry_duration segundos.
      - Ambos eventos pertenecen al mismo periodo.

    Metodología adaptada de StatsBomb Open Data (insert_ball_carries).

    Returns
    -------
    DataFrame con columnas: player_id, carries, carry_distance
    """
    PITCH_X = 105.0  # metros
    PITCH_Y = 68.0   # metros

    ev = events.copy().reset_index(drop=True)

    # Calcular tiempo acumulado en segundos para cada evento
    ev["_time_s"] = ev["expanded_minute"] * 60 + ev["second"].fillna(0)

    carry_rows = []

    # Tipos de evento que interrumpen una conducción
    NON_CARRY_TYPES = {
        "TakeOn",         # regate propio ya contabilizado aparte
        "Foul",
        "Card",
        "SubstitutionOff",
        "SubstitutionOn",
        "End",
        "Start",
        "FormationSet",
        "FormationChange",
    }

    for i in range(len(ev) - 1):
        prev = ev.iloc[i]
        nxt  = ev.iloc[i + 1]

        # El evento anterior debe tener coordenadas de destino
        if pd.isna(prev["end_x"]) or pd.isna(prev["end_y"]):
            continue

        # Mismo equipo, mismo periodo
        if prev["team_id"] != nxt["team_id"]:
            continue
        if prev["period_value"] != nxt["period_value"]:
            continue

        # El evento siguiente no debe ser de los que interrumpen
        if nxt["type_name"] in NON_CARRY_TYPES:
            continue

        # Distancia en metros (coordenadas WhoScored están en 0-100)
        dx = PITCH_X * (prev["end_x"] - nxt["x"]) / 100.0
        dy = PITCH_Y * (prev["end_y"] - nxt["y"]) / 100.0
        dist = (dx ** 2 + dy ** 2) ** 0.5

        if dist < min_carry_length or dist > max_carry_length:
            continue

        # Duración
        dt = nxt["_time_s"] - prev["_time_s"]
        if dt <= 0 or dt > max_carry_duration:
            continue

        carry_rows.append({
            "player_id":      nxt["player_id"],
            "carry_distance": dist,
        })

    if not carry_rows:
        return pd.DataFrame(columns=["player_id", "carries", "carry_distance"])

    carries_df = pd.DataFrame(carry_rows)
    return (
        carries_df
        .groupby("player_id")
        .agg(carries=("carry_distance", "count"), carry_distance=("carry_distance", "sum"))
        .reset_index()
    )


# =============================================================================
# AGREGACIÓN POR JUGADOR
# =============================================================================

def aggregate_players(
    matchcenter_dir: Path = _DEFAULT_MATCHCENTER_DIR,
    season: str = "2025-2026",
    min_minutes: int = 450,
) -> pd.DataFrame:
    """
    Agrega todas las métricas de evento a nivel jugador para la temporada dada.
    Aplica un mínimo de minutos para filtrar jugadores con poca muestra.

    Parameters
    ----------
    matchcenter_dir : Path
        Ruta a data/raw/matchcenter/ (dentro del proyecto por defecto).
    season : str
        Temporada en formato "YYYY-YYYY".
    min_minutes : int
        Minutos mínimos jugados para incluir al jugador.

    Returns
    -------
    DataFrame con una fila por jugador, columnas de features crudas (no per-90).
    Incluye columna 'minutes' y 'matches' para normalizar posteriormente.
    """
    print(f"Cargando parquets WhoScored — temporada {season}...")
    raw = load_raw(matchcenter_dir, season)

    # --- Minutos jugados ---
    minutes_df = _compute_minutes(raw)
    if minutes_df.empty:
        raise RuntimeError("No se encontraron datos de jugadores.")

    # Agregar por jugador: posición más frecuente como titular
    pos_mode = (
        minutes_df[minutes_df["is_first_eleven"] == True]
        .groupby("player_id")["position"]
        .agg(lambda x: x.mode().iloc[0] if len(x) > 0 else "Sub")
        .reset_index()
        .rename(columns={"position": "position_main"})
    )

    player_base = (
        minutes_df
        .groupby(["player_id", "player_name", "team_name", "_league"], dropna=False)
        .agg(minutes=("minutes", "sum"), matches=("match_id", "nunique"))
        .reset_index()
    )
    player_base = player_base.merge(pos_mode, on="player_id", how="left")
    player_base["position_main"] = player_base["position_main"].fillna("Sub")
    player_base = player_base.rename(columns={
        "team_name": "team", "_league": "league", "position_main": "position"
    })
    player_base["league"] = player_base["league"].map(LEAGUE_DISPLAY).fillna(player_base["league"])

    # --- Pases ---
    passes = raw["passes"]
    if not passes.empty:
        p = passes.copy()
        p["is_forward"] = p["angle"].between(-np.pi / 2, np.pi / 2) if "angle" in p.columns else False
        agg_passes = p.groupby("player_id").agg(
            passes_total=("event_id", "count"),
            passes_completed=("is_completed", "sum"),
            passes_forward=("is_forward", "sum"),
            passes_progressive=("is_progressive", "sum"),
            passes_into_box=("end_x", lambda x: (x > 83).sum()),
            passes_switch=("is_switch", "sum"),
            key_passes=("is_key_pass", "sum"),
            assists_pass=("is_assist", "sum"),
            crosses=("is_cross", "sum"),
            throughballs=("is_throughball", "sum"),
            pass_length_sum=("length", "sum"),
        ).reset_index()
        player_base = player_base.merge(agg_passes, on="player_id", how="left")
    else:
        for col in ["passes_total", "passes_completed", "passes_forward", "passes_progressive",
                    "passes_into_box", "passes_switch", "key_passes", "assists_pass",
                    "crosses", "throughballs", "pass_length_sum"]:
            player_base[col] = 0

    # --- Tiros ---
    shots = raw["shots"]
    if not shots.empty:
        agg_shots = shots.groupby("player_id").agg(
            shots_total=("event_id", "count"),
            shots_on_target=("shot_outcome", lambda x: x.isin(["ShotOnPost", "SavedShot", "Goal"]).sum()),
            goals=("shot_outcome", lambda x: (x == "Goal").sum()),
            shots_from_box=("x", lambda x: (x > 83).sum()),
        ).reset_index()
        player_base = player_base.merge(agg_shots, on="player_id", how="left")
    else:
        for col in ["shots_total", "shots_on_target", "goals", "shots_from_box"]:
            player_base[col] = 0

    # --- Acciones defensivas ---
    defn = raw["defensive"]
    if not defn.empty:
        agg_def = defn.groupby("player_id").agg(
            tackles=("is_tackle", "sum"),
            interceptions=("is_interception", "sum"),
            clearances=("is_clearance", "sum"),
            ball_recoveries=("is_ball_recovery", "sum"),
            aerials_total=("is_aerial", "sum"),
            aerials_won=("is_aerial_won", "sum"),
            fouls=("is_foul", "sum"),
            high_turnovers=("is_high_turnover", "sum"),
        ).reset_index()
        player_base = player_base.merge(agg_def, on="player_id", how="left")
    else:
        for col in ["tackles", "interceptions", "clearances", "ball_recoveries",
                    "aerials_total", "aerials_won", "fouls", "high_turnovers"]:
            player_base[col] = 0

    # --- Eventos generales (toques, conducciones, regates) ---
    events = raw["events"]
    if not events.empty:
        # Toques
        touches = (
            events[events["is_touch"] == True]
            .groupby("player_id").size()
            .reset_index(name="touches")
        )

        # Conducciones (carries): WhoScored no genera eventos Carry explícitos.
        # Se infieren como el espacio entre dos eventos consecutivos del mismo equipo
        # donde el balón se desplaza entre 3 y 60 metros en menos de 10 segundos,
        # siguiendo la metodología de StatsBomb/Opta (adaptada al schema WhoScored).
        carries_df = _infer_carries(events)

        # Regates: outcome_name en WhoScored es "Successful" / "Unsuccessful" (no "Success")
        dribbles_all = (
            events[events["type_name"] == "TakeOn"]
            .groupby("player_id").size()
            .reset_index(name="dribbles_attempted")
        )
        dribbles_won = (
            events[
                (events["type_name"] == "TakeOn") &
                (events["outcome_name"] == "Successful")
            ]
            .groupby("player_id").size()
            .reset_index(name="dribbles_won")
        )

        player_base = player_base.merge(touches,       on="player_id", how="left")
        player_base = player_base.merge(carries_df,    on="player_id", how="left")
        player_base = player_base.merge(dribbles_all,  on="player_id", how="left")
        player_base = player_base.merge(dribbles_won,  on="player_id", how="left")
    else:
        for col in ["touches", "carries", "carry_distance", "dribbles_attempted", "dribbles_won"]:
            player_base[col] = 0

    # --- Rellenar NaN con 0 en columnas numéricas ---
    num_cols = player_base.select_dtypes(include="number").columns
    player_base[num_cols] = player_base[num_cols].fillna(0)

    # --- Filtro de minutos mínimos ---
    before = len(player_base)
    player_base = player_base[player_base["minutes"] >= min_minutes].reset_index(drop=True)
    print(f"Jugadores tras filtro {min_minutes} min: {len(player_base)} (de {before})")

    return player_base
