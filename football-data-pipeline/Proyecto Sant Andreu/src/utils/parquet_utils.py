"""
parquet_utils.py
Utilidades para manejo de archivos Parquet: upsert, export a Power BI, tipos de datos
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from config import get_config
from utils.logging_config import get_logger

logger = get_logger("parquet_utils")


def optimize_int_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Optimiza columnas numéricas para que los enteros no tengan decimales.
    Usa Int64 (nullable) para manejar NaN sin convertir a float.
    
    Args:
        df: DataFrame a optimizar
    
    Returns:
        DataFrame con tipos optimizados
    """
    df = df.copy()
    
    for col in df.columns:
        # Detectar columnas que deberían ser enteras
        if df[col].dtype in ['float64', 'float32']:
            # Verificar si todos los valores no-nulos son enteros
            non_null = df[col].dropna()
            if len(non_null) > 0 and (non_null == non_null.astype(int)).all():
                df[col] = df[col].astype('Int64')  # Nullable integer
        
        # Columnas que terminan en _id siempre deben ser Int64
        if col.endswith('_id') or col.endswith('_sk'):
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    
    return df


def upsert_parquet(
    df_new: pd.DataFrame,
    path: Path,
    keys: List[str],
    optimize_types: bool = True
) -> pd.DataFrame:
    """
    Realiza upsert (update + insert) en un archivo Parquet.
    
    - Si el archivo no existe, lo crea.
    - Si existe, elimina registros con keys duplicadas y añade los nuevos.
    
    Args:
        df_new: DataFrame con datos nuevos
        path: Ruta del archivo Parquet
        keys: Lista de columnas que forman la clave única
        optimize_types: Si optimizar tipos de datos
    
    Returns:
        DataFrame resultante después del upsert
    """
    path = Path(path)
    
    if df_new.empty:
        logger.warning(f"DataFrame vacío, no se realiza upsert en {path.name}")
        if path.exists():
            return pd.read_parquet(path)
        return df_new
    
    # Optimizar tipos si se solicita
    if optimize_types:
        df_new = optimize_int_columns(df_new)
    
    # Si no existe el archivo, simplemente guardar
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        df_new.to_parquet(path, index=False)
        logger.info(f"Creado {path.name} con {len(df_new)} registros")
        return df_new
    
    # Cargar datos existentes
    df_existing = pd.read_parquet(path)
    
    # Asegurar que las keys existen en ambos DataFrames
    for key in keys:
        if key not in df_new.columns:
            raise ValueError(f"Key '{key}' no existe en df_new")
        if key not in df_existing.columns:
            raise ValueError(f"Key '{key}' no existe en archivo existente")
    
    # Crear índice de keys en df_new para identificar duplicados
    if len(keys) == 1:
        new_keys = set(df_new[keys[0]].dropna().astype(str))
        mask = ~df_existing[keys[0]].astype(str).isin(new_keys)
    else:
        # Multi-key: crear tuplas
        new_keys = set(
            tuple(str(v) for v in row) 
            for row in df_new[keys].values
        )
        existing_tuples = [
            tuple(str(v) for v in row) 
            for row in df_existing[keys].values
        ]
        mask = [t not in new_keys for t in existing_tuples]
    
    # Filtrar existentes que no están en nuevos
    df_existing_filtered = df_existing[mask]
    
    # Concatenar
    df_result = pd.concat([df_existing_filtered, df_new], ignore_index=True)
    
    # Optimizar tipos del resultado
    if optimize_types:
        df_result = optimize_int_columns(df_result)
    
    # Guardar
    df_result.to_parquet(path, index=False)
    
    registros_actualizados = len(df_existing) - len(df_existing_filtered)
    registros_nuevos = len(df_new) - registros_actualizados
    
    logger.info(
        f"Upsert {path.name}: {registros_nuevos} nuevos, "
        f"{registros_actualizados} actualizados, {len(df_result)} total"
    )
    
    return df_result


def export_to_powerbi(
    source_path: Path,
    output_dir: Path = None,
    uppercase_name: bool = True
) -> Path:
    """
    Exporta un archivo Parquet al directorio de Power BI.
    
    Args:
        source_path: Ruta del archivo fuente
        output_dir: Directorio destino (default: outputs_powerbi/)
        uppercase_name: Si convertir nombre a mayúsculas
    
    Returns:
        Ruta del archivo exportado
    """
    config = get_config()
    output_dir = output_dir or config.OUTPUTS_POWERBI_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Nombre del archivo
    name = source_path.stem
    if uppercase_name:
        name = name.upper()
    
    output_path = output_dir / f"{name}.parquet"
    
    # Leer, optimizar y guardar
    df = pd.read_parquet(source_path)
    df = optimize_int_columns(df)
    df.to_parquet(output_path, index=False)
    
    logger.info(f"Exportado a Power BI: {output_path.name} ({len(df)} registros)")
    
    return output_path


def export_all_to_powerbi() -> List[Path]:
    """
    Exporta todas las tablas procesadas a Power BI.
    
    Returns:
        Lista de rutas exportadas
    """
    config = get_config()
    exported = []
    
    # Lista de archivos a exportar
    files_to_export = [
        config.DIM_EQUIPOS_PATH,
        config.DIM_PARTIDOS_PATH,
        config.DIM_JUGADORES_PATH,
        config.FACT_GOALS_PATH,
        config.FACT_SUBSTITUTIONS_PATH,
        config.FACT_APPEARANCES_PATH,
    ]
    
    for file_path in files_to_export:
        if file_path.exists():
            output_path = export_to_powerbi(file_path)
            exported.append(output_path)
        else:
            logger.warning(f"Archivo no encontrado: {file_path.name}")
    
    logger.info(f"Exportación completada: {len(exported)} archivos")
    return exported


def load_or_create_parquet(path: Path, schema: dict = None) -> pd.DataFrame:
    """
    Carga un archivo Parquet o crea un DataFrame vacío con el schema indicado.
    
    Args:
        path: Ruta del archivo
        schema: Diccionario {columna: tipo} para crear DataFrame vacío
    
    Returns:
        DataFrame cargado o vacío
    """
    if path.exists():
        return pd.read_parquet(path)
    
    if schema:
        return pd.DataFrame({col: pd.Series(dtype=dtype) for col, dtype in schema.items()})
    
    return pd.DataFrame()


# Test
if __name__ == "__main__":
    # Test de optimize_int_columns
    df_test = pd.DataFrame({
        'team_id': [1.0, 2.0, 3.0, None],
        'name': ['A', 'B', 'C', 'D'],
        'score': [1.5, 2.5, 3.5, 4.5]  # Este NO debe convertirse
    })
    
    df_optimized = optimize_int_columns(df_test)
    print("Test optimize_int_columns:")
    print(df_optimized.dtypes)
    print(df_optimized)
