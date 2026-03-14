"""
fact_appearances.py
Transformación para crear/actualizar FACT_APPEARANCES
Contiene las apariciones de jugadores en partidos (titulares y suplentes que entraron)
"""
import pandas as pd
from datetime import datetime
from typing import List

from config import get_config
from parsers.lineup_parser import PlayerAppearance
from utils.parquet_utils import upsert_parquet
from utils.logging_config import get_logger

logger = get_logger("transform.fact_appearances")


def appearances_to_dataframe(
    local_players: List[PlayerAppearance],
    visitor_players: List[PlayerAppearance],
    match_id: int,
    home_team_id: int,
    away_team_id: int
) -> pd.DataFrame:
    """
    Convierte listas de PlayerAppearance a DataFrame.
    """
    all_players = local_players + visitor_players
    
    if not all_players:
        return pd.DataFrame()
    
    data = []
    for p in all_players:
        # Determinar team_id según side
        team_id = home_team_id if p.side == 'local' else away_team_id
        
        data.append({
            'match_id': match_id,
            'player_id': p.player_id,
            'player_sk': p.player_sk,
            'player_name': p.player_name,
            'team_id': team_id,
            'team_name': p.team_name,
            'position': p.position,
            'shirt_number': p.shirt_number,
            'is_starter': p.is_starter,
            'minute_in': p.minute_in,
            'side': p.side,
            'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d')
        })
    
    df = pd.DataFrame(data)
    
    # Tipos
    df['match_id'] = df['match_id'].astype('Int64')
    df['player_id'] = df['player_id'].astype('Int64')
    df['player_sk'] = df['player_sk'].astype('Int64')
    df['team_id'] = df['team_id'].astype('Int64')
    df['shirt_number'] = df['shirt_number'].astype('Int64')
    df['minute_in'] = df['minute_in'].astype('Int64')
    
    return df


def update_fact_appearances(all_appearances: List[tuple]) -> pd.DataFrame:
    """
    Actualiza FACT_APPEARANCES con nuevas apariciones.
    
    Args:
        all_appearances: Lista de tuplas (match_id, home_team_id, away_team_id, local_players, visitor_players)
    
    Returns:
        DataFrame actualizado
    """
    config = get_config()
    
    logger.info("=" * 60)
    logger.info("ACTUALIZANDO FACT_APPEARANCES")
    logger.info("=" * 60)
    
    # Convertir todas las apariciones a DataFrame
    dfs = []
    for match_id, home_team_id, away_team_id, local_players, visitor_players in all_appearances:
        df = appearances_to_dataframe(local_players, visitor_players, match_id, home_team_id, away_team_id)
        if not df.empty:
            dfs.append(df)
    
    if not dfs:
        logger.warning("No hay apariciones para procesar")
        if config.FACT_APPEARANCES_PATH.exists():
            return pd.read_parquet(config.FACT_APPEARANCES_PATH)
        return pd.DataFrame()
    
    df_new = pd.concat(dfs, ignore_index=True)
    logger.info(f"Apariciones nuevas a procesar: {len(df_new)}")
    
    # Upsert: clave compuesta match_id + player_sk
    df_result = upsert_parquet(
        df_new=df_new,
        path=config.FACT_APPEARANCES_PATH,
        keys=['match_id', 'player_sk']
    )
    
    # Estadísticas
    titulares = (df_result['is_starter'] == True).sum()
    suplentes_entraron = ((df_result['is_starter'] == False) & (df_result['minute_in'].notna())).sum()
    suplentes_no_entraron = ((df_result['is_starter'] == False) & (df_result['minute_in'].isna())).sum()
    
    logger.info(f"FACT_APPEARANCES total: {len(df_result)} registros")
    logger.info(f"  - Titulares: {titulares}")
    logger.info(f"  - Suplentes que entraron: {suplentes_entraron}")
    logger.info(f"  - Suplentes sin entrar: {suplentes_no_entraron}")
    logger.info(f"Guardado en: {config.FACT_APPEARANCES_PATH}")
    
    return df_result


def get_fact_appearances() -> pd.DataFrame:
    """Carga FACT_APPEARANCES desde disco."""
    config = get_config()
    if config.FACT_APPEARANCES_PATH.exists():
        return pd.read_parquet(config.FACT_APPEARANCES_PATH)
    return pd.DataFrame()
