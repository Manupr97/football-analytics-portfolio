"""
event_parser.py
Parser para extraer eventos (goles y sustituciones) del HTML de BeSoccer
"""
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
from dataclasses import dataclass

from utils.logging_config import get_logger
from utils.player_utils import (
    generate_player_sk,
    extract_player_id_from_url,
    extract_team_id_from_image,
    parse_minute
)

logger = get_logger("parsers.events")


@dataclass
class GoalEvent:
    """Datos de un gol"""
    minute: int
    minute_display: str
    scorer_player_id: Optional[int]
    scorer_player_sk: int
    scorer_name: str
    assist_player_id: Optional[int]
    assist_player_sk: Optional[int]
    assist_name: Optional[str]
    team_id: Optional[int]
    team_name: str
    side: str  # 'local' o 'visitor'
    goal_type: str  # 'normal', 'penalty', 'own_goal'


@dataclass
class SubstitutionEvent:
    """Datos de una sustitución"""
    minute: int
    player_in_id: Optional[int]
    player_in_sk: int
    player_in_name: str
    player_out_id: Optional[int]
    player_out_sk: int
    player_out_name: str
    team_id: Optional[int]
    team_name: str
    side: str  # 'local' o 'visitor'


def parse_goals(
    soup: BeautifulSoup,
    home_team_id: int = None,
    away_team_id: int = None,
    home_team_name: str = "",
    away_team_name: str = "",
) -> List[GoalEvent]:
    """
    Parsea la sección de goles.

    Args:
        soup: BeautifulSoup del HTML
        home_team_id: ID del equipo local (de DIM_PARTIDOS)
        away_team_id: ID del equipo visitante (de DIM_PARTIDOS)
        home_team_name: Nombre del equipo local (para generar player_sk estable)
        away_team_name: Nombre del equipo visitante (para generar player_sk estable)
    """
    goals = []
    
    goals_section = soup.select_one('#events-goals')
    if not goals_section:
        logger.debug("No se encontró sección de goles")
        return goals
    
    rows = goals_section.select('.table-played-match')
    
    for row in rows:
        try:
            # Minuto
            min_elem = row.select_one('.min')
            minute_display = min_elem.get_text(strip=True) if min_elem else ''
            minute = parse_minute(minute_display)
            if minute is None:
                continue
            
            # Side (local o visitor)
            arrow = row.select_one('span.arrow')
            if arrow:
                side = 'local' if 'left' in arrow.get('class', []) else 'visitor'
            else:
                left_side = row.select_one('.col-side.left .col-name')
                side = 'local' if left_side else 'visitor'
            
            # Tipo de gol
            event_img = row.select_one('.event-wrapper img')
            goal_type = 'normal'
            if event_img:
                alt = event_img.get('alt', '').lower()
                if 'propia' in alt:
                    goal_type = 'own_goal'
                elif 'penal' in alt:
                    goal_type = 'penalty'
            
            # Team ID: primero intentar popup, si no usar side + params
            team_id = None
            popup = row.select_one('.popup-box')
            if popup:
                shield_img = popup.select_one('.shield img')
                if shield_img:
                    team_id = extract_team_id_from_image(shield_img.get('src', ''))
            
            # Fallback: usar team_ids pasados por parámetro según side
            if team_id is None:
                if side == 'local' and home_team_id:
                    team_id = home_team_id
                elif side == 'visitor' and away_team_id:
                    team_id = away_team_id
                else:
                    logger.warning(
                        f"[team_id=None] Gol min={minute_display} side={side}: "
                        f"no se pudo extraer team_id del popup ni del fallback. "
                        f"Verificar HTML del partido."
                    )
            
            # Goleador y Asistente
            scorer_name = ''
            scorer_player_id = None
            assist_name = None
            assist_player_id = None
            
            if popup:
                items = popup.select('ul.item-list li')
                
                for item in items:
                    link = item.select_one('a.main-text')
                    if not link:
                        continue
                    
                    name = link.get_text(strip=True)
                    url = link.get('href', '')
                    player_id = extract_player_id_from_url(url)
                    
                    event_icon = item.select_one('.img-ico')
                    if event_icon:
                        classes = ' '.join(event_icon.get('class', []))
                        if 'event-1' in classes:
                            scorer_name = name
                            scorer_player_id = player_id
                        elif 'event-22' in classes:
                            assist_name = name
                            assist_player_id = player_id
            
            # Fallback: buscar en links de jugador (priorizar a.name)
            if not scorer_name:
                # Primero buscar a.name (tiene el texto)
                scorer_link = row.select_one('a.name[href*="/jugador/"]')
                if not scorer_link:
                    # Fallback: cualquier link con texto
                    for link in row.select('a[href*="/jugador/"]'):
                        if link.get_text(strip=True):
                            scorer_link = link
                            break
                
                if scorer_link:
                    scorer_name = scorer_link.get_text(strip=True)
                    scorer_url = scorer_link.get('href', '')
                    scorer_player_id = extract_player_id_from_url(scorer_url)
                
                # Asistente
                assist_link = row.select_one('a.color-grey2[href*="/jugador/"]')
                if assist_link:
                    assist_name = assist_link.get_text(strip=True)
                    assist_url = assist_link.get('href', '')
                    assist_player_id = extract_player_id_from_url(assist_url)
            
            # Nombre del equipo según side (para SK estable sin player_id)
            team_name = home_team_name if side == 'local' else away_team_name

            scorer_player_sk = generate_player_sk(scorer_player_id, scorer_name, team_name)
            assist_player_sk = generate_player_sk(assist_player_id, assist_name, team_name) if assist_name else None

            goal = GoalEvent(
                minute=minute,
                minute_display=minute_display,
                scorer_player_id=scorer_player_id,
                scorer_player_sk=scorer_player_sk,
                scorer_name=scorer_name,
                assist_player_id=assist_player_id,
                assist_player_sk=assist_player_sk,
                assist_name=assist_name,
                team_id=team_id,
                team_name=team_name,
                side=side,
                goal_type=goal_type
            )
            goals.append(goal)
            
        except Exception as e:
            logger.warning(f"Error parseando gol: {e}")
            continue
    
    logger.debug(f"Goles parseados: {len(goals)}")
    return goals


