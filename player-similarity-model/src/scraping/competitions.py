"""
competitions.py — Carga y acceso a la configuración declarativa de competiciones.

Lee competitions.yaml y expone objetos tipados para que el pipeline, el scraper
y la API nunca lean el YAML directamente ni hardcodeen IDs de WhoScored.

Uso:

    from ws_platform.identity.competitions import get_competition, list_competitions

    comp = get_competition("laliga")
    print(comp.display_name)          # "La Liga"
    print(comp.season("2025-2026").fixtures_url)

    for comp in list_competitions():
        print(comp.comp_key, comp.tier)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterator

import yaml

import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Modelos de datos (dataclasses, sin pydantic — son config estática del YAML)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageConfig:
    """Configuración de un stage (fase) dentro de una temporada europea."""
    ws_stage_id: int
    fixtures_url: str


@dataclass(frozen=True)
class SeasonConfig:
    """
    Configuración de una temporada para una competición.

    Las ligas nacionales tienen un único stage (ws_stage_id + fixtures_url
    directamente en el nivel de temporada). Las competiciones europeas (UCL, UEL)
    tienen stages múltiples: 'league' y 'knockout'.
    """
    ws_season_id: int
    # Para ligas nacionales (stage único):
    ws_stage_id: int | None = None
    fixtures_url: str | None = None
    # Para competiciones europeas (stages múltiples):
    stages: dict[str, StageConfig] = field(default_factory=dict)

    @property
    def is_multi_stage(self) -> bool:
        """True si la competición tiene stages separados (UCL, UEL)."""
        return bool(self.stages)

    def iter_stages(self) -> Iterator[tuple[str, StageConfig]]:
        """
        Itera sobre los stages disponibles.

        Para ligas nacionales devuelve un único stage sintético con el nombre 'default'.
        Para competiciones europeas devuelve ('league', ...) y ('knockout', ...).
        """
        if self.is_multi_stage:
            yield from self.stages.items()
        else:
            assert self.ws_stage_id is not None
            assert self.fixtures_url is not None
            yield "default", StageConfig(
                ws_stage_id=self.ws_stage_id,
                fixtures_url=self.fixtures_url,
            )


@dataclass(frozen=True)
class CompetitionConfig:
    """Configuración completa de una competición (todas las temporadas)."""
    comp_key: str
    display_name: str
    country: str
    tier: int
    ws_region_id: int
    ws_tournament_id: int
    shield_path: str
    seasons: dict[str, SeasonConfig]

    def season(self, season_key: str) -> SeasonConfig:
        """
        Devuelve la configuración de una temporada específica.

        Raises:
            KeyError: Si la temporada no existe en el YAML.
        """
        if season_key not in self.seasons:
            available = list(self.seasons.keys())
            raise KeyError(
                f"Temporada '{season_key}' no encontrada en '{self.comp_key}'. "
                f"Disponibles: {available}"
            )
        return self.seasons[season_key]

    def latest_season(self) -> tuple[str, SeasonConfig]:
        """Devuelve (season_key, SeasonConfig) de la temporada más reciente."""
        latest_key = sorted(self.seasons.keys())[-1]
        return latest_key, self.seasons[latest_key]


# ---------------------------------------------------------------------------
# Loader del YAML
# ---------------------------------------------------------------------------

def _parse_season(season_key: str, season_data: dict) -> SeasonConfig:
    """Convierte un bloque de temporada del YAML a SeasonConfig."""
    ws_season_id = season_data["ws_season_id"]

    if "stages" in season_data:
        # Competición europea: stages múltiples
        stages = {
            stage_name: StageConfig(
                ws_stage_id=stage_data["ws_stage_id"],
                fixtures_url=stage_data["fixtures_url"],
            )
            for stage_name, stage_data in season_data["stages"].items()
        }
        return SeasonConfig(ws_season_id=ws_season_id, stages=stages)
    else:
        # Liga nacional: stage único
        return SeasonConfig(
            ws_season_id=ws_season_id,
            ws_stage_id=season_data["ws_stage_id"],
            fixtures_url=season_data["fixtures_url"],
        )


def _parse_competition(comp_key: str, comp_data: dict) -> CompetitionConfig:
    """Convierte un bloque de competición del YAML a CompetitionConfig."""
    seasons = {
        str(season_key): _parse_season(str(season_key), season_data)
        for season_key, season_data in comp_data.get("seasons", {}).items()
    }
    return CompetitionConfig(
        comp_key=comp_key,
        display_name=comp_data["display_name"],
        country=comp_data["country"],
        tier=comp_data["tier"],
        ws_region_id=comp_data["ws_region_id"],
        ws_tournament_id=comp_data["ws_tournament_id"],
        shield_path=comp_data["shield_path"],
        seasons=seasons,
    )


@lru_cache(maxsize=1)
def _load_yaml(yaml_path: str) -> dict[str, CompetitionConfig]:
    """
    Carga y parsea el YAML de competiciones. Cacheado en memoria.

    Args:
        yaml_path: Ruta absoluta al archivo competitions.yaml (str para hashability).

    Returns:
        Dict de comp_key → CompetitionConfig.
    """
    path = Path(yaml_path)
    log.info("cargando_competitions_yaml", path=str(path))

    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    competitions: dict[str, CompetitionConfig] = {}
    for comp_key, comp_data in raw.get("competitions", {}).items():
        competitions[comp_key] = _parse_competition(comp_key, comp_data)

    log.info("competitions_cargadas", total=len(competitions), keys=list(competitions.keys()))
    return competitions


def _get_registry() -> dict[str, CompetitionConfig]:
    """Devuelve el registro de competiciones."""
    # La ruta del YAML es estática — se resuelve relativa a este paquete.
    # competitions.py está en src/scraping/, el YAML en src/config/
    yaml_path = str(Path(__file__).resolve().parent.parent / "config" / "competitions.yaml")
    return _load_yaml(yaml_path)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def get_competition(comp_key: str) -> CompetitionConfig:
    """
    Devuelve la configuración de una competición por su clave.

    Args:
        comp_key: Clave snake_case de la competición (ej: "laliga", "champions_league").

    Raises:
        KeyError: Si comp_key no existe en competitions.yaml.
    """
    registry = _get_registry()
    if comp_key not in registry:
        available = list(registry.keys())
        raise KeyError(
            f"Competición '{comp_key}' no encontrada. Disponibles: {available}"
        )
    return registry[comp_key]


def list_competitions(tier: int | None = None) -> list[CompetitionConfig]:
    """
    Lista todas las competiciones configuradas.

    Args:
        tier: Si se especifica, filtra por tier (0=europeo, 1=primera división).

    Returns:
        Lista de CompetitionConfig ordenada por tier y comp_key.
    """
    registry = _get_registry()
    comps = list(registry.values())
    if tier is not None:
        comps = [c for c in comps if c.tier == tier]
    return sorted(comps, key=lambda c: (c.tier, c.comp_key))


def get_competition_keys() -> list[str]:
    """Devuelve la lista de comp_key disponibles."""
    return list(_get_registry().keys())
