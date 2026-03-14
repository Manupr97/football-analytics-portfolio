"""
processed_matches.py
Registro de partidos procesados para procesamiento incremental
"""
import pandas as pd
from datetime import datetime
from typing import Set, List

from config import get_config
from utils.logging_config import get_logger

logger = get_logger("pipeline.processed_matches")


def get_processed_match_ids() -> Set[int]:
    """
    Obtiene el set de match_ids ya procesados.
    """
    config = get_config()
    
    if not config.PROCESSED_MATCHES_PATH.exists():
        return set()
    
    df = pd.read_parquet(config.PROCESSED_MATCHES_PATH)
    return set(df['match_id'].tolist())


def mark_matches_processed(match_ids: List[int]) -> None:
    """
    Marca partidos como procesados.
    """
    config = get_config()
    
    if not match_ids:
        return
    
    # Crear DataFrame con nuevos IDs
    df_new = pd.DataFrame({
        'match_id': match_ids,
        'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    df_new['match_id'] = df_new['match_id'].astype('Int64')
    
    # Cargar existentes si hay
    if config.PROCESSED_MATCHES_PATH.exists():
        df_existing = pd.read_parquet(config.PROCESSED_MATCHES_PATH)
        df_result = pd.concat([df_existing, df_new], ignore_index=True)
        df_result = df_result.drop_duplicates(subset=['match_id'], keep='last')
    else:
        df_result = df_new
    
    # Asegurar directorio existe
    config.META_DIR.mkdir(parents=True, exist_ok=True)
    
    # Guardar
    df_result.to_parquet(config.PROCESSED_MATCHES_PATH, index=False)
    logger.info(f"Marcados {len(match_ids)} partidos como procesados")


def get_pending_matches(all_finished_matches: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra partidos finalizados que aún no han sido procesados.
    
    Args:
        all_finished_matches: DataFrame con todos los partidos finalizados
    
    Returns:
        DataFrame con partidos pendientes de procesar
    """
    processed_ids = get_processed_match_ids()
    
    if not processed_ids:
        logger.info("No hay partidos procesados previamente")
        return all_finished_matches
    
    pending = all_finished_matches[~all_finished_matches['match_id'].isin(processed_ids)]
    
    logger.info(f"Partidos finalizados: {len(all_finished_matches)}")
    logger.info(f"Ya procesados: {len(processed_ids)}")
    logger.info(f"Pendientes: {len(pending)}")
    
    return pending


def reset_processed_matches() -> None:
    """
    Resetea el registro de partidos procesados (para reprocesar todo).
    """
    config = get_config()
    
    if config.PROCESSED_MATCHES_PATH.exists():
        config.PROCESSED_MATCHES_PATH.unlink()
        logger.info("Registro de partidos procesados reseteado")
