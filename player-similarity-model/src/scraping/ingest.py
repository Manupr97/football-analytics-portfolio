"""
ingest.py — Orquestador de scraping para el proyecto player-similarity-model.

Descarga partidos de WhoScored para las 5 grandes ligas y los guarda como
parquets en data/raw/matchcenter/<liga>/<temporada>/<partido>/parquet/.

Uso:
  # Scraping completo (todos los meses de la temporada activa)
  python -m src.scraping.ingest

  # Solo ciertos meses
  python -m src.scraping.ingest --months "oct 2025" "nov 2025" "dic 2025"

  # Solo una liga
  python -m src.scraping.ingest --leagues laliga premier_league

  # Re-parsear parquets desde HTMLs ya guardados (sin scrapear)
  python -m src.scraping.ingest --reparse

Notas:
  - Los datos raw (parquets) NO se sobreescriben si ya existen.
  - El scraper usa undetected-chromedriver para bypass anti-bot de WhoScored.
  - Rango de meses por defecto: ago 2025 – junio 2026 (temporada 2025-2026).
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from src.scraping.competitions import get_competition, list_competitions
from src.scraping.driver_factory import build_driver, quit_driver
from src.scraping.fixtures_scraper import FixturesScraper
from src.scraping.matchcenter_scraper import MatchcenterScraper
from src.parsing.payload_parser import load_payload_from_html, to_dataframes
from src.parsing.passes import build_df_passes_enriched
from src.parsing.shots import build_df_shots
from src.parsing.defensive import build_df_defensive_actions, build_df_gk_actions
from src.parsing.formations import (
    build_formations_timeline,
    build_player_positions,
    build_score_timeline,
)
from src.storage.raw_store import RawStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Ligas de las 5 grandes a scrapear (corresponden a comp_key en competitions.yaml)
_DEFAULT_LEAGUES = ["laliga", "premier_league", "bundesliga", "serie_a", "ligue_1"]

# Meses de la temporada 2025-2026 (ajusta según avance la temporada)
_DEFAULT_MONTHS = [
    "ago 2025", "sep 2025", "oct 2025", "nov 2025", "dic 2025",
    "ene 2026", "feb 2026", "mar 2026", "abr 2026", "may 2026", "jun 2026",
]

_DEFAULT_SEASON = "2025-2026"


def ingest_league(
    comp_key: str,
    season: str,
    months: list[str],
    driver,
) -> None:
    """Descarga y guarda todos los partidos de una liga."""
    comp = get_competition(comp_key)
    season_cfg = comp.season(season)

    log.info(f"=== {comp.display_name} — {season} ===")

    # 1. Obtener lista de partidos
    fixtures_scraper = FixturesScraper(driver)
    _, stage_cfg = next(iter(season_cfg.iter_stages()))
    fixtures = fixtures_scraper.fetch_finished(stage_cfg.fixtures_url, months=months)

    if fixtures.empty:
        log.warning(f"Sin partidos encontrados para {comp_key} en {months}")
        return

    log.info(f"{len(fixtures)} partidos encontrados para {comp.display_name}")

    # 2. Scrapear y guardar cada partido
    mc_scraper = MatchcenterScraper(driver)
    store = RawStore(comp_key=comp_key, season_key=season)

    for _, row in fixtures.iterrows():
        match_id = int(row["match_id"])
        home = row.get("home_name", "home")
        away = row.get("away_name", "away")

        log.info(f"  [{match_id}] {home} vs {away}")

        try:
            html = mc_scraper.fetch(match_id=match_id)
            _parse_and_save(html, store)
        except Exception as exc:
            log.error(f"  Error en partido {match_id}: {exc}")
            continue

        # Pausa cortés entre partidos
        time.sleep(2)


def _parse_and_save(html: str, store: RawStore) -> None:
    """Parsea el HTML y guarda los parquets."""
    payload = load_payload_from_html(html)
    df_match, df_players, df_events = to_dataframes(payload)

    df_passes = build_df_passes_enriched(df_events)
    df_shots = build_df_shots(df_events)
    df_def = build_df_defensive_actions(df_events)
    df_gk = build_df_gk_actions(df_events)
    df_formations = build_formations_timeline(payload)
    df_positions = build_player_positions(payload)
    df_score = build_score_timeline(payload)

    store.save_match(
        payload=payload,
        df_match=df_match,
        df_players=df_players,
        df_events=df_events,
        df_shots=df_shots,
        df_passes=df_passes,
        df_def=df_def,
        df_gk=df_gk,
        df_formations=df_formations,
        df_positions=df_positions,
        df_score=df_score,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scraper WhoScored → parquets")
    parser.add_argument(
        "--leagues", nargs="+", default=_DEFAULT_LEAGUES,
        help=f"Ligas a scrapear (default: {_DEFAULT_LEAGUES})"
    )
    parser.add_argument(
        "--months", nargs="+", default=_DEFAULT_MONTHS,
        help='Meses a scrapear, formato "mmm YYYY" (ej: "oct 2025")'
    )
    parser.add_argument(
        "--season", default=_DEFAULT_SEASON,
        help=f"Temporada (default: {_DEFAULT_SEASON})"
    )
    parser.add_argument(
        "--headless", action="store_true", default=True,
        help="Chrome en modo headless (default: True)"
    )
    parser.add_argument(
        "--no-headless", dest="headless", action="store_false",
        help="Chrome con ventana visible"
    )
    args = parser.parse_args()

    log.info(f"Iniciando scraping — temporada {args.season}")
    log.info(f"Ligas: {args.leagues}")
    log.info(f"Meses: {args.months}")

    driver = build_driver(headless=args.headless)
    try:
        for comp_key in args.leagues:
            try:
                ingest_league(comp_key, args.season, args.months, driver)
            except Exception as exc:
                log.error(f"Error en liga {comp_key}: {exc}")
                continue
    finally:
        quit_driver(driver)

    log.info("Scraping completado.")


if __name__ == "__main__":
    main()
