"""
matches.py
Scraper para obtener partidos de cada equipo desde BeSoccer
"""
import re
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime

from config import get_config
from utils.http_client import get_http_client
from utils.logging_config import get_logger
from transform.dim_equipos import get_dim_equipos

logger = get_logger("scrapers.matches")

# Meses en español para parsear fechas
MESES_ESP = {
    'ENE': 1, 'FEB': 2, 'MAR': 3, 'ABR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AGO': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DIC': 12
}

# Meses para filtrar paneles (septiembre 2025 a mayo 2026)
MESES_TEMPORADA = [
    'septiembre - 2025', 'octubre - 2025', 'noviembre - 2025', 'diciembre - 2025',
    'enero - 2026', 'febrero - 2026', 'marzo - 2026', 'abril - 2026', 'mayo - 2026'
]


@dataclass
class MatchData:
    """Datos de un partido extraídos del scraping"""
    match_id: int
    match_url: str
    jornada: Optional[int]
    fecha: Optional[str]  # ISO format
    fecha_display: str  # Formato visible (ej: "06 SEP 2025")
    home_team_id: Optional[int]
    home_team_name: str
    away_team_id: Optional[int]
    away_team_name: str
    score_home: Optional[int]
    score_away: Optional[int]
    status: str  # 'Finalizado', 'Programado', 'Aplazado'


def extract_team_id_from_image(img_url: str) -> Optional[int]:
    """Extrae team_id de URL de imagen"""
    if not img_url:
        return None
    match = re.search(r'/(\d+)\.(?:png|jpg)', img_url)
    if match:
        return int(match.group(1))
    return None


def extract_match_id_from_element(element) -> Optional[int]:
    """Extrae match_id del elemento <a>"""
    # Primero intentar desde id="match-XXXXX"
    elem_id = element.get('id', '')
    match = re.search(r'match-(\d+)', elem_id)
    if match:
        return int(match.group(1))
    
    # Fallback: extraer de la URL
    href = element.get('href', '')
    match = re.search(r'/(\d+)$', href)
    if match:
        return int(match.group(1))
    
    return None


