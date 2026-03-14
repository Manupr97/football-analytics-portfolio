"""
fact_goals.py
Transformación para crear/actualizar FACT_GOALS
"""
import pandas as pd
from datetime import datetime
from typing import List

from config import get_config
from parsers.event_parser import GoalEvent
from utils.parquet_utils import upsert_parquet
from utils.logging_config import get_logger

logger = get_logger("transform.fact_goals")


def goals_to_dataframe(goals: List[GoalEvent], match_id: int) -> pd.DataFrame:
    """
    Convierte lista de GoalEvent a DataFrame.
    Añade goal_index (posición ordinal dentro del partido) para evitar
    colisiones de clave cuando un jugador marca dos goles en el mismo minuto.
    """
    if not goals:
        return pd.DataFrame()

    data = []
    for i, g in enumerate(goals):
        data.append({
            'match_id': match_id,
            'goal_index': i,          # ordinal dentro del partido (0-based)
            'minute': g.minute,
            'minute_display': g.minute_display,
            'scorer_player_id': g.scorer_player_id,
            'scorer_player_sk': g.scorer_player_sk,
            'scorer_name': g.scorer_name,
            'assist_player_id': g.assist_player_id,
            'assist_player_sk': g.assist_player_sk,
            'assist_name': g.assist_name,
            'team_id': g.team_id,
            'team_name': g.team_name,
            'side': g.side,
            'goal_type': g.goal_type,
            'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d')
        })

    df = pd.DataFrame(data)

    df['match_id'] = df['match_id'].astype('Int64')
    df['goal_index'] = df['goal_index'].astype('Int64')
    df['minute'] = df['minute'].astype('Int64')
    df['scorer_player_id'] = df['scorer_player_id'].astype('Int64')
    df['scorer_player_sk'] = df['scorer_player_sk'].astype('Int64')
    df['assist_player_id'] = df['assist_player_id'].astype('Int64')
    df['assist_player_sk'] = df['assist_player_sk'].astype('Int64')
    df['team_id'] = df['team_id'].astype('Int64')

    return df


def update_fact_goals(all_goals: List[tuple]) -> pd.DataFrame:
    """
    Actualiza FACT_GOALS con nuevos goles.

    Args:
        all_goals: Lista de tuplas (match_id, List[GoalEvent])

    Returns:
        DataFrame actualizado
    """
    config = get_config()

    logger.info("=" * 60)
    logger.info("ACTUALIZANDO FACT_GOALS")
    logger.info("=" * 60)

    dfs = []
    for match_id, goals in all_goals:
        df = goals_to_dataframe(goals, match_id)
        if not df.empty:
            dfs.append(df)

    if not dfs:
        logger.warning("No hay goles para procesar")
        if config.FACT_GOALS_PATH.exists():
            return pd.read_parquet(config.FACT_GOALS_PATH)
        return pd.DataFrame()

    df_new = pd.concat(dfs, ignore_index=True)
    logger.info(f"Goles nuevos a procesar: {len(df_new)}")

    # Clave: match_id + goal_index — única incluso con dobles en el mismo minuto
    df_result = upsert_parquet(
        df_new=df_new,
        path=config.FACT_GOALS_PATH,
        keys=['match_id', 'goal_index']
    )

    logger.info(f"FACT_GOALS total: {len(df_result)} goles")
    logger.info(f"  - Normales: {(df_result['goal_type'] == 'normal').sum()}")
    logger.info(f"  - Penalties: {(df_result['goal_type'] == 'penalty').sum()}")
    logger.info(f"  - Propios: {(df_result['goal_type'] == 'own_goal').sum()}")
    logger.info(f"  - Con asistencia: {df_result['assist_player_sk'].notna().sum()}")
    logger.info(f"Guardado en: {config.FACT_GOALS_PATH}")

    return df_result


def get_fact_goals() -> pd.DataFrame:
    """Carga FACT_GOALS desde disco."""
    config = get_config()
    if config.FACT_GOALS_PATH.exists():
        return pd.read_parquet(config.FACT_GOALS_PATH)
    return pd.DataFrame()
