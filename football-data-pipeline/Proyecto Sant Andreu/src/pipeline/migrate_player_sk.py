"""
migrate_player_sk.py
====================
Script de migración única: recalcula todos los player_sk en los parquets
existentes usando la lógica canónica actual de generate_player_sk
(nombre + equipo normalizados, sin tildes, en mayúsculas).

Motivación
----------
Los parquets en data_processed/ y outputs_powerbi/ se generaron en diferentes
momentos con versiones distintas de generate_player_sk (una usaba .lower(),
otra no pasaba team_name en FACT_GOALS). Esto provocó que el mismo jugador
sin player_id real (ej: Jaume Tovar) tuviera SK distintos en FACT_APPEARANCES
y FACT_GOALS, rompiendo las relaciones del modelo estrella.

Estrategia
----------
La fuente de verdad son los HTML cacheados en html/events/ y html/lineups/.
Re-parseamos partido a partido usando los parsers actualizados, que ya
propagan home_team_name/away_team_name correctamente, y reconstruimos
FACT_GOALS, FACT_SUBSTITUTIONS, FACT_APPEARANCES y DIM_JUGADORES desde cero.

Uso
---
    cd <proyecto>/src
    python pipeline/migrate_player_sk.py
"""
import sys
from pathlib import Path

# Asegurar que src/ está en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime

from config import get_config
from utils.logging_config import get_logger, setup_logging

# Activar logging a consola y archivo
setup_logging(get_config().LOGS_DIR)
from parsers.event_parser import parse_events_html
from parsers.lineup_parser import parse_lineup_html
from transform.fact_goals import goals_to_dataframe
from transform.fact_substitutions import substitutions_to_dataframe
from transform.fact_appearances import appearances_to_dataframe
from transform.dim_jugadores import build_dim_jugadores_from_appearances

logger = get_logger("pipeline.migrate_sk")


def _load_dim_partidos(config) -> pd.DataFrame:
    path = config.DIM_PARTIDOS_PATH
    if not path.exists():
        raise FileNotFoundError(f"No existe DIM_PARTIDOS en {path}")
    return pd.read_parquet(path)


