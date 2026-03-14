"""
normalize_features.py
Imputa NaN, aplica StandardScaler y guarda artefactos del modelo.

Input:  data/features/features_model_raw.parquet
Output: data/features/features_model.parquet
        models/scalers/feature_scaler.joblib
"""

from pathlib import Path
import pandas as pd
from sklearn.preprocessing import StandardScaler
import joblib

from src.utils.feature_config import MODEL_FEATURES, ID_COLUMNS

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

INPUT_PATH  = _PROJECT_ROOT / "data" / "features" / "features_model_raw.parquet"
OUTPUT_PATH = _PROJECT_ROOT / "data" / "features" / "features_model.parquet"
SCALER_PATH = _PROJECT_ROOT / "models" / "scalers" / "feature_scaler.joblib"


def normalize(
    input_path: Path = INPUT_PATH,
    output_path: Path = OUTPUT_PATH,
    scaler_path: Path = SCALER_PATH,
) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(
            f"Dataset no encontrado: {input_path}\n"
            "Ejecuta primero: python src/pipeline/build_features.py"
        )

    df = pd.read_parquet(input_path)
    print(f"Dataset cargado: {df.shape[0]} jugadores, {df.shape[1]} columnas")

    missing = [f for f in MODEL_FEATURES if f not in df.columns]
    if missing:
        raise ValueError(f"Faltan features: {missing}")

    X_raw = df[MODEL_FEATURES].copy()

    # Imputar NaN residuales con mediana
    for col in X_raw.columns[X_raw.isnull().any()]:
        X_raw[col] = X_raw[col].fillna(X_raw[col].median())

    scaler = StandardScaler()
    X_scaled = pd.DataFrame(scaler.fit_transform(X_raw), columns=MODEL_FEATURES, index=df.index)

    id_cols = [c for c in ID_COLUMNS if c in df.columns]
    df_out = pd.concat([df[id_cols], X_scaled], axis=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_parquet(output_path, index=False)
    print(f"Guardado: {output_path.name}  ({len(df_out)} jugadores, {len(MODEL_FEATURES)} features)")

    scaler_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, scaler_path)
    print(f"Scaler:   {scaler_path.name}")

    return df_out


if __name__ == "__main__":
    normalize()
