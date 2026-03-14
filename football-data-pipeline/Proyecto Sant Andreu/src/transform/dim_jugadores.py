"""
dim_jugadores.py
Transformación para crear/actualizar DIM_JUGADORES
Se construye a partir de FACT_APPEARANCES (jugadores únicos)
"""
import pandas as pd
from datetime import datetime

from config import get_config
from utils.parquet_utils import upsert_parquet
from utils.logging_config import get_logger

logger = get_logger("transform.dim_jugadores")


def build_dim_jugadores_from_appearances() -> pd.DataFrame:
    """
    Construye DIM_JUGADORES a partir de FACT_APPEARANCES.
    Extrae jugadores únicos por player_sk.
    """
    config = get_config()
    
    logger.info("=" * 60)
    logger.info("CONSTRUYENDO DIM_JUGADORES")
    logger.info("=" * 60)
    
    if not config.FACT_APPEARANCES_PATH.exists():
        logger.warning("FACT_APPEARANCES no existe. Ejecutar primero el pipeline de alineaciones.")
        return pd.DataFrame()
    
    # Cargar appearances
    appearances = pd.read_parquet(config.FACT_APPEARANCES_PATH)
    logger.info(f"Apariciones cargadas: {len(appearances)}")
    
    # Agrupar por player_sk para obtener jugadores únicos
    # Tomamos el último registro de cada jugador (más reciente)
    jugadores = appearances.sort_values('fecha_actualizacion').groupby('player_sk').last().reset_index()
    
    # Seleccionar columnas relevantes para la dimensión
    dim_jugadores = pd.DataFrame({
        'player_sk': jugadores['player_sk'],
        'player_id': jugadores['player_id'],
        'player_name': jugadores['player_name'],
        'team_id': jugadores['team_id'],
        'team_name': jugadores['team_name'],
        'position': jugadores['position'],
        'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d')
    })
    
    # Tipos
    dim_jugadores['player_sk'] = dim_jugadores['player_sk'].astype('Int64')
    dim_jugadores['player_id'] = dim_jugadores['player_id'].astype('Int64')
    dim_jugadores['team_id'] = dim_jugadores['team_id'].astype('Int64')
    
    # Ordenar por nombre
    dim_jugadores = dim_jugadores.sort_values('player_name').reset_index(drop=True)
    
    # Guardar
    dim_jugadores.to_parquet(config.DIM_JUGADORES_PATH, index=False)
    
    # Estadísticas
    con_id = dim_jugadores['player_id'].notna().sum()
    sin_id = dim_jugadores['player_id'].isna().sum()
    
    logger.info(f"DIM_JUGADORES total: {len(dim_jugadores)} jugadores")
    logger.info(f"  - Con player_id: {con_id}")
    logger.info(f"  - Sin player_id (hash): {sin_id}")
    logger.info(f"  - Equipos: {dim_jugadores['team_id'].nunique()}")
    logger.info(f"Guardado en: {config.DIM_JUGADORES_PATH}")
    
    return dim_jugadores


def get_dim_jugadores() -> pd.DataFrame:
    """Carga DIM_JUGADORES desde disco."""
    config = get_config()
    if config.DIM_JUGADORES_PATH.exists():
        return pd.read_parquet(config.DIM_JUGADORES_PATH)
    return pd.DataFrame()


def update_dim_jugadores() -> pd.DataFrame:
    """Alias para build_dim_jugadores_from_appearances."""
    return build_dim_jugadores_from_appearances()
