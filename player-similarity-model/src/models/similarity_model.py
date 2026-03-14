"""
similarity_model.py
Modelo de similitud entre jugadores basado en cosine similarity.

Uso:
    model = PlayerSimilarityModel()
    model.load()
    results = model.find_similar_players("Vinicius Junior", top_n=10)
    print(results)
"""

from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from src.utils.feature_config import MODEL_FEATURES, ID_COLUMNS

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL_PATH = _PROJECT_ROOT / "data" / "features" / "features_model.parquet"


class PlayerSimilarityModel:

    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH):
        self.model_path = model_path
        self.df: pd.DataFrame | None = None
        self.feature_matrix: np.ndarray | None = None
        self._is_loaded = False

    def load(self) -> "PlayerSimilarityModel":
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Modelo no encontrado: {self.model_path}\n"
                "Ejecuta primero:\n"
                "  python src/pipeline/build_features.py\n"
                "  python src/pipeline/build_model.py --build"
            )
        self.df = pd.read_parquet(self.model_path)
        missing = [f for f in MODEL_FEATURES if f not in self.df.columns]
        if missing:
            raise ValueError(f"Faltan features en el dataset: {missing}")
        self.feature_matrix = self.df[MODEL_FEATURES].values
        self._is_loaded = True
        print(f"Modelo cargado: {len(self.df)} jugadores, {len(MODEL_FEATURES)} features")
        return self

    def find_similar_players(
        self,
        player_name: str,
        top_n: int = 10,
        exclude_same_team: bool = False,
    ) -> pd.DataFrame:
        if not self._is_loaded:
            raise RuntimeError("Llama a model.load() primero.")

        mask = self.df["player_name"].str.contains(player_name, case=False, na=False)
        matches = self.df[mask]

        if len(matches) == 0:
            suggestions = self._suggest_names(player_name)
            raise ValueError(f"Jugador '{player_name}' no encontrado. ¿Quisiste decir? {suggestions}")
        if len(matches) > 1:
            raise ValueError(
                f"'{player_name}' coincide con varios jugadores: {matches['player_name'].tolist()}\n"
                "Usa el nombre completo."
            )

        idx = matches.index[0]
        sims = cosine_similarity(self.feature_matrix[idx].reshape(1, -1), self.feature_matrix)[0]

        result = self.df.copy()
        result["similarity"] = sims
        result = result[result.index != idx]

        if exclude_same_team:
            result = result[result["team"] != self.df.loc[idx, "team"]]

        result = result.sort_values("similarity", ascending=False).head(top_n)
        out_cols = [c for c in ["player_name", "team", "league", "position", "minutes", "similarity"]
                    if c in result.columns]
        return result[out_cols].reset_index(drop=True)

    def get_player_profile(self, player_name: str) -> pd.Series:
        if not self._is_loaded:
            raise RuntimeError("Llama a model.load() primero.")
        mask = self.df["player_name"].str.contains(player_name, case=False, na=False)
        matches = self.df[mask]
        if len(matches) == 0:
            raise ValueError(f"Jugador '{player_name}' no encontrado.")
        if len(matches) > 1:
            raise ValueError(f"'{player_name}' ambiguo: {matches['player_name'].tolist()}")
        return matches.iloc[0][MODEL_FEATURES]

    def list_players(self) -> pd.DataFrame:
        if not self._is_loaded:
            raise RuntimeError("Llama a model.load() primero.")
        cols = [c for c in ["player_name", "team", "league", "position", "minutes"] if c in self.df.columns]
        return self.df[cols].copy()

    def _suggest_names(self, query: str, n: int = 5) -> list[str]:
        q = query.lower()
        scored = sorted(
            self.df["player_name"].tolist(),
            key=lambda name: sum(c in name.lower() for c in q),
            reverse=True,
        )
        return scored[:n]
