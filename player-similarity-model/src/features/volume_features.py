"""
volume_features.py
Calcula las métricas de volumen por 90 minutos (bloque B del dataset de features).

Criterio: ¿cuánto hace este jugador?
Todas las métricas se expresan en unidades por 90 minutos jugados.

Para columnas que FBRef ya ofrece como _por90 se usan directamente.
Para columnas que FBRef solo ofrece como totales acumulados se dividen por `p90`.
"""

import pandas as pd


# Columnas que FBRef ya calcula como per 90 — se usan directamente
_FBREF_PER90 = {
    "goals_p90":              "goles_por90",
    "assists_p90":            "asistencias_por90",
    "xg_p90":                 "xg_por90",
    "npxg_p90":               "npxg_por90",
    "xa_p90":                 "xg_asistencias_por90",
    "shots_p90":              "tiros_por90",
    "shots_on_target_p90":    "tiros_a_puerta_por90",
}

# Columnas brutas que hay que dividir por p90 manualmente
_RAW_TO_P90 = {
    "touches_p90":                "toques",
    "touches_att_box_p90":        "toques_area_rival",
    "passes_p90":                 "pases",
    "progressive_passes_p90":     "pases_progresivos",
    "progressive_carries_p90":    "conducciones_progresivas",
    "dribbles_attempted_p90":     "regates_intentados",
    "dribbles_completed_p90":     "regates_exitosos",
    "fouls_won_p90":              "faltas_recibidas",
    "crosses_p90":                "centros",
}


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade las métricas de volumen per 90 al DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset filtrado de load_fbref.py (debe incluir columna `p90`).

    Returns
    -------
    pd.DataFrame
        DataFrame original con las columnas de volumen añadidas.
    """
    if "p90" not in df.columns:
        raise ValueError("El DataFrame no tiene la columna 'p90'. Ejecuta load_fbref.load_and_filter() primero.")

    result = df.copy()

    # Métricas que FBRef ya entrega como per 90
    for feature_name, source_col in _FBREF_PER90.items():
        result[feature_name] = result[source_col]

    # Métricas que calculamos dividiendo el acumulado entre p90
    for feature_name, source_col in _RAW_TO_P90.items():
        result[feature_name] = result[source_col] / result["p90"]

    # Duelos aéreos totales per 90 (ganados + perdidos)
    result["aerial_duels_p90"] = (
        result["duelos_aereos_ganados"] + result["duelos_aereos_perdidos"]
    ) / result["p90"]

    return result


def get_volume_feature_names() -> list[str]:
    """Devuelve la lista de nombres de features de volumen generadas."""
    return (
        list(_FBREF_PER90.keys())
        + list(_RAW_TO_P90.keys())
        + ["aerial_duels_p90"]
    )
