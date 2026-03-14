"""
run_pipeline.py
Orquestador principal del pipeline de scraping y transformación
Procesa solo partidos nuevos (incremental)
"""
import time
from datetime import datetime
from typing import Optional

from config import get_config
from utils.logging_config import get_logger
from utils.http_client import get_http_client

# Scrapers
from scrapers.lineups import scrape_or_load_lineups
from scrapers.events import scrape_or_load_events

# Transformaciones
from transform.dim_equipos import update_dim_equipos
from transform.dim_partidos import update_dim_partidos, get_finished_matches
from transform.fact_goals import update_fact_goals
from transform.fact_substitutions import update_fact_substitutions
from transform.fact_appearances import update_fact_appearances
from transform.dim_jugadores import update_dim_jugadores

# Pipeline
from pipeline.processed_matches import get_pending_matches, mark_matches_processed

logger = get_logger("pipeline.main")


def run_full_pipeline(
    force_reprocess: bool = False,
    max_matches: Optional[int] = None,
    delay_between_matches: float = 1.5
) -> dict:
    """
    Ejecuta el pipeline completo.
    
    Args:
        force_reprocess: Si True, reprocesa todos los partidos
        max_matches: Límite de partidos a procesar (None = todos)
        delay_between_matches: Segundos entre requests de partidos
    
    Returns:
        Dict con estadísticas del proceso
    """
    config = get_config()
    start_time = datetime.now()
    
    logger.info("=" * 70)
    logger.info("INICIO DEL PIPELINE - Segunda RFEF Grupo 3")
    logger.info(f"Fecha: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    stats = {
        'partidos_procesados': 0,
        'goles': 0,
        'sustituciones': 0,
        'apariciones': 0,
        'errores': 0
    }
    
    try:
        # 1. Actualizar dimensiones base
        logger.info("\n[1/6] Actualizando DIM_EQUIPOS...")
        update_dim_equipos()
        
        logger.info("\n[2/6] Actualizando DIM_PARTIDOS...")
        update_dim_partidos()
        
        # 2. Obtener partidos pendientes
        logger.info("\n[3/6] Identificando partidos pendientes...")
        finished = get_finished_matches()
        
        if force_reprocess:
            from pipeline.processed_matches import reset_processed_matches
            reset_processed_matches()
            pending = finished
        else:
            pending = get_pending_matches(finished)
        
        if pending.empty:
            logger.info("No hay partidos nuevos para procesar")
        else:
            if max_matches:
                pending = pending.head(max_matches)
                logger.info(f"Limitando a {max_matches} partidos")
            
            logger.info(f"Partidos a procesar: {len(pending)}")
            
            # 3. Procesar cada partido
            all_goals = []
            all_subs = []
            all_appearances = []
            processed_ids = []
            
            for idx, match in pending.iterrows():
                match_id = int(match['match_id'])
                home_team_id = int(match['home_team_id'])
                away_team_id = int(match['away_team_id'])
                home_team_name = str(match.get('home_team_name', ''))
                away_team_name = str(match.get('away_team_name', ''))
                
                logger.info(f"\n  Procesando [{len(processed_ids)+1}/{len(pending)}]: "
                           f"{match['home_team_name']} vs {match['away_team_name']} (ID: {match_id})")
                
                try:
                    # Scrapear alineaciones
                    local_players, visitor_players = scrape_or_load_lineups(
                        match_id=match_id,
                        match_url=match['match_url'],
                        use_cache=True
                    )
                    
                    # Scrapear eventos
                    goals, subs = scrape_or_load_events(
                        match_id=match_id,
                        match_url=match['match_url'],
                        home_team_id=home_team_id,
                        away_team_id=away_team_id,
                        home_team_name=home_team_name,
                        away_team_name=away_team_name,
                        use_cache=True
                    )
                    
                    # Enriquecer minute_in de suplentes con datos de sustituciones
                    # (fuente única: FACT_SUBSTITUTIONS, evita doble parsing)
                    if subs:
                        subs_by_player_side = {
                            (s.player_in_name, s.side): s.minute for s in subs
                        }
                        for p in local_players + visitor_players:
                            if not p.is_starter and p.minute_in is None:
                                key = (p.player_name, p.side)
                                if key in subs_by_player_side:
                                    p.minute_in = subs_by_player_side[key]

                    # Acumular resultados
                    if goals:
                        all_goals.append((match_id, goals))
                    if subs:
                        all_subs.append((match_id, subs))
                    if local_players or visitor_players:
                        all_appearances.append((
                            match_id, home_team_id, away_team_id,
                            local_players, visitor_players
                        ))
                    
                    processed_ids.append(match_id)
                    
                    logger.info(f"    -> {len(local_players)+len(visitor_players)} jugadores, "
                               f"{len(goals)} goles, {len(subs)} sustituciones")
                    
                    # Delay entre partidos
                    time.sleep(delay_between_matches)
                    
                except Exception as e:
                    logger.error(f"    -> ERROR: {e}")
                    stats['errores'] += 1
                    continue
            
            # 4. Actualizar tablas FACT
            logger.info("\n[4/6] Actualizando FACT_GOALS...")
            if all_goals:
                df_goals = update_fact_goals(all_goals)
                stats['goles'] = len(df_goals) if not df_goals.empty else 0
            
            logger.info("\n[5/6] Actualizando FACT_SUBSTITUTIONS...")
            if all_subs:
                df_subs = update_fact_substitutions(all_subs)
                stats['sustituciones'] = len(df_subs) if not df_subs.empty else 0
            
            logger.info("\n[6/6] Actualizando FACT_APPEARANCES y DIM_JUGADORES...")
            if all_appearances:
                df_app = update_fact_appearances(all_appearances)
                stats['apariciones'] = len(df_app) if not df_app.empty else 0
                
                # Actualizar DIM_JUGADORES
                update_dim_jugadores()
            
            # 5. Marcar partidos como procesados
            if processed_ids:
                mark_matches_processed(processed_ids)
                stats['partidos_procesados'] = len(processed_ids)
        
        # Resumen final
        elapsed = (datetime.now() - start_time).total_seconds()
        
        logger.info("\n" + "=" * 70)
        logger.info("PIPELINE COMPLETADO")
        logger.info("=" * 70)
        logger.info(f"Tiempo total: {elapsed:.1f} segundos")
        logger.info(f"Partidos procesados: {stats['partidos_procesados']}")
        logger.info(f"Goles totales: {stats['goles']}")
        logger.info(f"Sustituciones totales: {stats['sustituciones']}")
        logger.info(f"Apariciones totales: {stats['apariciones']}")
        logger.info(f"Errores: {stats['errores']}")
        logger.info(f"\nArchivos en: {config.DATA_PROCESSED_DIR}")
        
        return stats
        
    except Exception as e:
        logger.error(f"ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        raise


def run_incremental() -> dict:
    """Ejecuta pipeline incremental (solo partidos nuevos)."""
    return run_full_pipeline(force_reprocess=False)


def run_full_reprocess() -> dict:
    """Ejecuta pipeline completo reprocesando todo."""
    return run_full_pipeline(force_reprocess=True)


if __name__ == "__main__":
    run_incremental()
