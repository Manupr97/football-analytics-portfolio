"""
player_utils.py
Funciones comunes para manejo de identificadores de jugadores.
"""
import re
import hashlib
import unicodedata
from typing import Optional


def _normalize_for_hash(text: str) -> str:
    """
    Normaliza un texto para usarlo como clave de hash estable:
    elimina tildes, pasa a mayúsculas, colapsa espacios.
    Así 'Martínez' y 'Martinez' generan el mismo hash.
    """
    nfkd = unicodedata.normalize('NFKD', text)
    ascii_str = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', ascii_str).strip().upper()


def generate_player_sk(player_id: Optional[int], player_name: str, team_name: str = "") -> int:
    """
    Genera un player_sk único y estable.

    - Si tiene player_id, lo usa directamente (valor positivo).
    - Si no tiene player_id, genera un hash negativo estable basado en
      nombre+equipo normalizados (sin tildes, mayúsculas).

    Args:
        player_id: ID del jugador en BeSoccer (puede ser None)
        player_name: Nombre del jugador
        team_name: Nombre del equipo (para desambiguar jugadores con mismo nombre)

    Returns:
        player_sk: Entero positivo (si tiene ID) o negativo (hash)
    """
    if player_id is not None:
        return player_id

    # Normalizar antes del hash para que variantes de acento sean idénticas
    key = f"{_normalize_for_hash(player_name)}_{_normalize_for_hash(team_name)}"
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return -int(h[:8], 16)


def extract_player_id_from_url(url: str) -> Optional[int]:
    """
    Extrae player_id de una URL de BeSoccer.

    Formatos soportados:
        - https://es.besoccer.com/jugador/nombre-apellido-123456
        - https://es.besoccer.com/jugador/nombre-123456/
    """
    if not url:
        return None

    match = re.search(r'-(\d+)/?$', url.rstrip('/'))
    if match:
        return int(match.group(1))
    return None


def extract_team_id_from_image(img_url: str) -> Optional[int]:
    """
    Extrae team_id de una URL de imagen de escudo.

    Formatos soportados:
        - https://cdn.resfu.com/img_data/equipos/1981.png
        - https://cdn.resfu.com/img_data/equipos/1981.jpg
    """
    if not img_url:
        return None

    match = re.search(r'/equipos/(\d+)\.', img_url)
    if match:
        return int(match.group(1))
    return None


def parse_minute(minute_text: str) -> Optional[int]:
    """
    Convierte texto de minutos a entero.

    Formatos soportados:
        - "68'" -> 68
        - "90'+4" -> 94
        - "45+2'" -> 47
        - "90+3" -> 93
    """
    if not minute_text:
        return None

    text = minute_text.strip().replace("'", "")

    # Formato "90+4" o "45+2"
    match = re.search(r'(\d+)\s*\+\s*(\d+)', text)
    if match:
        base = int(match.group(1))
        added = int(match.group(2))
        return base + added

    # Formato simple "68"
    match = re.search(r'(\d+)', text)
    if match:
        return int(match.group(1))

    return None
