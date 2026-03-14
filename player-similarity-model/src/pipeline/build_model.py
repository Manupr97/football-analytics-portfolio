"""
build_model.py
CLI para construir y consultar el modelo de similitud de jugadores.

Uso:
  # Paso 1: construir features desde WhoScored
  python src/pipeline/build_features.py

  # Paso 2: normalizar y guardar modelo
  python src/pipeline/build_model.py --build

  # Consultar similares
  python src/pipeline/build_model.py --player "Vinicius"
  python src/pipeline/build_model.py --player "Haaland" --top 15 --exclude-same-team

  # Ver todos los jugadores disponibles
  python src/pipeline/build_model.py --list-players
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing.normalize_features import normalize
from src.models.similarity_model import PlayerSimilarityModel


def cmd_build() -> None:
    print("=" * 55)
    print("Normalizando features y construyendo modelo...")
    print("=" * 55)
    normalize()
    print("\nModelo listo.")


def cmd_find_similar(player_name: str, top_n: int, exclude_same_team: bool) -> None:
    model = PlayerSimilarityModel()
    model.load()
    print(f"\nJugadores más similares a: {player_name}")
    print("-" * 65)
    results = model.find_similar_players(player_name, top_n=top_n, exclude_same_team=exclude_same_team)
    _print_results(results)


def cmd_list_players() -> None:
    model = PlayerSimilarityModel()
    model.load()
    players = model.list_players()
    print(f"\n{len(players)} jugadores disponibles:\n")
    print(players.to_string(index=False))


def _print_results(results) -> None:
    w = 26
    header = f"{'player_name':<{w}} {'team':<22} {'league':<18} {'pos':<8} {'min':>5}  similarity"
    print(header)
    print("-" * len(header))
    for _, row in results.iterrows():
        print(
            f"{str(row.get('player_name','')):<{w}} "
            f"{str(row.get('team','')):<22} "
            f"{str(row.get('league','')):<18} "
            f"{str(row.get('position','')):<8} "
            f"{int(row.get('minutes',0)):>5}  "
            f"{row['similarity']:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Modelo de similitud de jugadores — WhoScored 2025-26")
    parser.add_argument("--build", action="store_true", help="Normalizar y guardar modelo.")
    parser.add_argument("--player", type=str, default=None, help="Jugador a consultar.")
    parser.add_argument("--top", type=int, default=10, help="Nº de similares (default: 10).")
    parser.add_argument("--exclude-same-team", action="store_true", help="Excluir mismo equipo.")
    parser.add_argument("--list-players", action="store_true", help="Listar todos los jugadores.")
    args = parser.parse_args()

    if not any([args.build, args.player, args.list_players]):
        parser.print_help()
        sys.exit(0)

    if args.build:
        cmd_build()
    if args.list_players:
        cmd_list_players()
    if args.player:
        try:
            cmd_find_similar(args.player, args.top, args.exclude_same_team)
        except ValueError as e:
            print(f"\nError: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
