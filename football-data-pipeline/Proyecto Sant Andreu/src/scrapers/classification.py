"""
classification.py
Scraper para obtener equipos desde la clasificación de BeSoccer
"""
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from dataclasses import dataclass

from config import get_config
from utils.http_client import get_http_client
from utils.logging_config import get_logger

logger = get_logger("scrapers.classification")


@dataclass
class TeamData:
    """Datos de un equipo extraídos de la clasificación"""
    team_id: int
    nombre: str
    slug: str
    url_equipo: str
    url_escudo: str
    posicion: int


def extract_team_id_from_image(img_url: str) -> Optional[int]:
    """
    Extrae el team_id de la URL de la imagen del escudo.
    Ejemplo: https://cdn.resfu.com/img_data/equipos/1981.png -> 1981
    """
    if not img_url:
        return None
    match = re.search(r'/equipos/(\d+)\.', img_url)
    if match:
        return int(match.group(1))
    return None


def extract_slug_from_url(url: str) -> Optional[str]:
    """
    Extrae el slug del equipo de la URL.
    Ejemplo: https://es.besoccer.com/equipo/sant-andreu -> sant-andreu
    """
    if not url:
        return None
    match = re.search(r'/equipo/([^/]+)/?$', url)
    if match:
        return match.group(1)
    return None


def scrape_classification() -> List[TeamData]:
    """
    Scrapea la página de clasificación y extrae todos los equipos.

    Returns:
        Lista de TeamData con la información de cada equipo
    """
    config = get_config()
    client = get_http_client()

    logger.info(f"Scrapeando clasificación: {config.COMPETITION_URL}")

    html = client.get_html(config.COMPETITION_URL)
    if not html:
        logger.error("No se pudo obtener la página de clasificación")
        return []

    # Guardar HTML raw para auditoría
    raw_path = config.CLASSIFICATION_RAW_DIR / "clasificacion_latest.html"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, 'lxml')

    classification_div = soup.select_one('#classificationTables')
    if not classification_div:
        logger.error("No se encontró el div de clasificación (#classificationTables)")
        return []

    teams = []
    rows = classification_div.select('tr.row-body')

    logger.info(f"Encontradas {len(rows)} filas de equipos")

    null_team_id_count = 0

    for idx, row in enumerate(rows, start=1):
        try:
            pos_div = row.select_one('td.number-box div')
            posicion = int(pos_div.get_text(strip=True)) if pos_div else idx

            img = row.select_one('td.td-shield img')
            url_escudo = img.get('src', '') if img else ''
            team_id = extract_team_id_from_image(url_escudo)

            if team_id is None:
                null_team_id_count += 1
                logger.warning(
                    f"[team_id=None] Fila {idx}: no se pudo extraer team_id "
                    f"de la imagen. url_escudo='{url_escudo}'. "
                    f"Posible cambio en el CDN o formato de URL de BeSoccer."
                )

            link = row.select_one('td.name a[data-cy="team"]')
            if not link:
                continue

            url_equipo = link.get('href', '')
            if not url_equipo.startswith('http'):
                url_equipo = config.BESOCCER_BASE_URL + url_equipo

            nombre_span = link.select_one('span.team-name')
            nombre = nombre_span.get_text(strip=True) if nombre_span else link.get_text(strip=True)

            slug = extract_slug_from_url(url_equipo)

            if team_id and nombre:
                team = TeamData(
                    team_id=team_id,
                    nombre=nombre,
                    slug=slug or '',
                    url_equipo=url_equipo,
                    url_escudo=url_escudo,
                    posicion=posicion
                )
                teams.append(team)
                logger.debug(f"  {posicion}. {nombre} (ID: {team_id})")

        except Exception as e:
            logger.warning(f"Error procesando fila {idx}: {e}")
            continue

    if null_team_id_count > 0:
        logger.error(
            f"ALERTA: {null_team_id_count} equipos sin team_id. "
            f"Verificar si BeSoccer cambió el formato de URLs de imágenes."
        )

    logger.info(f"Extraídos {len(teams)} equipos de la clasificación")
    return teams


def get_teams_dict() -> Dict[int, TeamData]:
    """Retorna un diccionario de equipos indexado por team_id."""
    teams = scrape_classification()
    return {t.team_id: t for t in teams}


# Test
if __name__ == "__main__":
    teams = scrape_classification()
    print(f"\nEquipos encontrados: {len(teams)}")
    print("-" * 60)
    for t in teams:
        print(f"{t.posicion:2}. {t.nombre:<25} ID: {t.team_id:<6} Slug: {t.slug}")
