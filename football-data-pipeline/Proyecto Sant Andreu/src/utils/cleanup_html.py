"""
cleanup_html.py
Script para limpiar archivos HTML de data_raw/ que ya no son necesarios
(los datos ya están en Parquet)
"""
import shutil
from pathlib import Path
from typing import List, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from utils.logging_config import get_logger

logger = get_logger("cleanup_html")


def get_html_stats(directory: Path) -> Tuple[int, int]:
    """
    Obtiene estadísticas de archivos HTML en un directorio.

    Returns:
        Tupla (num_archivos, tamaño_total_bytes)
    """
    if not directory.exists():
        return 0, 0

    html_files = list(directory.glob("*.html"))
    total_size = sum(f.stat().st_size for f in html_files)

    return len(html_files), total_size


def format_size(size_bytes: int) -> str:
    """Formatea tamaño en bytes a formato legible"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def cleanup_html_files(
    directories: List[Path] = None,
    dry_run: bool = True,
    keep_examples: bool = True
) -> dict:
    """
    Limpia archivos HTML de los directorios especificados.

    Args:
        directories: Lista de directorios a limpiar (None = lineups y events)
        dry_run: Si True, solo muestra qué se eliminaría sin eliminar
        keep_examples: Si True, mantiene archivos con 'ejemplo' o 'raw' en el nombre

    Returns:
        Dict con estadísticas de la limpieza
    """
    config = get_config()

    if directories is None:
        directories = [
            config.LINEUPS_RAW_DIR,
            config.EVENTS_RAW_DIR,
        ]

    stats = {
        'directories_processed': 0,
        'files_deleted': 0,
        'files_kept': 0,
        'bytes_freed': 0,
        'dry_run': dry_run
    }

    logger.info("=" * 60)
    logger.info(f"LIMPIEZA DE HTMLs {'(DRY RUN)' if dry_run else ''}")
    logger.info("=" * 60)

    for directory in directories:
        if not directory.exists():
            logger.warning(f"Directorio no existe: {directory}")
            continue

        stats['directories_processed'] += 1
        html_files = list(directory.glob("*.html"))

        logger.info(f"\nDirectorio: {directory.name}/")
        logger.info(f"  Archivos HTML encontrados: {len(html_files)}")

        for html_file in html_files:
            # Decidir si mantener o eliminar
            filename = html_file.name.lower()
            should_keep = keep_examples and ('ejemplo' in filename or 'raw' in filename)

            if should_keep:
                stats['files_kept'] += 1
                logger.debug(f"  [MANTENER] {html_file.name}")
            else:
                file_size = html_file.stat().st_size
                stats['bytes_freed'] += file_size

                if dry_run:
                    logger.debug(f"  [ELIMINAR] {html_file.name} ({format_size(file_size)})")
                else:
                    html_file.unlink()
                    logger.debug(f"  [ELIMINADO] {html_file.name}")

                stats['files_deleted'] += 1

    # Resumen
    logger.info("\n" + "=" * 60)
    logger.info("RESUMEN")
    logger.info("=" * 60)
    logger.info(f"Directorios procesados: {stats['directories_processed']}")
    logger.info(f"Archivos {'a eliminar' if dry_run else 'eliminados'}: {stats['files_deleted']}")
    logger.info(f"Archivos mantenidos: {stats['files_kept']}")
    logger.info(f"Espacio {'a liberar' if dry_run else 'liberado'}: {format_size(stats['bytes_freed'])}")

    if dry_run:
        logger.info("\n[!] Esto fue un DRY RUN. Ejecuta con dry_run=False para eliminar.")

    return stats


def cleanup_all_raw_html(dry_run: bool = True) -> dict:
    """
    Limpia TODOS los HTMLs de data_raw/ excepto classification/.

    Args:
        dry_run: Si True, solo muestra qué se eliminaría

    Returns:
        Dict con estadísticas
    """
    config = get_config()

    directories = [
        config.LINEUPS_RAW_DIR,
        config.EVENTS_RAW_DIR,
        config.MATCHES_RAW_DIR,
    ]

    return cleanup_html_files(directories, dry_run=dry_run, keep_examples=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Limpia archivos HTML de data_raw/")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Ejecuta la limpieza (por defecto solo muestra qué se eliminaría)"
    )
    parser.add_argument(
        "--no-keep-examples",
        action="store_true",
        help="También elimina archivos de ejemplo (*_ejemplo_raw.html)"
    )

    args = parser.parse_args()

    # Mostrar estadísticas antes
    config = get_config()

    print("\n📊 ESTADÍSTICAS ACTUALES:")
    print("-" * 40)

    for name, directory in [
        ("lineups", config.LINEUPS_RAW_DIR),
        ("events", config.EVENTS_RAW_DIR),
        ("matches", config.MATCHES_RAW_DIR),
        ("classification", config.CLASSIFICATION_RAW_DIR),
    ]:
        num_files, total_size = get_html_stats(directory)
        print(f"  {name:15} {num_files:4} archivos  {format_size(total_size):>10}")

    print()

    # Ejecutar limpieza
    cleanup_all_raw_html(
        dry_run=not args.execute,
    )
