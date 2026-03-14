"""
dim_equipos.py
Transformación para crear/actualizar DIM_EQUIPOS
"""
import pandas as pd
from datetime import datetime
from typing import List

from config import get_config
from scrapers.classification import scrape_classification, TeamData
from utils.parquet_utils import upsert_parquet, export_to_powerbi
from utils.logging_config import get_logger

logger = get_logger("transform.dim_equipos")


def teams_to_dataframe(teams: List[TeamData]) -> pd.DataFrame:
    """
    Convierte lista de TeamData a DataFrame.
    
    Args:
        teams: Lista de objetos TeamData
    
    Returns:
        DataFrame con los datos de equipos
    """
    if not teams:
        return pd.DataFrame()
    
    data = []
    for t in teams:
        data.append({
            'team_id': t.team_id,
            'nombre_equipo': t.nombre,
            'slug': t.slug,
            'url_equipo': t.url_equipo,
            'url_escudo': t.url_escudo,
            'posicion_actual': t.posicion,
            'activo': True,
            'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d')
        })
    
    df = pd.DataFrame(data)
    
    # Asegurar tipos correctos
    df['team_id'] = df['team_id'].astype('Int64')
    df['posicion_actual'] = df['posicion_actual'].astype('Int64')
    
    return df


def update_dim_equipos() -> pd.DataFrame:
    """
    Actualiza DIM_EQUIPOS scrapeando la clasificación actual.
    
    Returns:
        DataFrame actualizado de equipos
    """
    config = get_config()
    
    logger.info("=" * 60)
    logger.info("ACTUALIZANDO DIM_EQUIPOS")
    logger.info("=" * 60)
    
    # 1. Scrapear clasificación
    teams = scrape_classification()
    
    if not teams:
        logger.error("No se obtuvieron equipos de la clasificación")
        # Retornar datos existentes si los hay
        if config.DIM_EQUIPOS_PATH.exists():
            return pd.read_parquet(config.DIM_EQUIPOS_PATH)
        return pd.DataFrame()
    
    # 2. Convertir a DataFrame
    df_new = teams_to_dataframe(teams)
    logger.info(f"Equipos scrapeados: {len(df_new)}")
    
    # 3. Upsert en parquet
    df_result = upsert_parquet(
        df_new=df_new,
        path=config.DIM_EQUIPOS_PATH,
        keys=['team_id']
    )
    
    # 4. Estadísticas
    logger.info(f"DIM_EQUIPOS total: {len(df_result)} equipos")
    logger.info(f"Guardado en: {config.DIM_EQUIPOS_PATH}")
    
    return df_result


def get_dim_equipos() -> pd.DataFrame:
    """
    Carga DIM_EQUIPOS desde disco.
    Si no existe, la crea.
    """
    config = get_config()
    
    if not config.DIM_EQUIPOS_PATH.exists():
        logger.info("DIM_EQUIPOS no existe, creando...")
        return update_dim_equipos()
    
    return pd.read_parquet(config.DIM_EQUIPOS_PATH)


def get_team_name(team_id: int) -> str:
    """Obtiene el nombre de un equipo por su ID"""
    df = get_dim_equipos()
    match = df[df['team_id'] == team_id]
    if not match.empty:
        return match.iloc[0]['nombre_equipo']
    return f"Equipo_{team_id}"


def get_team_slug(team_id: int) -> str:
    """Obtiene el slug de un equipo por su ID"""
    df = get_dim_equipos()
    match = df[df['team_id'] == team_id]
    if not match.empty:
        return match.iloc[0]['slug']
    return None


# Test
if __name__ == "__main__":
    df = update_dim_equipos()
    print(f"\nDIM_EQUIPOS creada con {len(df)} equipos:")
    print(df[['team_id', 'nombre_equipo', 'slug', 'posicion_actual']].to_string())
