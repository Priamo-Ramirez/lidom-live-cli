"""Comandos CLI para consultar resultados en vivo de LIDOM."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from time import sleep
from urllib.error import HTTPError, URLError

from .client import (
    DOMINICAN_TZ,
    LidomApiClient,
    LidomGameScore,
    get_today_in_dominican_republic,
)

EXIT_OK = 0
EXIT_NETWORK_ERROR = 3
EXIT_RESPONSE_ERROR = 4


def _score(value: int | None) -> str:
    return "-" if value is None else str(value)


def _parse_csv_values(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _filter_games(
    games: list[LidomGameScore], statuses: set[str], team_query: str | None
) -> list[LidomGameScore]:
    filtered = games

    if statuses:
        filtered = [game for game in filtered if game.status.lower() in statuses]

    if team_query:
        query = team_query.lower()
        filtered = [
            game
            for game in filtered
            if query in game.away_team.lower() or query in game.home_team.lower()
        ]

    return filtered


def _render_table(
    games: list[LidomGameScore],
    date_iso: str,
    compact: bool,
    show_header: bool,
    separator: str,
) -> str:
    lines: list[str] = []
    if show_header:
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        lines.append(f"LIDOM | Fecha: {date_iso} | Actualizado: {stamp}")
        lines.append("-" * 92)
        if compact:
            lines.append("Partido | Estado | Hora RD")
        else:
            lines.append(
                f"{'Visitante':<26} {'R':>2}  {'Home':<26} {'R':>2}  {'Estado':<18} {'Hora RD'}"
            )
        lines.append("-" * 92)

    if not games:
        lines.append("Sin juegos para la fecha indicada.")
    else:
        for game in games:
            if compact:
                lines.append(
                    f"{game.away_team} {_score(game.away_score)}-{_score(game.home_score)} "
                    f"{game.home_team}{separator}{game.status}{separator}{game.start_time_rd}"
                )
            else:
                lines.append(
                    f"{game.away_team:<26} {_score(game.away_score):>2}  "
                    f"{game.home_team:<26} {_score(game.home_score):>2}  "
                    f"{game.status:<18} {game.start_time_rd}"
                )
    return "\n".join(lines)


def _fetch_filtered_games(
    client: LidomApiClient, date_iso: str, status_filter: str | None, team_filter: str | None
) -> list[LidomGameScore]:
    payload = client.get_schedule(date_iso)
    if not isinstance(payload, dict):
        raise TypeError("Respuesta inválida desde MLB Stats API.")

    games = client.parse_scores(payload)
    statuses = _parse_csv_values(status_filter)
    return _filter_games(games, statuses, team_filter)


def _print_now(
    client: LidomApiClient,
    date_iso: str,
    as_json: bool,
    status_filter: str | None,
    team_filter: str | None,
    compact: bool,
    show_header: bool,
    separator: str,
) -> None:
    games = _fetch_filtered_games(client, date_iso, status_filter, team_filter)
    if as_json:
        print(json.dumps([asdict(game) for game in games], ensure_ascii=False, indent=2))
        return
    print(_render_table(games, date_iso, compact, show_header, separator))


def _print_watch(
    client: LidomApiClient,
    date_iso: str,
    interval_seconds: int,
    status_filter: str | None,
    team_filter: str | None,
    iterations: int,
    clear_screen: bool,
    compact: bool,
    show_header: bool,
    separator: str,
) -> None:
    loop_count = 0
    while iterations == 0 or loop_count < iterations:
        games = _fetch_filtered_games(client, date_iso, status_filter, team_filter)
        # Limpia pantalla para mostrar solo la versión más reciente del marcador.
        if clear_screen:
            print("\033c", end="")
        print(_render_table(games, date_iso, compact, show_header, separator))
        loop_count += 1
        if iterations != 0 and loop_count >= iterations:
            break
        sleep(interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI de resultados en vivo para LIDOM")
    subparsers = parser.add_subparsers(dest="command", required=True)

    now_parser = subparsers.add_parser("now", help="Muestra resultados para una fecha")
    now_parser.add_argument("--date", default=get_today_in_dominican_republic(), help="Fecha YYYY-MM-DD")
    now_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    now_parser.add_argument(
        "--status",
        help='Filtra por estado (CSV), por ejemplo: "In Progress,Final"',
    )
    now_parser.add_argument("--team", help="Filtra por equipo (coincidencia parcial)")
    now_parser.add_argument("--compact", action="store_true", help="Usa vista compacta")
    now_parser.add_argument("--no-header", action="store_true", help="Oculta cabecera de la tabla")
    now_parser.add_argument("--separator", default=" | ", help="Separador en modo compacto")

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
    watch_parser.add_argument(
        "--status",
        help='Filtra por estado (CSV), por ejemplo: "In Progress,Final"',
    )
    watch_parser.add_argument("--team", help="Filtra por equipo (coincidencia parcial)")
    watch_parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Cantidad de actualizaciones. 0 significa infinito (default 0)",
    )
    watch_parser.add_argument(
        "--clear",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Limpia pantalla entre actualizaciones (default true)",
    )
    watch_parser.add_argument("--compact", action="store_true", help="Usa vista compacta")
    watch_parser.add_argument("--no-header", action="store_true", help="Oculta cabecera de la tabla")
    watch_parser.add_argument("--separator", default=" | ", help="Separador en modo compacto")

    args = parser.parse_args()
    client = LidomApiClient()

    try:
        if args.command == "now":
            _print_now(
                client=client,
                date_iso=args.date,
                as_json=args.json,
                status_filter=args.status,
                team_filter=args.team,
                compact=args.compact,
                show_header=not args.no_header,
                separator=args.separator,
            )
            return EXIT_OK

        _print_watch(
            client=client,
            date_iso=args.date,
            interval_seconds=args.interval,
            status_filter=args.status,
            team_filter=args.team,
            iterations=args.iterations,
            clear_screen=args.clear,
            compact=args.compact,
            show_header=not args.no_header,
            separator=args.separator,
        )
        return EXIT_OK
    except KeyboardInterrupt:
        print("\nSeguimiento finalizado por usuario.", file=sys.stderr)
        return EXIT_OK
    except (HTTPError, URLError) as error:
        print(f"Error de red/API: {error}", file=sys.stderr)
        print("Sugerencia: vuelve a intentar el comando en unos segundos.", file=sys.stderr)
        return EXIT_NETWORK_ERROR
    except (TypeError, ValueError) as error:
        print(f"Error de respuesta: {error}", file=sys.stderr)
        return EXIT_RESPONSE_ERROR
