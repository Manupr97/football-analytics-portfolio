"""
lineups.py
Scraper para descargar y procesar alineaciones de partidos.
Guarda siempre el HTML en html/lineups/<match_id>.html para caché y auditoría.
"""
from typing import List, Optional, Tuple

from config import get_config
from utils.http_client import get_http_client
from utils.logging_config import get_logger
from parsers.lineup_parser import parse_lineup_html, PlayerAppearance

logger = get_logger("scrapers.lineups")


def get_lineup_url(match_url: str) -> str:
    """Genera la URL de alineaciones a partir de la URL del partido."""
    return match_url.rstrip('/') + '/alineaciones'


def scrape_match_lineups(
    match_id: int,
    match_url: str,
) -> Tuple[List[PlayerAppearance], List[PlayerAppearance]]:
    """
    Scrapea las alineaciones de un partido y guarda el HTML en caché.

    Returns:
        Tupla (jugadores_local, jugadores_visitor)
    """
    config = get_config()
    client = get_http_client()

    lineup_url = get_lineup_url(match_url)
    logger.debug(f"Scrapeando alineaciones: {lineup_url}")

    html = client.get_html(lineup_url)

    if not html:
        logger.warning(f"No se pudo obtener alineaciones para partido {match_id}")
        return [], []

    # Guardar siempre en caché
    html_path = config.LINEUPS_HTML_DIR / f"{match_id}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    logger.debug(f"  HTML guardado: {html_path}")

    local, visitor = parse_lineup_html(html)
    logger.debug(f"  Partido {match_id}: {len(local)} local, {len(visitor)} visitor")
    return local, visitor


def load_cached_lineups(match_id: int):
    """Carga alineaciones desde HTML cacheado si existe."""
    config = get_config()
    html_path = config.LINEUPS_HTML_DIR / f"{match_id}.html"

    if not html_path.exists():
        return None

    html = html_path.read_text(encoding="utf-8")
    return parse_lineup_html(html)


def scrape_or_load_lineups(
    match_id: int,
    match_url: str,
    use_cache: bool = True
) -> Tuple[List[PlayerAppearance], List[PlayerAppearance]]:
    """
    Obtiene alineaciones usando caché si está disponible, o scrapea y guarda.
    """
    if use_cache:
        cached = load_cached_lineups(match_id)
        if cached:
            logger.debug(f"Usando caché para partido {match_id}")
            return cached

    return scrape_match_lineups(match_id, match_url)


# Test
if __name__ == "__main__":
    match_id = 202621164
    match_url = "https://es.besoccer.com/partido/poblense/espanyol-b/202621164"

    local, visitor = scrape_or_load_lineups(match_id, match_url)

    print(f"\nPartido {match_id}:")
    print(f"  Local: {len(local)} jugadores")
    print(f"  Visitor: {len(visitor)} jugadores")

    print("\nTitulares LOCAL:")
    for p in [x for x in local if x.is_starter]:
        print(f"  #{p.shirt_number:>2} {p.player_name}")
