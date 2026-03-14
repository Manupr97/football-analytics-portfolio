"""
lineup_parser.py
Parser para extraer alineaciones (titulares y suplentes) del HTML de BeSoccer
"""
import json
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup
from dataclasses import dataclass

from utils.logging_config import get_logger
from utils.player_utils import generate_player_sk, extract_player_id_from_url, parse_minute

logger = get_logger("parsers.lineup")


@dataclass
class PlayerAppearance:
    """Datos de aparición de un jugador en un partido"""
    player_id: Optional[int]
    player_sk: int  # Siempre tiene valor (ID o hash)
    player_name: str
    player_url: str
    player_image_url: str
    team_name: str
    position: str  # Posición (Portero, Defensa, etc.)
    shirt_number: Optional[int]  # Dorsal
    is_starter: bool  # True = titular, False = suplente
    minute_in: Optional[int]  # Minuto de entrada (0 para titulares, N para suplentes que entran)
    side: str  # 'local' o 'visitor'


def parse_json_ld(script_tag) -> Dict:
    """Parsea el JSON-LD de un script tag"""
    if not script_tag:
        return {}
    try:
        text = script_tag.string or script_tag.get_text()
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.debug(f"Error parseando JSON-LD: {e}")
        return {}
    except Exception as e:
        logger.debug(f"Error inesperado en JSON-LD: {e}")
        return {}


def parse_shirt_number(element, selector: str) -> Optional[int]:
    """Extrae dorsal de un elemento usando el selector dado"""
    if not element:
        return None

    num_elem = element.select_one(selector)
    if num_elem:
        text = num_elem.get_text(strip=True)
        try:
            return int(text)
        except ValueError:
            logger.debug(f"No se pudo convertir dorsal a int: '{text}'")
    return None


# Mapeo de abreviaturas de posición en suplentes a nombres completos
POSITION_ABBREV_MAP = {
    'PT': 'Portero',
    'POR': 'Portero',
    'DEF': 'Defensa',
    'MED': 'midfielder',
    'DEL': 'Delantero',
}


def parse_bench_position(bench_element) -> str:
    """
    Extrae la posición de un suplente desde el .role-box.
    En suplentes, el JSON-LD no tiene jobtitle, pero la posición
    aparece como texto en .role-box > span.t-up (ej: "14 DEL").

    El HTML es:
        <span class="t-up">
            <span class="number bold mr3">14</span>
            DEL
        </span>

    get_text(strip=True) devuelve "14DEL" (sin espacio),
    por eso usamos separator=' ' para forzar "14 DEL".
    """
    role_box = bench_element.select_one('.role-box span.t-up')
    if not role_box:
        return ''

    # separator=' ' fuerza espacio entre nodos hijos: "14 DEL"
    full_text = role_box.get_text(separator=' ', strip=True)
    parts = full_text.split()
    for part in parts:
        abbrev = part.strip().upper()
        if abbrev in POSITION_ABBREV_MAP:
            return POSITION_ABBREV_MAP[abbrev]

    # Fallback: devolver la parte no numérica tal cual
    for part in parts:
        if not part.isdigit():
            return part

    return ''


def parse_starters(soup: BeautifulSoup, side: str) -> List[PlayerAppearance]:
    """
    Parsea titulares de un equipo.
    
    Args:
        soup: BeautifulSoup del HTML
        side: 'local' o 'visitor'
    
    Returns:
        Lista de PlayerAppearance para titulares
    """
    players = []
    
    lineup = soup.select_one(f'ul.lineup.{side}')
    if not lineup:
        logger.warning(f"No se encontró lineup para {side}")
        return players
    
    for li in lineup.select('li[class^="pos"]'):
        try:
            # JSON-LD
            script = li.select_one('script[type="application/ld+json"]')
            data = parse_json_ld(script)
            
            if not data:
                continue
            
            player_name = data.get('name', '')
            player_url = data.get('url', '')
            player_image = data.get('image', '')
            team_name = data.get('worksFor', '')
            position = data.get('jobtitle', '')
            
            player_id = extract_player_id_from_url(player_url)
            
            # Generar player_sk (siempre tiene valor)
            player_sk = generate_player_sk(player_id, player_name, team_name)
            
            # Dorsal - en titulares está en .num-lineups span.bold
            shirt_number = parse_shirt_number(li, '.num-lineups span.bold')
            
            player = PlayerAppearance(
                player_id=player_id,
                player_sk=player_sk,
                player_name=player_name,
                player_url=player_url,
                player_image_url=player_image,
                team_name=team_name,
                position=position,
                shirt_number=shirt_number,
                is_starter=True,
                minute_in=0,  # Titulares entran en minuto 0
                side=side
            )
            players.append(player)
            
        except Exception as e:
            logger.warning(f"Error parseando titular {side}: {e}")
            continue
    
    logger.debug(f"  Titulares {side}: {len(players)}")
    return players


