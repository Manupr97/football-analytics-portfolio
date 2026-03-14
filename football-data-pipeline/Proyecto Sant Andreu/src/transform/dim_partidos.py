"""
dim_partidos.py
Transformación para crear/actualizar DIM_PARTIDOS
"""
import pandas as pd
from datetime import datetime
from typing import List

from config import get_config
from scrapers.matches import scrape_all_matches, MatchData
from utils.parquet_utils import upsert_parquet
from utils.logging_config import get_logger

logger = get_logger("transform.dim_partidos")


def matches_to_dataframe(matches: List[MatchData]) -> pd.DataFrame:
    """
    Convierte lista de MatchData a DataFrame.
    
    Args:
        matches: Lista de objetos MatchData
    
    Returns:
        DataFrame con los datos de partidos
    """
    if not matches:
        return pd.DataFrame()
    
    data = []
    for m in matches:
        data.append({
            'match_id': m.match_id,
            'match_url': m.match_url,
            'jornada': m.jornada,
            'fecha': m.fecha,
            'fecha_display': m.fecha_display,
            'home_team_id': m.home_team_id,
            'home_team_name': m.home_team_name,
            'away_team_id': m.away_team_id,
            'away_team_name': m.away_team_name,
            'score_home': m.score_home,
            'score_away': m.score_away,
            'status': m.status,
            'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d')
        })
    
    df = pd.DataFrame(data)
    
    # Asegurar tipos correctos
    df['match_id'] = df['match_id'].astype('Int64')
    df['jornada'] = df['jornada'].astype('Int64')
    df['home_team_id'] = df['home_team_id'].astype('Int64')
    df['away_team_id'] = df['away_team_id'].astype('Int64')
    df['score_home'] = df['score_home'].astype('Int64')
    df['score_away'] = df['score_away'].astype('Int64')
    
    return df


def update_dim_partidos() -> pd.DataFrame:
    """
    Actualiza DIM_PARTIDOS scrapeando partidos de todos los equipos.
    
    Returns:
        DataFrame actualizado de partidos
    """
    config = get_config()
    
    logger.info("=" * 60)
    logger.info("ACTUALIZANDO DIM_PARTIDOS")
    logger.info("=" * 60)
    
    # 1. Scrapear todos los partidos
    matches = scrape_all_matches()
    
    if not matches:
        logger.error("No se obtuvieron partidos")
        if config.DIM_PARTIDOS_PATH.exists():
            return pd.read_parquet(config.DIM_PARTIDOS_PATH)
        return pd.DataFrame()
    
    # 2. Convertir a DataFrame
    df_new = matches_to_dataframe(matches)
    logger.info(f"Partidos scrapeados: {len(df_new)}")
    
    # 3. Upsert en parquet
    df_result = upsert_parquet(
        df_new=df_new,
        path=config.DIM_PARTIDOS_PATH,
        keys=['match_id']
    )
    
    # 4. Estadísticas
    finalizados = (df_result['status'] == 'Finalizado').sum()
    programados = (df_result['status'] == 'Programado').sum()
    aplazados = (df_result['status'] == 'Aplazado').sum()
    
    logger.info(f"DIM_PARTIDOS total: {len(df_result)} partidos")
    logger.info(f"  - Finalizados: {finalizados}")
    logger.info(f"  - Programados: {programados}")
    logger.info(f"  - Aplazados: {aplazados}")
    logger.info(f"Guardado en: {config.DIM_PARTIDOS_PATH}")
    
    return df_result


def get_dim_partidos() -> pd.DataFrame:
    """
    Carga DIM_PARTIDOS desde disco.
    Si no existe, la crea.
    """
    config = get_config()
    
    if not config.DIM_PARTIDOS_PATH.exists():
        logger.info("DIM_PARTIDOS no existe, creando...")
        return update_dim_partidos()
    
    return pd.read_parquet(config.DIM_PARTIDOS_PATH)


def get_finished_matches() -> pd.DataFrame:
    """Retorna solo los partidos finalizados"""
    df = get_dim_partidos()
    return df[df['status'] == 'Finalizado'].copy()


def get_pending_matches() -> pd.DataFrame:
    """Retorna partidos programados (pendientes de jugar)"""
    df = get_dim_partidos()
    return df[df['status'] == 'Programado'].copy()


def get_match_by_id(match_id: int) -> pd.Series:
    """Obtiene un partido por su ID"""
    df = get_dim_partidos()
    match = df[df['match_id'] == match_id]
    if not match.empty:
        return match.iloc[0]
    return None


# Test
if __name__ == "__main__":
    df = update_dim_partidos()
    print(f"\nDIM_PARTIDOS creada con {len(df)} partidos")
    print(df[['match_id', 'jornada', 'home_team_name', 'score_home', 'score_away', 'away_team_name', 'status']].head(20).to_string())