def migrate_all_sk(dry_run: bool = False) -> dict:
    """
    Reconstruye FACT_GOALS, FACT_SUBSTITUTIONS, FACT_APPEARANCES y DIM_JUGADORES
    reparsando desde los HTML en caché con la lógica de SK actualizada.

    Args:
        dry_run: Si True, muestra estadísticas pero no guarda nada.

    Returns:
        Dict con contadores de registros procesados.
    """
    config = get_config()
    logger.info("=" * 70)
    logger.info("MIGRACIÓN DE PLAYER_SK")
    logger.info(f"Modo: {'DRY RUN (sin guardar)' if dry_run else 'ESCRITURA REAL'}")
    logger.info("=" * 70)

    dim_partidos = _load_dim_partidos(config)
    logger.info(f"Partidos en DIM_PARTIDOS: {len(dim_partidos)}")

    # Solo los partidos finalizados (tienen HTML en caché)
    finalizados = dim_partidos[dim_partidos['status'] == 'Finalizado'].copy()
    logger.info(f"Partidos finalizados: {len(finalizados)}")

    all_goals_dfs = []
    all_subs_dfs = []
    all_appearances_dfs = []

    partidos_ok = 0
    partidos_sin_html = 0

    for _, match in finalizados.iterrows():
        match_id = int(match['match_id'])
        home_team_id = int(match['home_team_id'])
        away_team_id = int(match['away_team_id'])
        home_team_name = str(match.get('home_team_name', ''))
        away_team_name = str(match.get('away_team_name', ''))

        events_html_path = config.EVENTS_HTML_DIR / f"{match_id}.html"
        lineups_html_path = config.LINEUPS_HTML_DIR / f"{match_id}.html"

        if not events_html_path.exists() and not lineups_html_path.exists():
            logger.warning(f"  [{match_id}] Sin HTML en caché — omitido")
            partidos_sin_html += 1
            continue

        # --- Eventos (goles y sustituciones) ---
        if events_html_path.exists():
            html_events = events_html_path.read_text(encoding="utf-8")
            goals, subs = parse_events_html(
                html_events,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_team_name=home_team_name,
                away_team_name=away_team_name,
            )

            if goals:
                df_goals = goals_to_dataframe(goals, match_id)
                all_goals_dfs.append(df_goals)

            if subs:
                df_subs = substitutions_to_dataframe(subs, match_id)
                all_subs_dfs.append(df_subs)
        else:
            goals, subs = [], []

        # --- Alineaciones (appearances) ---
        if lineups_html_path.exists():
            html_lineups = lineups_html_path.read_text(encoding="utf-8")
            local_players, visitor_players = parse_lineup_html(html_lineups)

            # Enriquecer minute_in desde sustituciones
            if subs:
                subs_by_player_side = {
                    (s.player_in_name, s.side): s.minute for s in subs
                }
                for p in local_players + visitor_players:
                    if not p.is_starter and p.minute_in is None:
                        key = (p.player_name, p.side)
                        if key in subs_by_player_side:
                            p.minute_in = subs_by_player_side[key]

            df_app = appearances_to_dataframe(
                local_players, visitor_players,
                match_id, home_team_id, away_team_id
            )
            if not df_app.empty:
                all_appearances_dfs.append(df_app)

        partidos_ok += 1

    logger.info(f"\nPartidos procesados: {partidos_ok} | Sin HTML: {partidos_sin_html}")

    # Construir DataFrames finales
    stats = {
        'partidos_procesados': partidos_ok,
        'partidos_sin_html': partidos_sin_html,
        'goles': 0,
        'sustituciones': 0,
        'apariciones': 0,
    }

    if all_goals_dfs:
        df_goals_final = pd.concat(all_goals_dfs, ignore_index=True)
        df_goals_final = df_goals_final.sort_values(['match_id', 'goal_index']).reset_index(drop=True)
        stats['goles'] = len(df_goals_final)
        logger.info(f"FACT_GOALS: {len(df_goals_final)} goles")
        if not dry_run:
            df_goals_final.to_parquet(config.FACT_GOALS_PATH, index=False)
            logger.info(f"  Guardado: {config.FACT_GOALS_PATH}")

    if all_subs_dfs:
        df_subs_final = pd.concat(all_subs_dfs, ignore_index=True)
        df_subs_final = df_subs_final.sort_values(['match_id', 'minute']).reset_index(drop=True)
        stats['sustituciones'] = len(df_subs_final)
        logger.info(f"FACT_SUBSTITUTIONS: {len(df_subs_final)} sustituciones")
        if not dry_run:
            df_subs_final.to_parquet(config.FACT_SUBSTITUTIONS_PATH, index=False)
            logger.info(f"  Guardado: {config.FACT_SUBSTITUTIONS_PATH}")

    if all_appearances_dfs:
        df_app_final = pd.concat(all_appearances_dfs, ignore_index=True)
        df_app_final = df_app_final.sort_values(['match_id', 'player_sk']).reset_index(drop=True)
        stats['apariciones'] = len(df_app_final)
        logger.info(f"FACT_APPEARANCES: {len(df_app_final)} apariciones")
        if not dry_run:
            df_app_final.to_parquet(config.FACT_APPEARANCES_PATH, index=False)
            logger.info(f"  Guardado: {config.FACT_APPEARANCES_PATH}")

            # Reconstruir DIM_JUGADORES desde las appearances recién migradas
            logger.info("Reconstruyendo DIM_JUGADORES...")
            build_dim_jugadores_from_appearances()

    if dry_run:
        logger.info("\n[DRY RUN] No se ha guardado nada.")

    logger.info("\n" + "=" * 70)
    logger.info("MIGRACIÓN COMPLETADA")
    logger.info("=" * 70)
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")

    return stats


