"""
fact_substitutions.py
Transformación para crear/actualizar FACT_SUBSTITUTIONS
"""
import pandas as pd
from datetime import datetime
from typing import List

from config import get_config
from parsers.event_parser import SubstitutionEvent
from utils.parquet_utils import upsert_parquet
from utils.logging_config import get_logger

logger = get_logger("transform.fact_substitutions")


def substitutions_to_dataframe(subs: List[SubstitutionEvent], match_id: int) -> pd.DataFrame:
    """
    Convierte lista de SubstitutionEvent a DataFrame.
    """
    if not subs:
        return pd.DataFrame()
    
    data = []
    for s in subs:
        data.append({
            'match_id': match_id,
            'minute': s.minute,
            'player_in_id': s.player_in_id,
            'player_in_sk': s.player_in_sk,
            'player_in_name': s.player_in_name,
            'player_out_id': s.player_out_id,
            'player_out_sk': s.player_out_sk,
            'player_out_name': s.player_out_name,
            'team_id': s.team_id,
            'team_name': s.team_name,
            'side': s.side,
            'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d')
        })
    
    df = pd.DataFrame(data)
    
    # Tipos
    df['match_id'] = df['match_id'].astype('Int64')
    df['minute'] = df['minute'].astype('Int64')
    df['player_in_id'] = df['player_in_id'].astype('Int64')
    df['player_in_sk'] = df['player_in_sk'].astype('Int64')
    df['player_out_id'] = df['player_out_id'].astype('Int64')
    df['player_out_sk'] = df['player_out_sk'].astype('Int64')
    df['team_id'] = df['team_id'].astype('Int64')
    
    return df


def update_fact_substitutions(all_subs: List[tuple]) -> pd.DataFrame:
    """
    Actualiza FACT_SUBSTITUTIONS con nuevas sustituciones.
    
    Args:
        all_subs: Lista de tuplas (match_id, List[SubstitutionEvent])
    
    Returns:
        DataFrame actualizado
    """
    config = get_config()
    
    logger.info("=" * 60)
    logger.info("ACTUALIZANDO FACT_SUBSTITUTIONS")
    logger.info("=" * 60)
    
    # Convertir todas las sustituciones a DataFrame
    dfs = []
    for match_id, subs in all_subs:
        df = substitutions_to_dataframe(subs, match_id)
        if not df.empty:
            dfs.append(df)
    
    if not dfs:
        logger.warning("No hay sustituciones para procesar")
        if config.FACT_SUBSTITUTIONS_PATH.exists():
            return pd.read_parquet(config.FACT_SUBSTITUTIONS_PATH)
        return pd.DataFrame()
    
    df_new = pd.concat(dfs, ignore_index=True)
    logger.info(f"Sustituciones nuevas a procesar: {len(df_new)}")
    
    # Upsert: clave compuesta match_id + minute + player_in_sk
    df_result = upsert_parquet(
        df_new=df_new,
        path=config.FACT_SUBSTITUTIONS_PATH,
        keys=['match_id', 'minute', 'player_in_sk']
    )
    
    # Estadísticas
    logger.info(f"FACT_SUBSTITUTIONS total: {len(df_result)} sustituciones")
    logger.info(f"Guardado en: {config.FACT_SUBSTITUTIONS_PATH}")
    
    return df_result


def get_fact_substitutions() -> pd.DataFrame:
    """Carga FACT_SUBSTITUTIONS desde disco."""
    config = get_config()
    if config.FACT_SUBSTITUTIONS_PATH.exists():
        return pd.read_parquet(config.FACT_SUBSTITUTIONS_PATH)
    return pd.DataFrame()