def parse_substitutes(soup: BeautifulSoup, side: str) -> List[PlayerAppearance]:
    """
    Parsea suplentes de un equipo.
    
    Args:
        soup: BeautifulSoup del HTML
        side: 'local' o 'visitor'
    
    Returns:
        Lista de PlayerAppearance para suplentes
    """
    players = []
    
    # Suplentes están en a.col-bench.{side}
    bench_players = soup.select(f'a.col-bench.{side}')
    
    for bench in bench_players:
        try:
            # JSON-LD
            script = bench.select_one('script[type="application/ld+json"]')
            data = parse_json_ld(script)
            
            if not data:
                continue
            
            player_name = data.get('name', '')
            player_url = data.get('url', '')
            player_image = data.get('image', '')
            team_name = data.get('worksFor', '')
            position = data.get('jobtitle', '')
            
            player_id = extract_player_id_from_url(player_url)

            # Generar player_sk (siempre tiene valor)
            player_sk = generate_player_sk(player_id, player_name, team_name)

            # Posición: jobtitle viene vacío en suplentes, extraer de .role-box
            if not position:
                position = parse_bench_position(bench)

            # Dorsal suplentes - en .role-box .number.bold.mr3
            shirt_number = parse_shirt_number(bench, '.role-box .number.bold.mr3')

            # Fallback: buscar cualquier .number.bold
            if shirt_number is None:
                shirt_number = parse_shirt_number(bench, '.number.bold')

            # El minuto de entrada se enriquece después desde FACT_SUBSTITUTIONS.
            # Aquí solo marcamos si el suplente llegó a entrar (icono visible).
            entered = bench.select_one('img[alt="Entra"]') is not None
            minute_in = None  # Se rellena en run_pipeline al cruzar con substitutions
            
            player = PlayerAppearance(
                player_id=player_id,
                player_sk=player_sk,
                player_name=player_name,
                player_url=player_url,
                player_image_url=player_image,
                team_name=team_name,
                position=position,
                shirt_number=shirt_number,
                is_starter=False,
                minute_in=minute_in,  # Se rellena desde FACT_SUBSTITUTIONS en el pipeline
                side=side
            )
            players.append(player)
            
        except Exception as e:
            logger.warning(f"Error parseando suplente {side}: {e}")
            continue
    
    logger.debug(f"  Suplentes {side}: {len(players)}")
    return players


def parse_lineup_html(html: str) -> Tuple[List[PlayerAppearance], List[PlayerAppearance]]:
    """
    Parsea el HTML completo de alineaciones.
    
    Args:
        html: HTML de la página de alineaciones
    
    Returns:
        Tupla (jugadores_local, jugadores_visitor)
    """
    soup = BeautifulSoup(html, 'lxml')
    
    # Titulares
    starters_local = parse_starters(soup, 'local')
    starters_visitor = parse_starters(soup, 'visitor')
    
    # Suplentes
    subs_local = parse_substitutes(soup, 'local')
    subs_visitor = parse_substitutes(soup, 'visitor')
    
    # Combinar
    local_players = starters_local + subs_local
    visitor_players = starters_visitor + subs_visitor
    
    logger.debug(f"Total local: {len(local_players)}, visitor: {len(visitor_players)}")
    
    return local_players, visitor_players


# Test
if __name__ == "__main__":
    from pathlib import Path
    
    # Leer HTML de ejemplo
    html_path = Path(r"C:\Users\manue\OneDrive\Sports Data Campus\Máster Python\Proyecto Sant Andreu\data_raw\lineups\alineaciones_ejemplo_raw.html")
    
    if html_path.exists():
        html = html_path.read_text(encoding='utf-8')
        local, visitor = parse_lineup_html(html)
        
        print(f"\nJugadores LOCAL: {len(local)}")
        for p in local:
            status = "Titular" if p.is_starter else f"Suplente (entra {p.minute_in}')" if p.minute_in else "Suplente"
            id_info = f"ID:{p.player_id}" if p.player_id else f"SK:{p.player_sk} (sin ID)"
            print(f"  #{p.shirt_number or '?':>2} {p.player_name:<20} {status:<25} {id_info}")
        
        print(f"\nJugadores VISITOR: {len(visitor)}")
        for p in visitor:
            status = "Titular" if p.is_starter else f"Suplente (entra {p.minute_in}')" if p.minute_in else "Suplente"
            id_info = f"ID:{p.player_id}" if p.player_id else f"SK:{p.player_sk} (sin ID)"
            print(f"  #{p.shirt_number or '?':>2} {p.player_name:<20} {status:<25} {id_info}")
