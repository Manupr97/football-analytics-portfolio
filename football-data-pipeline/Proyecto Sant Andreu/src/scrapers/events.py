"""
events.py
Scraper para descargar y procesar eventos (goles y sustituciones) de partidos.
Guarda siempre el HTML en html/events/<match_id>.html para caché y auditoría.
"""
from typing import List, Tuple, Optional

from config import get_config
from utils.http_client import get_http_client
from utils.logging_config import get_logger
from parsers.event_parser import parse_events_html, GoalEvent, SubstitutionEvent

logger = get_logger("scrapers.events")


def scrape_match_events(
    match_id: int,
    match_url: str,
    home_team_id: int,
    away_team_id: int,
    home_team_name: str = "",
    away_team_name: str = "",
) -> Tuple[List[GoalEvent], List[SubstitutionEvent]]:
    """
    Scrapea los eventos de un partido y guarda el HTML en caché.

    Returns:
        Tupla (goals, substitutions)
    """
    config = get_config()
    client = get_http_client()

    logger.debug(f"Scrapeando eventos: {match_url}")

    html = client.get_html(match_url)

    if not html:
        logger.warning(f"No se pudo obtener eventos para partido {match_id}")
        return [], []

    # Guardar siempre en caché
    html_path = config.EVENTS_HTML_DIR / f"{match_id}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    logger.debug(f"  HTML guardado: {html_path}")

    goals, subs = parse_events_html(html, home_team_id, away_team_id, home_team_name, away_team_name)
    logger.debug(f"  Partido {match_id}: {len(goals)} goles, {len(subs)} sustituciones")
    return goals, subs


def load_cached_events(
    match_id: int,
    home_team_id: int,
    away_team_id: int,
    home_team_name: str = "",
    away_team_name: str = "",
) -> Optional[Tuple[List[GoalEvent], List[SubstitutionEvent]]]:
    """Carga eventos desde HTML cacheado si existe."""
    config = get_config()
    html_path = config.EVENTS_HTML_DIR / f"{match_id}.html"

    if not html_path.exists():
        return None

    html = html_path.read_text(encoding="utf-8")
    return parse_events_html(html, home_team_id, away_team_id, home_team_name, away_team_name)


def scrape_or_load_events(
    match_id: int,
    match_url: str,
    home_team_id: int,
    away_team_id: int,
    home_team_name: str = "",
    away_team_name: str = "",
    use_cache: bool = True,
) -> Tuple[List[GoalEvent], List[SubstitutionEvent]]:
    """
    Obtiene eventos usando caché si está disponible, o scrapea y guarda.
    """
    if use_cache:
        cached = load_cached_events(match_id, home_team_id, away_team_id, home_team_name, away_team_name)
        if cached:
            logger.debug(f"Usando caché para eventos partido {match_id}")
            return cached

    return scrape_match_events(match_id, match_url, home_team_id, away_team_id, home_team_name, away_team_name)
