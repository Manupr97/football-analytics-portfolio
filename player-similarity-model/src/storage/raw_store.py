"""
raw_store.py — Escritura de datos raw en disco (Parquet + JSON).

Los archivos raw son INMUTABLES una vez escritos. Nunca se sobreescriben.
Sirven como fuente de verdad offline para re-parsear sin volver a scrapear.

Estructura de salida (relativa a settings.matchcenter_raw_dir):

    <comp_slug>/<season_slug>/<YYYYMMDD>_<home_slug>_vs_<away_slug>_<match_id>/
        normalized/
            payload.json          ← payload completo re-parseable
            manifest.json         ← metadatos de ingesta
        parquet/
            match_meta.parquet
            players.parquet
            events.parquet
            events_shots.parquet
            events_passes.parquet
            events_defensive.parquet
            events_gk_actions.parquet
            formations_timeline.parquet
            player_positions_timeline.parquet
            score_timeline.parquet

Uso:

    from ws_platform.storage.raw_store import RawStore
    store = RawStore(comp_key="laliga", season_key="2025-2026")
    match_dir = store.save_match(
        payload, df_match, df_players, df_events,
        df_shots, df_passes, df_def, df_gk, df_form, df_pos, df_score,
    )
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

import logging

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_RAW_DIR = _PROJECT_ROOT / "data" / "raw" / "matchcenter"


def _slugify(text: str) -> str:
    """Convierte un nombre de equipo en slug para nombres de carpeta."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return (
        text.lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("'", "")
        .replace("-", "_")
    )


class RawStore:
    """
    Gestiona la escritura de datos raw de un partido en disco.

    Args:
        comp_key:   Clave de competición (ej: "laliga").
        season_key: Clave de temporada (ej: "2025-2026").
        base_dir:   Directorio raíz para los parquets. Por defecto: data/raw/matchcenter/.
    """

    def __init__(self, comp_key: str, season_key: str, base_dir: Path | None = None) -> None:
        self.comp_key   = comp_key
        self.season_key = season_key
        self._base_dir  = base_dir if base_dir is not None else _DEFAULT_RAW_DIR

    def _match_dir(
        self,
        match_id: int,
        match_date: str,
        home_name: str,
        away_name: str,
    ) -> Path:
        """
        Construye la ruta del directorio de un partido.

        match_date: "YYYY-MM-DD" (ISO, del parser) o "DD/MM/YYYY" (legado).
        """
        date_str = "00000000"
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(match_date[:10], fmt)
                date_str = dt.strftime("%Y%m%d")
                break
            except Exception:
                continue

        home_slug = _slugify(home_name or "home")
        away_slug = _slugify(away_name or "away")
        folder    = f"{date_str}_{home_slug}_vs_{away_slug}_{match_id}"

        return self._base_dir / self.comp_key / self.season_key / folder

    def save_match(
        self,
        payload:    dict[str, Any],
        df_match:   pd.DataFrame,
        df_players: pd.DataFrame,
        df_events:  pd.DataFrame,
        df_shots:   pd.DataFrame,
        df_passes:  pd.DataFrame,
        df_def:     pd.DataFrame,
        df_gk:      pd.DataFrame,
        df_formations: pd.DataFrame,
        df_positions:  pd.DataFrame,
        df_score:      pd.DataFrame,
    ) -> Path:
        """
        Persiste todos los datos de un partido en disco.

        No sobreescribe si el directorio ya existe (protección de inmutabilidad).

        Returns:
            Path al directorio del partido.
        """
        match_id  = int(df_match["match_id"].iloc[0])
        home_name = str(df_match["home_name"].iloc[0] or "home")
        away_name = str(df_match["away_name"].iloc[0] or "away")
        match_date = str(df_match["start_date"].iloc[0] or "")

        match_dir = self._match_dir(match_id, match_date, home_name, away_name)

        if match_dir.exists():
            log.warning(
                "raw_store_directorio_ya_existe",
                match_id=match_id,
                path=str(match_dir),
            )
            return match_dir

        # Crear estructura de carpetas
        normalized_dir = match_dir / "normalized"
        parquet_dir    = match_dir / "parquet"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        parquet_dir.mkdir(parents=True, exist_ok=True)

        # --- payload.json ---
        (normalized_dir / "payload.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # --- manifest.json ---
        manifest = {
            "match_id":   match_id,
            "comp_key":   self.comp_key,
            "season_key": self.season_key,
            "home_name":  home_name,
            "away_name":  away_name,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "n_events":   len(df_events),
            "n_shots":    len(df_shots),
            "n_passes":   len(df_passes),
            "n_defensive": len(df_def),
            "n_gk":       len(df_gk),
        }
        (normalized_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # --- Parquet ---
        # qualifiers es una lista de dicts — serializar a JSON string para
        # compatibilidad con Parquet (no admite listas de objetos mixtos).
        # NOTA: las coordenadas se guardan en escala WhoScored (0–100) tal
        # como salen del parser. La conversión a UEFA (105×68) se aplica
        # en viz/pitch_utils.py → to_uefa() antes de dibujar.
        def _prep_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
            df = df.copy()
            if "qualifiers" in df.columns:
                df["qualifiers"] = df["qualifiers"].apply(
                    lambda x: json.dumps(x, ensure_ascii=False) if x is not None else None
                )
            return df

        parquet_files = {
            "match_meta.parquet":               df_match,
            "players.parquet":                  df_players,
            "events.parquet":                   df_events,
            "events_shots.parquet":             df_shots,
            "events_passes.parquet":            df_passes,
            "events_defensive.parquet":         df_def,
            "events_gk_actions.parquet":        df_gk,
            "formations_timeline.parquet":      df_formations,
            "player_positions_timeline.parquet": df_positions,
            "score_timeline.parquet":           df_score,
        }

        for filename, df in parquet_files.items():
            if df is not None and not df.empty:
                _prep_for_parquet(df).to_parquet(
                    parquet_dir / filename,
                    index=False,
                    engine="pyarrow",
                    compression="snappy",
                )

        log.info(
            "raw_store_partido_guardado",
            match_id=match_id,
            path=str(match_dir),
            n_events=len(df_events),
            n_shots=len(df_shots),
            n_passes=len(df_passes),
        )

        return match_dir