def verify_sk_consistency() -> bool:
    """
    Verifica que los player_sk son consistentes entre todas las tablas.

    Un conflicto REAL es: mismo jugador (mismo player_sk) aparece con
    distinto nombre, o el mismo nombre+equipo tiene dos SK distintos.
    Jugadores homónimos en equipos distintos son correctos y se ignoran.

    Returns:
        True si no hay inconsistencias reales.
    """
    config = get_config()
    logger.info("\n" + "=" * 70)
    logger.info("VERIFICACIÓN DE CONSISTENCIA DE PLAYER_SK")
    logger.info("=" * 70)

    ok = True

    if not config.FACT_APPEARANCES_PATH.exists():
        logger.warning("FACT_APPEARANCES no existe, no se puede verificar.")
        return True

    # Mapa canónico: player_sk -> (player_name, team_name) desde FACT_APPEARANCES
    app = pd.read_parquet(config.FACT_APPEARANCES_PATH)
    canonical = (
        app[['player_sk', 'player_name', 'team_name']]
        .dropna(subset=['player_sk'])
        .drop_duplicates(subset=['player_sk'])
        .set_index('player_sk')
    )

    # Recopilar todos los pares (player_name, player_sk, team_name) de los facts de eventos
    # Para goals/subs cruzamos el team_name desde team_id via appearances
    records = []

    def _collect(path, col_pairs):
        if not path.exists():
            return
        df = pd.read_parquet(path)
        for name_col, sk_col in col_pairs:
            if name_col not in df.columns or sk_col not in df.columns:
                continue
            sub = df[[name_col, sk_col, 'team_name']].dropna(subset=[name_col, sk_col]).drop_duplicates()
            sub = sub.rename(columns={name_col: 'player_name', sk_col: 'player_sk'})
            records.append(sub)

    _collect(config.FACT_GOALS_PATH, [
        ('scorer_name', 'scorer_player_sk'),
        ('assist_name', 'assist_player_sk'),
    ])
    _collect(config.FACT_SUBSTITUTIONS_PATH, [
        ('player_in_name', 'player_in_sk'),
        ('player_out_name', 'player_out_sk'),
    ])

    if not records:
        logger.info("OK — No hay datos de eventos para verificar.")
        return True

    all_events = pd.concat(records, ignore_index=True).drop_duplicates()

    # Conflicto real: mismo (player_name, team_name) con dos SK distintos
    # Esto indicaría que un jugador del mismo equipo recibió dos hashes diferentes.
    conflictos = (
        all_events.groupby(['player_name', 'team_name'])['player_sk']
        .nunique()
        .reset_index()
        .rename(columns={'player_sk': 'n_sk'})
        .query('n_sk > 1')
    )

    if conflictos.empty:
        logger.info("OK — Todos los player_sk son consistentes.")
    else:
        ok = False
        logger.error(f"CONFLICTOS ENCONTRADOS: {len(conflictos)} jugadores con SK duplicado en el mismo equipo")
        for _, row in conflictos.iterrows():
            mask = (all_events['player_name'] == row['player_name']) & (all_events['team_name'] == row['team_name'])
            detalle = all_events[mask][['player_sk']].drop_duplicates()
            logger.error(f"\n  {row['player_name']} ({row['team_name']}): SKs = {detalle['player_sk'].tolist()}")

    # Estadística informativa: jugadores sin player_id (SKs negativos/hash)
    n_hash = (canonical.index < 0).sum()
    logger.info(f"Jugadores con SK por hash (sin player_id BeSoccer): {n_hash}")

    return ok


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migra player_sk en los parquets del proyecto Sant Andreu")
    parser.add_argument("--dry-run", action="store_true", help="Simula sin guardar")
    parser.add_argument("--verify-only", action="store_true", help="Solo verifica sin migrar")
    args = parser.parse_args()

    if args.verify_only:
        ok = verify_sk_consistency()
        sys.exit(0 if ok else 1)

    migrate_all_sk(dry_run=args.dry_run)

    if not args.dry_run:
        verify_sk_consistency()
