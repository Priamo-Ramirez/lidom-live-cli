"""Comandos CLI para consultar resultados en vivo de LIDOM."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from time import sleep

from .client import DOMINICAN_TZ, LidomApiClient, LidomGameScore, get_today_in_dominican_republic


def _score(value: int | None) -> str:
    return "-" if value is None else str(value)


def _render_table(games: list[LidomGameScore], date_iso: str) -> str:
    lines: list[str] = []
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines.append(f"LIDOM | Fecha: {date_iso} | Actualizado: {stamp}")
    lines.append("-" * 92)
    lines.append(f"{'Visitante':<26} {'R':>2}  {'Home':<26} {'R':>2}  {'Estado':<18} {'Hora RD'}")
    lines.append("-" * 92)

    if not games:
        lines.append("Sin juegos para la fecha indicada.")
    else:
        for game in games:
            lines.append(
                f"{game.away_team:<26} {_score(game.away_score):>2}  "
                f"{game.home_team:<26} {_score(game.home_score):>2}  "
                f"{game.status:<18} {game.start_time_rd}"
            )
    return "\n".join(lines)


def _print_now(client: LidomApiClient, date_iso: str, as_json: bool) -> None:
    payload = client.get_schedule(date_iso)
    games = client.parse_scores(payload)
    if as_json:
        print(json.dumps([asdict(game) for game in games], ensure_ascii=False, indent=2))
        return
    print(_render_table(games, date_iso))


def _print_watch(client: LidomApiClient, date_iso: str, interval_seconds: int) -> None:
    while True:
        payload = client.get_schedule(date_iso)
        games = client.parse_scores(payload)
        # Limpia pantalla para mostrar solo la versión más reciente del marcador.
        print("\033c", end="")
        print(_render_table(games, date_iso))
        sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI de resultados en vivo para LIDOM")
    subparsers = parser.add_subparsers(dest="command", required=True)

    now_parser = subparsers.add_parser("now", help="Muestra resultados para una fecha")
    now_parser.add_argument("--date", default=get_today_in_dominican_republic(), help="Fecha YYYY-MM-DD")
    now_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")

    watch_parser = subparsers.add_parser("watch", help="Actualiza resultados continuamente")
    watch_parser.add_argument(
        "--date",
        default=get_today_in_dominican_republic(),
        help=f"Fecha YYYY-MM-DD (default hoy en {DOMINICAN_TZ})",
    )
    watch_parser.add_argument(
        "--interval",
        type=int,
        default=20,
        help="Intervalo en segundos entre actualizaciones (default 20)",
    )

    args = parser.parse_args()
    client = LidomApiClient()

    if args.command == "now":
        _print_now(client, args.date, args.json)
        return

    _print_watch(client, args.date, args.interval)