def extract_jornada(text: str) -> Optional[int]:
    """Extrae número de jornada de texto como 'Segunda Federación. Jornada 1'"""
    if not text:
        return None
    match = re.search(r'Jornada\s+(\d+)', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def parse_fecha_display(fecha_str: str) -> Optional[str]:
    """
    Convierte fecha del formato '06 SEP 2025' a ISO format '2025-09-06'
    """
    if not fecha_str:
        return None
    try:
        partes = fecha_str.strip().split()
        if len(partes) >= 3:
            dia = int(partes[0])
            mes = MESES_ESP.get(partes[1].upper())
            año = int(partes[2])
            if mes:
                return f"{año}-{mes:02d}-{dia:02d}"
    except:
        pass
    return None


def parse_status(status_text: str, has_score: bool) -> str:
    """Determina el estado del partido"""
    status_lower = status_text.lower() if status_text else ''
    
    if 'fin' in status_lower or 'finalizado' in status_lower:
        return 'Finalizado'
    elif 'aplazado' in status_lower or 'suspendido' in status_lower:
        return 'Aplazado'
    elif has_score:
        return 'Finalizado'
    else:
        return 'Programado'


def is_month_in_season(month_text: str) -> bool:
    """Verifica si el mes está dentro de la temporada"""
    if not month_text:
        return False
    month_lower = month_text.lower().strip()
    return any(m.lower() in month_lower for m in MESES_TEMPORADA)


def scrape_team_matches(team_slug: str, team_id: int = None) -> List[MatchData]:
    """
    Scrapea los partidos de un equipo específico.
    
    Args:
        team_slug: Slug del equipo (ej: "poblense")
        team_id: ID del equipo (opcional, para logging)
    
    Returns:
        Lista de MatchData
    """
    config = get_config()
    client = get_http_client()
    
    url = config.get_team_matches_url(team_slug)
    logger.debug(f"Scrapeando partidos de {team_slug}: {url}")
    
    html = client.get_html(url)
    if not html:
        logger.error(f"No se pudo obtener partidos de {team_slug}")
        return []
    
    soup = BeautifulSoup(html, 'lxml')
    matches = []
    
    # Buscar todos los paneles de meses
    panels = soup.select('div.panel')
    
    for panel in panels:
        # Verificar si es un mes de la temporada
        title_elem = panel.select_one('.panel-title')
        if not title_elem:
            continue
        
        month_text = title_elem.get_text(strip=True)
        if not is_month_in_season(month_text):
            continue
        
        # Buscar partidos dentro del panel
        match_links = panel.select('a.match-link')
        
        for link in match_links:
            try:
                match_id = extract_match_id_from_element(link)
                if not match_id:
                    continue
                
                match_url = link.get('href', '')
                if not match_url.startswith('http'):
                    match_url = config.BESOCCER_BASE_URL + match_url
                
                # Jornada
                middle_info = link.select_one('.middle-info')
                jornada_text = middle_info.get_text(strip=True) if middle_info else ''
                jornada = extract_jornada(jornada_text)
                
                # Solo procesar si es de la competición correcta (Segunda Federación)
                if 'Segunda Federación' not in jornada_text and 'Segunda División RFEF' not in jornada_text:
                    continue
                
                # Fecha
                fecha_elem = link.select_one('.date')
                fecha_display = fecha_elem.get_text(strip=True) if fecha_elem else ''
                fecha_iso = parse_fecha_display(fecha_display)
                
                # También intentar desde starttime
                if not fecha_iso:
                    starttime = link.get('starttime', '')
                    if starttime:
                        fecha_iso = starttime[:10]  # "2025-09-06T17:00:00" -> "2025-09-06"
                
                # Equipos
                team_infos = link.select('.team-info')
                
                home_team_name = ''
                home_team_id = None
                away_team_name = ''
                away_team_id = None
                
                if len(team_infos) >= 2:
                    # Home team (primero, con team_left)
                    home_info = team_infos[0]
                    home_name_elem = home_info.select_one('.team-name .name')
                    home_team_name = home_name_elem.get_text(strip=True) if home_name_elem else ''
                    home_img = home_info.select_one('img')
                    if home_img:
                        home_team_id = extract_team_id_from_image(home_img.get('src', ''))
                        if home_team_id is None:
                            logger.warning(
                                f"[team_id=None] match_id={match_id} equipo local '{home_team_name}': "
                                f"no se pudo extraer team_id de '{home_img.get('src', '')}'. "
                                f"Posible cambio en el CDN de BeSoccer."
                            )

                    # Away team (segundo)
                    away_info = team_infos[1]
                    away_name_elem = away_info.select_one('.team-name .name')
                    away_team_name = away_name_elem.get_text(strip=True) if away_name_elem else ''
                    away_img = away_info.select_one('img')
                    if away_img:
                        away_team_id = extract_team_id_from_image(away_img.get('src', ''))
                        if away_team_id is None:
                            logger.warning(
                                f"[team_id=None] match_id={match_id} equipo visitante '{away_team_name}': "
                                f"no se pudo extraer team_id de '{away_img.get('src', '')}'. "
                                f"Posible cambio en el CDN de BeSoccer."
                            )
                
                # Marcador
                marker = link.select_one('.marker')
                score_home = None
                score_away = None
                
                if marker:
                    r1 = marker.select_one('.r1')
                    r2 = marker.select_one('.r2')
                    if r1 and r2:
                        try:
                            score_home = int(r1.get_text(strip=True))
                            score_away = int(r2.get_text(strip=True))
                        except:
                            pass
                
                # Estado
                status_elem = link.select_one('.tag')
                status_text = status_elem.get_text(strip=True) if status_elem else ''
                status = parse_status(status_text, score_home is not None)
                
                match_data = MatchData(
                    match_id=match_id,
                    match_url=match_url,
                    jornada=jornada,
                    fecha=fecha_iso,
                    fecha_display=fecha_display,
                    home_team_id=home_team_id,
                    home_team_name=home_team_name,
                    away_team_id=away_team_id,
                    away_team_name=away_team_name,
                    score_home=score_home,
                    score_away=score_away,
                    status=status
                )
                matches.append(match_data)
                
            except Exception as e:
                logger.warning(f"Error procesando partido en {team_slug}: {e}")
                continue
    
    logger.debug(f"  {team_slug}: {len(matches)} partidos encontrados")
    return matches


def scrape_all_matches() -> List[MatchData]:
    """
    Scrapea partidos de TODOS los equipos y elimina duplicados.
    
    Returns:
        Lista de MatchData únicos (por match_id)
    """
    config = get_config()
    
    logger.info("=" * 60)
    logger.info("SCRAPEANDO PARTIDOS DE TODOS LOS EQUIPOS")
    logger.info("=" * 60)
    
    # Obtener equipos
    df_equipos = get_dim_equipos()
    
    if df_equipos.empty:
        logger.error("No hay equipos en DIM_EQUIPOS")
        return []
    
    all_matches: Dict[int, MatchData] = {}  # match_id -> MatchData (para deduplicar)
    
    for _, equipo in df_equipos.iterrows():
        team_slug = equipo['slug']
        team_id = equipo['team_id']
        team_name = equipo['nombre_equipo']
        
        logger.info(f"Scrapeando: {team_name} ({team_slug})")
        
        matches = scrape_team_matches(team_slug, team_id)
        
        # Agregar al diccionario (deduplica automáticamente por match_id)
        for m in matches:
            if m.match_id not in all_matches:
                all_matches[m.match_id] = m
        
        logger.info(f"  → {len(matches)} partidos, Total únicos: {len(all_matches)}")
    
    # Convertir a lista y ordenar por jornada
    result = sorted(all_matches.values(), key=lambda x: (x.jornada or 99, x.match_id))
    
    logger.info(f"Total partidos únicos: {len(result)}")
    
    return result


# Test
if __name__ == "__main__":
    # Test con un solo equipo primero
    matches = scrape_team_matches("poblense")
    print(f"\nPartidos del Poblense: {len(matches)}")
    for m in matches[:5]:
        print(f"  J{m.jornada}: {m.home_team_name} {m.score_home}-{m.score_away} {m.away_team_name} ({m.status})")
