"""
config.py
Configuración centralizada para el pipeline de scraping Segunda RFEF Grupo 3
"""
import os
from pathlib import Path
from dataclasses import dataclass, field

# Ruta por defecto (puede sobrescribirse con variable de entorno)
_DEFAULT_BASE_DIR = Path(r"C:\Users\manue\OneDrive\Sports Data Campus\Máster Python\Proyecto Sant Andreu")


def _get_base_dir() -> Path:
    env_path = os.environ.get("SANT_ANDREU_PROJECT_DIR")
    if env_path:
        return Path(env_path)
    return _DEFAULT_BASE_DIR


@dataclass(frozen=True)
class Config:
    """Configuración inmutable del proyecto"""

    BASE_DIR: Path = field(default_factory=_get_base_dir)
    BESOCCER_BASE_URL: str = "https://es.besoccer.com"
    COMPETITION_URL: str = "https://es.besoccer.com/competicion/clasificacion/segunda_division_rfef/2026/grupo3"
    COMPETITION_NAME: str = "SegundaRFEF"
    GROUP: str = "Grupo3"
    SEASON: str = "2025-26"
    MAX_RETRIES: int = 3
    RETRY_BACKOFF: float = 2.0
    REQUEST_TIMEOUT: int = 30
    MIN_DELAY: float = 1.0
    MAX_DELAY: float = 3.0
    NUM_WORKERS: int = 5
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    @property
    def DATA_RAW_DIR(self) -> Path:
        return self.BASE_DIR / "data_raw"

    @property
    def DATA_PROCESSED_DIR(self) -> Path:
        return self.BASE_DIR / "data_processed"

    @property
    def OUTPUTS_POWERBI_DIR(self) -> Path:
        return self.BASE_DIR / "outputs_powerbi"

    @property
    def LOGS_DIR(self) -> Path:
        return self.BASE_DIR / "logs"

    @property
    def META_DIR(self) -> Path:
        return self.DATA_PROCESSED_DIR / "meta"

    # === CACHÉ HTML ===
    @property
    def HTML_CACHE_DIR(self) -> Path:
        return self.BASE_DIR / "html"

    @property
    def LINEUPS_HTML_DIR(self) -> Path:
        return self.HTML_CACHE_DIR / "lineups"

    @property
    def EVENTS_HTML_DIR(self) -> Path:
        return self.HTML_CACHE_DIR / "events"

    # Alias de compatibilidad
    @property
    def LINEUPS_RAW_DIR(self) -> Path:
        return self.LINEUPS_HTML_DIR

    @property
    def EVENTS_RAW_DIR(self) -> Path:
        return self.EVENTS_HTML_DIR

    @property
    def CLASSIFICATION_RAW_DIR(self) -> Path:
        return self.DATA_RAW_DIR / "classification"

    @property
    def MATCHES_RAW_DIR(self) -> Path:
        return self.DATA_RAW_DIR / "matches"

    @property
    def DIM_EQUIPOS_PATH(self) -> Path:
        return self.DATA_PROCESSED_DIR / "dim_equipos.parquet"

    @property
    def DIM_PARTIDOS_PATH(self) -> Path:
        return self.DATA_PROCESSED_DIR / "dim_partidos.parquet"

    @property
    def DIM_JUGADORES_PATH(self) -> Path:
        return self.DATA_PROCESSED_DIR / "dim_jugadores.parquet"

    @property
    def FACT_GOALS_PATH(self) -> Path:
        return self.DATA_PROCESSED_DIR / "fact_goals.parquet"

    @property
    def FACT_SUBSTITUTIONS_PATH(self) -> Path:
        return self.DATA_PROCESSED_DIR / "fact_substitutions.parquet"

    @property
    def FACT_APPEARANCES_PATH(self) -> Path:
        return self.DATA_PROCESSED_DIR / "fact_appearances.parquet"

    @property
    def PROCESSED_MATCHES_PATH(self) -> Path:
        return self.META_DIR / "processed_matches.parquet"

    @property
    def REQUEST_HEADERS(self) -> dict:
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def get_team_matches_url(self, team_slug: str) -> str:
        return f"{self.BESOCCER_BASE_URL}/equipo/partidos/{team_slug}"

    def get_match_url(self, match_id: int) -> str:
        return f"{self.BESOCCER_BASE_URL}/partido/{match_id}"


config = Config()


def get_config() -> Config:
    return config


if __name__ == "__main__":
    cfg = get_config()
    print(f"Proyecto: {cfg.COMPETITION_NAME} {cfg.GROUP} {cfg.SEASON}")
    print(f"Base dir: {cfg.BASE_DIR}")
    print(f"Caché HTML: {cfg.HTML_CACHE_DIR}")
