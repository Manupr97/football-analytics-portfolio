"""
style_features.py
Calcula las métricas de estilo (bloque C del dataset de features).

Criterio: ¿cómo juega este jugador, independientemente del volumen?
Todas las métricas son ratios o porcentajes acotados entre 0 y 1 (o 0-100).

Las divisiones por cero se manejan con fillna(0): si un jugador no tiene
denominador (p.ej. 0 pases), el ratio se define como 0.
"""

import pandas as pd
import numpy as np


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """
    Calcula numerator / denominator con manejo seguro de división por cero.
    Devuelve 0.0 donde el denominador es 0 o NaN.
    """
    return numerator.div(denominator.replace(0, np.nan)).fillna(0.0)


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade las métricas de estilo al DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset con columnas de FBRef (tras load_fbref y opcionalmente volume_features).

    Returns
    -------
    pd.DataFrame
        DataFrame original con las columnas de estilo añadidas.
    """
    result = df.copy()

    # -------------------------------------------------------------------------
    # TIROS
    # -------------------------------------------------------------------------

    # % tiros a puerta (FBRef ya lo calcula, lo reutilizamos directamente)
    result["shot_accuracy_pct"] = result["porc_tiros_a_puerta"]

    # Calidad media de cada tiro (npxG por tiro)
    result["npxg_per_shot"] = result["npxg_por_tiro"]

    # Distancia media del tiro (en yardas)
    result["avg_shot_distance"] = result["dist_media_tiro"]

    # -------------------------------------------------------------------------
    # REGATES
    # -------------------------------------------------------------------------

    # % regates completados sobre intentados
    result["dribble_success_pct"] = result["porc_regates_exitosos"]

    # -------------------------------------------------------------------------
    # PASES — precisión y distribución por longitud
    # -------------------------------------------------------------------------

    # Precisión general de pase (%)
    result["pass_accuracy_pct"] = result["porc_precision_pase"]

    # % pases cortos sobre el total de pases
    result["short_pass_pct"] = _safe_ratio(result["pases_cortos"], result["pases"]) * 100

    # % pases largos sobre el total de pases
    result["long_pass_pct"] = _safe_ratio(result["pases_largos"], result["pases"]) * 100

    # -------------------------------------------------------------------------
    # PASES — intencionalidad y progresión
    # -------------------------------------------------------------------------

    # % pases progresivos sobre el total (mide tendencia a buscar la portería)
    result["progressive_pass_ratio"] = _safe_ratio(
        result["pases_progresivos"], result["pases"]
    ) * 100

    # % pases al tercio final (presencia en zona ofensiva)
    result["final_third_pass_ratio"] = _safe_ratio(
        result["pases_tercio_final"], result["pases"]
    ) * 100

    # % pases al área rival (llegada a zona de peligro)
    result["passes_into_box_ratio"] = _safe_ratio(
        result["pases_area"], result["pases"]
    ) * 100

    # % centros sobre el total de pases (perfil de extremo rematador vs interior)
    result["cross_ratio"] = _safe_ratio(result["centros"], result["pases"]) * 100

    # % pases al hueco (throughballs — tendencia a romper líneas)
    result["throughball_ratio"] = _safe_ratio(
        result["pases_al_hueco"], result["pases"]
    ) * 100

    # -------------------------------------------------------------------------
    # TOQUES — zonas de influencia
    # -------------------------------------------------------------------------

    # % toques en el tercio ofensivo
    result["touches_att_third_pct"] = _safe_ratio(
        result["toques_tercio_ofensivo"], result["toques"]
    ) * 100

    # % toques en el tercio medio (perfil más retrasado)
    result["touches_mid_third_pct"] = _safe_ratio(
        result["toques_tercio_medio"], result["toques"]
    ) * 100

    # % toques en el área rival (presencia en la zona de mayor peligro)
    result["touches_box_ratio"] = _safe_ratio(
        result["toques_area_rival"], result["toques"]
    ) * 100

    # -------------------------------------------------------------------------
    # CONDUCCIONES — progresividad
    # -------------------------------------------------------------------------

    # % de la distancia conducida que es progresiva (avanza hacia portería)
    result["carry_progression_ratio"] = _safe_ratio(
        result["distancia_conducciones_progresivas"],
        result["distancia_conducciones"]
    ) * 100

    # % conducciones que terminan en el tercio final
    result["final_third_carry_ratio"] = _safe_ratio(
        result["conducciones_tercio_final"], result["conducciones"]
    ) * 100

    # -------------------------------------------------------------------------
    # DUELOS AÉREOS
    # -------------------------------------------------------------------------

    # % duelos aéreos ganados (FBRef ya lo calcula)
    result["aerial_win_pct"] = result["porc_duelos_aereos_ganados"]

    # -------------------------------------------------------------------------
    # CREACIÓN DE JUEGO
    # -------------------------------------------------------------------------

    # Ratio de participación en la creación vs en la finalización:
    # xA / (xG + xA) → 0 = puro finalizador, 1 = puro creador
    result["creation_vs_finishing_ratio"] = _safe_ratio(
        result["xg_asistencias"],
        result["xg"] + result["xg_asistencias"]
    )

    return result


def get_style_feature_names() -> list[str]:
    """Devuelve la lista de nombres de features de estilo generadas."""
    return [
        # Tiros
        "shot_accuracy_pct",
        "npxg_per_shot",
        "avg_shot_distance",
        # Regates
        "dribble_success_pct",
        # Pases — precisión
        "pass_accuracy_pct",
        "short_pass_pct",
        "long_pass_pct",
        # Pases — intencionalidad
        "progressive_pass_ratio",
        "final_third_pass_ratio",
        "passes_into_box_ratio",
        "cross_ratio",
        "throughball_ratio",
        # Toques
        "touches_att_third_pct",
        "touches_mid_third_pct",
        "touches_box_ratio",
        # Conducciones
        "carry_progression_ratio",
        "final_third_carry_ratio",
        # Duelos
        "aerial_win_pct",
        # Creación
        "creation_vs_finishing_ratio",
    ]
