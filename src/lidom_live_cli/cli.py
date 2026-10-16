"""Comandos CLI para consultar resultados en vivo de LIDOM."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from time import sleep
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from .client import (
    DOMINICAN_TZ,
    AtBatSnapshot,
    GameStatsSummary,
    LeagueHittingLeader,
    LidomApiClient,
    LidomGameScore,
    get_today_in_dominican_republic,
)

EXIT_OK = 0
EXIT_NETWORK_ERROR = 3
EXIT_RESPONSE_ERROR = 4

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_CYAN = "\033[36m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_RED = "\033[31m"


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
        lines.append("-" * 108)
        if compact:
            lines.append("gamePk | Partido | Estado | Hora RD")
        else:
            lines.append(
                f"{'gamePk':<8} {'Visitante':<26} {'R':>2}  {'Home':<26} {'R':>2}  {'Estado':<18} {'Hora RD'}"
            )
        lines.append("-" * 108)

    if not games:
        lines.append("Sin juegos para la fecha indicada.")
    else:
        for game in games:
            if compact:
                lines.append(
                    f"{game.game_pk}{separator}{game.away_team} {_score(game.away_score)}-{_score(game.home_score)} "
                    f"{game.home_team}{separator}{game.status}{separator}{game.start_time_rd}"
                )
            else:
                lines.append(
                    f"{game.game_pk:<8} {game.away_team:<26} {_score(game.away_score):>2}  "
                    f"{game.home_team:<26} {_score(game.home_score):>2}  "
                    f"{game.status:<18} {game.start_time_rd}"
                )
    return "\n".join(lines)


def _render_at_bat(snapshot: AtBatSnapshot, compact: bool, use_color: bool) -> str:
    inning_label = _inning_label(snapshot.half_inning, snapshot.inning)
    pitcher_suffix = f" ({_hand_short(snapshot.pitcher_hand)})" if snapshot.pitcher_hand else ""
    batter_suffix = f" ({_hand_short(snapshot.batter_side)})" if snapshot.batter_side else ""
    last_pitch = snapshot.last_pitch_type
    if snapshot.last_pitch_speed is not None:
        last_pitch = f"{last_pitch}, {snapshot.last_pitch_speed:.1f} mph"

    if compact:
        return (
            f"{snapshot.away_team} {_score(snapshot.away_runs)}-{_score(snapshot.home_runs)} "
            f"{snapshot.home_team} | {inning_label} | Outs: {snapshot.outs} | "
            f"{snapshot.batter}{batter_suffix} vs {snapshot.pitcher}{pitcher_suffix} | "
            f"Conteo {_format_count(snapshot.balls, snapshot.strikes, use_color=False)} | "
            f"Último: {snapshot.last_event} ({last_pitch})"
        )

    separator = "=" * 80
    lines = [
        _style(separator, ANSI_CYAN, use_color),
        _style("LIDOM EN VIVO", ANSI_BOLD, use_color),
        f"Juego: {snapshot.away_team} vs {snapshot.home_team}",
        (
            f"Estado: {snapshot.status} | Fecha: {snapshot.official_date or '-'} | "
            f"Estadio: {snapshot.venue or '-'}"
        ),
        (
            f"Marcador: {snapshot.away_team} {_score(snapshot.away_runs)} - "
            f"{_score(snapshot.home_runs)} {snapshot.home_team}"
        ),
        f"Inning: {inning_label} | Outs: {snapshot.outs} | Corredores: {snapshot.runners}",
        _style(separator, ANSI_CYAN, use_color),
        "",
        _style("TURNO ACTUAL", ANSI_BOLD, use_color),
        f"- Equipo al bate: {snapshot.batting_team or '-'}",
        f"- Bateador: {snapshot.batter}{batter_suffix}",
        f"- Pitcher: {snapshot.pitcher}{pitcher_suffix}",
        f"- Conteo: {_format_count(snapshot.balls, snapshot.strikes, use_color)}",
        f"- Último pitcheo: {snapshot.last_event} ({last_pitch})",
        "",
        _style("SECUENCIA DEL TURNO", ANSI_BOLD, use_color),
    ]

    if snapshot.event_sequence:
        for idx, event in enumerate(snapshot.event_sequence, start=1):
            lines.append(f"{idx}) {event}")
    else:
        lines.append("Sin eventos registrados para este turno.")

    lines.extend(
        [
            "",
            _style("CONTEXTO RÁPIDO", ANSI_BOLD, use_color),
            f"- Bateador hoy: {snapshot.batter_today}",
            f"- Pitcher hoy: {snapshot.pitcher_today}",
            f"- Próximo bateador: {snapshot.on_deck or '-'}",
            _style(separator, ANSI_CYAN, use_color),
        ]
    )
    return "\n".join(lines)


def _render_game_stats(summary: GameStatsSummary) -> str:
    lines = [
        f"Juego {summary.game_pk} | {summary.away_team} vs {summary.home_team}",
        f"Estado: {summary.status}",
    ]
    if summary.current_inning:
        lines.append(f"Inning: {summary.inning_state} {summary.current_inning}")
    lines.extend(
        [
            "",
            f"{'Equipo':<26} {'R':>2} {'H':>2} {'E':>2} {'AVG':>6}",
            "-" * 44,
            (
                f"{summary.away_team:<26} {_score(summary.away_runs):>2} "
                f"{_score(summary.away_hits):>2} {_score(summary.away_errors):>2} "
                f"{summary.away_avg or '-':>6}"
            ),
            (
                f"{summary.home_team:<26} {_score(summary.home_runs):>2} "
                f"{_score(summary.home_hits):>2} {_score(summary.home_errors):>2} "
                f"{summary.home_avg or '-':>6}"
            ),
        ]
    )
    return "\n".join(lines)


def _render_league_leaders(leaders: list[LeagueHittingLeader], season: int) -> str:
    lines = [f"Líderes de bateo LIDOM | Temporada {season}", "-" * 74]
    if not leaders:
        lines.append("Sin estadísticas de bateo disponibles para esta temporada.")
        return "\n".join(lines)

    lines.append(f"{'#':>2} {'Jugador':<28} {'Equipo':<22} {'AVG':>6} {'AB':>4} {'H':>4} {'OPS':>6}")
    lines.append("-" * 74)
    for leader in leaders:
        lines.append(
            f"{leader.rank:>2} {leader.player_name:<28} {leader.team_name:<22} "
            f"{leader.avg:>6} {_score(leader.at_bats):>4} {_score(leader.hits):>4} "
            f"{leader.ops or '-':>6}"
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


def _print_at_bat(
    client: LidomApiClient, game_pk: int, as_json: bool, compact: bool, use_color: bool
) -> None:
    snapshot = client.get_current_at_bat(game_pk)
    if as_json:
        print(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2))
        return
    print(_render_at_bat(snapshot, compact=compact, use_color=use_color))


def _print_game_stats(client: LidomApiClient, game_pk: int, as_json: bool) -> None:
    summary = client.get_game_stats_summary(game_pk)
    if as_json:
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
        return
    print(_render_game_stats(summary))


def _print_league_leaders(client: LidomApiClient, season: int, limit: int, as_json: bool) -> None:
    if limit <= 0:
        raise ValueError("El parámetro --limit debe ser mayor que cero.")
    leaders = client.get_league_hitting_leaders(season=season, limit=limit)
    if as_json:
        print(json.dumps([asdict(leader) for leader in leaders], ensure_ascii=False, indent=2))
        return
    print(_render_league_leaders(leaders, season))


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

    atbat_parser = subparsers.add_parser("atbat", help="Muestra el turno actual (live feed) de un juego")
    atbat_parser.add_argument("--game-pk", type=int, required=True, help="Identificador gamePk del juego")
    atbat_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    atbat_parser.add_argument("--compact", action="store_true", help="Vista de una sola línea")
    atbat_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI en la salida detallada (default false)",
    )

    game_stats_parser = subparsers.add_parser(
        "game-stats", help="Muestra line score y stats clave de un juego por gamePk"
    )
    game_stats_parser.add_argument("--game-pk", type=int, required=True, help="Identificador gamePk del juego")
    game_stats_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")

    leaders_parser = subparsers.add_parser(
        "leaders", help="Muestra líderes de bateo (AVG) de la temporada de LIDOM"
    )
    leaders_parser.add_argument(
        "--season",
        type=int,
        default=datetime.now(ZoneInfo(DOMINICAN_TZ)).year,
        help="Temporada (por ejemplo 2025). Default: año actual",
    )
    leaders_parser.add_argument("--limit", type=int, default=10, help="Cantidad máxima de jugadores (default 10)")
    leaders_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")

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

        if args.command == "atbat":
            _print_at_bat(
                client=client,
                game_pk=args.game_pk,
                as_json=args.json,
                compact=args.compact,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "game-stats":
            _print_game_stats(client=client, game_pk=args.game_pk, as_json=args.json)
            return EXIT_OK

        if args.command == "leaders":
            _print_league_leaders(client=client, season=args.season, limit=args.limit, as_json=args.json)
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


def _inning_label(half_inning: str, inning: int | None) -> str:
    half = {"top": "Alta", "bottom": "Baja"}.get(half_inning.lower(), half_inning.capitalize())
    if not half:
        half = "-"
    return f"{half} {inning}" if inning else half


def _hand_short(side_description: str) -> str:
    side = side_description.strip().lower()
    if side == "left":
        return "L"
    if side == "right":
        return "R"
    if side == "switch":
        return "S"
    return side_description


def _format_count(balls: int, strikes: int, use_color: bool) -> str:
    if not use_color:
        return f"{balls}-{strikes}"
    return f"{_style(str(balls), ANSI_YELLOW, True)}-{_style(str(strikes), ANSI_RED, True)}"


def _style(value: str, color_code: str, use_color: bool) -> str:
    if not use_color:
        return value
    return f"{color_code}{value}{ANSI_RESET}"