def parse_substitutions(
    soup: BeautifulSoup,
    home_team_id: int = None,
    away_team_id: int = None,
    home_team_name: str = "",
    away_team_name: str = "",
) -> List[SubstitutionEvent]:
    """
    Parsea la sección de sustituciones.

    Args:
        soup: BeautifulSoup del HTML
        home_team_id: ID del equipo local
        away_team_id: ID del equipo visitante
        home_team_name: Nombre del equipo local (para generar player_sk estable)
        away_team_name: Nombre del equipo visitante (para generar player_sk estable)
    """
    substitutions = []
    
    subs_section = soup.select_one('#events-changes')
    if not subs_section:
        logger.debug("No se encontró sección de sustituciones")
        return substitutions
    
    rows = subs_section.select('.table-played-match')
    
    for row in rows:
        try:
            min_elem = row.select_one('.min')
            minute = parse_minute(min_elem.get_text(strip=True)) if min_elem else None
            if minute is None:
                continue
            
            # Side
            arrow = row.select_one('span.arrow')
            if arrow:
                side = 'local' if 'left' in arrow.get('class', []) else 'visitor'
            else:
                left_side = row.select_one('.col-side.left .col-name')
                side = 'local' if left_side else 'visitor'
            
            popup = row.select_one('.popup-box')
            
            player_in_name = ''
            player_in_id = None
            player_out_name = ''
            player_out_id = None
            team_id = None
            
            if popup:
                shield_img = popup.select_one('.shield img')
                if shield_img:
                    team_id = extract_team_id_from_image(shield_img.get('src', ''))
                
                items = popup.select('ul.item-list li')
                
                for item in items:
                    link = item.select_one('a.main-text')
                    if not link:
                        continue
                    
                    name = link.get_text(strip=True)
                    url = link.get('href', '')
                    player_id = extract_player_id_from_url(url)
                    
                    event_icon = item.select_one('.img-ico')
                    if event_icon:
                        classes = ' '.join(event_icon.get('class', []))
                        if 'event-19' in classes:
                            player_in_name = name
                            player_in_id = player_id
                        elif 'event-18' in classes:
                            player_out_name = name
                            player_out_id = player_id
            
            # Fallback team_id usando side
            if team_id is None:
                if side == 'local' and home_team_id:
                    team_id = home_team_id
                elif side == 'visitor' and away_team_id:
                    team_id = away_team_id
                else:
                    logger.warning(
                        f"[team_id=None] Sustitución min={minute} side={side}: "
                        f"no se pudo extraer team_id del popup ni del fallback. "
                        f"Verificar HTML del partido."
                    )
            
            # Fallback jugadores
            if not player_in_name:
                name_links = row.select('a.name')
                if len(name_links) >= 1:
                    player_in_name = name_links[0].get_text(strip=True)
                    player_in_id = extract_player_id_from_url(name_links[0].get('href', ''))
                if len(name_links) >= 2:
                    player_out_name = name_links[1].get_text(strip=True)
                    player_out_id = extract_player_id_from_url(name_links[1].get('href', ''))
            
            # Nombre del equipo según side (para SK estable sin player_id)
            team_name = home_team_name if side == 'local' else away_team_name

            player_in_sk = generate_player_sk(player_in_id, player_in_name, team_name)
            player_out_sk = generate_player_sk(player_out_id, player_out_name, team_name)

            sub = SubstitutionEvent(
                minute=minute,
                player_in_id=player_in_id,
                player_in_sk=player_in_sk,
                player_in_name=player_in_name,
                player_out_id=player_out_id,
                player_out_sk=player_out_sk,
                player_out_name=player_out_name,
                team_id=team_id,
                team_name=team_name,
                side=side
            )
            substitutions.append(sub)
            
        except Exception as e:
            logger.warning(f"Error parseando sustitución: {e}")
            continue
    
    logger.debug(f"Sustituciones parseadas: {len(substitutions)}")
    return substitutions


def parse_events_html(
    html: str,
    home_team_id: int = None,
    away_team_id: int = None,
    home_team_name: str = "",
    away_team_name: str = "",
) -> Tuple[List[GoalEvent], List[SubstitutionEvent]]:
    """
    Parsea el HTML completo de eventos.

    Args:
        html: HTML de la página del partido
        home_team_id: ID del equipo local (de DIM_PARTIDOS)
        away_team_id: ID del equipo visitante (de DIM_PARTIDOS)
        home_team_name: Nombre del equipo local (para player_sk estable)
        away_team_name: Nombre del equipo visitante (para player_sk estable)

    Returns:
        Tupla (goals, substitutions)
    """
    soup = BeautifulSoup(html, 'lxml')

    goals = parse_goals(soup, home_team_id, away_team_id, home_team_name, away_team_name)
    substitutions = parse_substitutions(soup, home_team_id, away_team_id, home_team_name, away_team_name)

    return goals, substitutions
