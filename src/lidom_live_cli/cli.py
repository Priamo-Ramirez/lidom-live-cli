"""Comandos CLI para consultar resultados en vivo de LIDOM."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
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
    PlayByPlayEntry,
    PlayByPlayReport,
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
ANSI_BLUE_BRIGHT = "\033[94m"
ANSI_RED_BRIGHT = "\033[91m"
ANSI_YELLOW_BRIGHT = "\033[93m"
ANSI_GREEN_BRIGHT = "\033[92m"
ANSI_MAGENTA_BRIGHT = "\033[95m"
ANSI_ORANGE_APPROX = "\033[33m"

DEFAULT_SCHEDULE_STATUSES = (
    "Scheduled",
    "Pre-Game",
    "Warmup",
    "Delayed Start",
)
TEAM_COLOR_TOKENS: dict[str, str] = {
    "tigres del licey": ANSI_BLUE_BRIGHT,
    "leones del escogido": ANSI_RED_BRIGHT,
    "aguilas cibaenas": ANSI_YELLOW_BRIGHT,
    "gigantes del cibao": ANSI_MAGENTA_BRIGHT,
    "estrellas orientales": ANSI_GREEN_BRIGHT,
    "toros del este": ANSI_ORANGE_APPROX,
}


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
    use_color: bool,
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
            away_team = _team_label(game.away_team, use_color)
            home_team = _team_label(game.home_team, use_color)
            if compact:
                lines.append(
                    f"{game.game_pk}{separator}{away_team} {_score(game.away_score)}-{_score(game.home_score)} "
                    f"{home_team}{separator}{game.status}{separator}{game.start_time_rd}"
                )
            else:
                away_team_fixed = _team_label(game.away_team, use_color, width=26)
                home_team_fixed = _team_label(game.home_team, use_color, width=26)
                lines.append(
                    f"{game.game_pk:<8} {away_team_fixed} {_score(game.away_score):>2}  "
                    f"{home_team_fixed} {_score(game.home_score):>2}  "
                    f"{game.status:<18} {game.start_time_rd}"
                )
    return "\n".join(lines)


def _render_history_table(
    games: list[LidomGameScore],
    start_date_iso: str,
    end_date_iso: str,
    compact: bool,
    show_header: bool,
    separator: str,
    use_color: bool,
) -> str:
    lines: list[str] = []
    if show_header:
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        lines.append(
            f"LIDOM | Rango: {start_date_iso} -> {end_date_iso} | Actualizado: {stamp}"
        )
        lines.append("-" * 122)
        if compact:
            lines.append("Fecha | gamePk | Partido | Estado | Hora RD")
        else:
            lines.append(
                f"{'Fecha':<10} {'gamePk':<8} {'Visitante':<26} {'R':>2}  "
                f"{'Home':<26} {'R':>2}  {'Estado':<18} {'Hora RD'}"
            )
        lines.append("-" * 122)

    if not games:
        lines.append("Sin juegos para el rango indicado.")
    else:
        ordered_games = sorted(games, key=lambda game: (game.official_date, game.start_time_rd, game.game_pk))
        for game in ordered_games:
            away_team = _team_label(game.away_team, use_color)
            home_team = _team_label(game.home_team, use_color)
            if compact:
                lines.append(
                    f"{game.official_date}{separator}{game.game_pk}{separator}"
                    f"{away_team} {_score(game.away_score)}-{_score(game.home_score)} {home_team}"
                    f"{separator}{game.status}{separator}{game.start_time_rd}"
                )
            else:
                away_team_fixed = _team_label(game.away_team, use_color, width=26)
                home_team_fixed = _team_label(game.home_team, use_color, width=26)
                lines.append(
                    f"{game.official_date:<10} {game.game_pk:<8} {away_team_fixed} "
                    f"{_score(game.away_score):>2}  {home_team_fixed} {_score(game.home_score):>2}  "
                    f"{game.status:<18} {game.start_time_rd}"
                )
    return "\n".join(lines)


def _render_schedule_table(
    games: list[LidomGameScore],
    start_date_iso: str,
    end_date_iso: str,
    compact: bool,
    show_header: bool,
    separator: str,
    use_color: bool,
) -> str:
    lines: list[str] = []
    if show_header:
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        lines.append(
            f"LIDOM | Schedule programado: {start_date_iso} -> {end_date_iso} | Actualizado: {stamp}"
        )
        lines.append("-" * 122)
        if compact:
            lines.append("Fecha | gamePk | Partido | Estado | Hora RD")
        else:
            lines.append(
                f"{'Fecha':<10} {'gamePk':<8} {'Visitante':<26} {'R':>2}  "
                f"{'Home':<26} {'R':>2}  {'Estado':<18} {'Hora RD'}"
            )
        lines.append("-" * 122)

    if not games:
        lines.append("Sin juegos programados para el rango indicado.")
    else:
        ordered_games = sorted(games, key=lambda game: (game.official_date, game.start_time_rd, game.game_pk))
        for game in ordered_games:
            away_team = _team_label(game.away_team, use_color)
            home_team = _team_label(game.home_team, use_color)
            if compact:
                matchup = (
                    f"{away_team} vs {home_team}"
                    if game.away_score is None and game.home_score is None
                    else f"{away_team} {_score(game.away_score)}-{_score(game.home_score)} {home_team}"
                )
                lines.append(
                    f"{game.official_date}{separator}{game.game_pk}{separator}"
                    f"{matchup}"
                    f"{separator}{game.status}{separator}{game.start_time_rd}"
                )
            else:
                away_team_fixed = _team_label(game.away_team, use_color, width=26)
                home_team_fixed = _team_label(game.home_team, use_color, width=26)
                lines.append(
                    f"{game.official_date:<10} {game.game_pk:<8} {away_team_fixed} "
                    f"{_score(game.away_score):>2}  {home_team_fixed} {_score(game.home_score):>2}  "
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
            f"{_team_label(snapshot.away_team, use_color)} {_score(snapshot.away_runs)}-{_score(snapshot.home_runs)} "
            f"{_team_label(snapshot.home_team, use_color)} | {inning_label} | Outs: {snapshot.outs} | "
            f"{snapshot.batter}{batter_suffix} vs {snapshot.pitcher}{pitcher_suffix} | "
            f"Conteo {_format_count(snapshot.balls, snapshot.strikes, use_color=False)} | "
            f"Último: {snapshot.last_event} ({last_pitch})"
        )

    separator = "=" * 80
    lines = [
        _style(separator, ANSI_CYAN, use_color),
        _style("LIDOM EN VIVO", ANSI_BOLD, use_color),
        f"Juego: {_team_label(snapshot.away_team, use_color)} vs {_team_label(snapshot.home_team, use_color)}",
        (
            f"Estado: {snapshot.status} | Fecha: {snapshot.official_date or '-'} | "
            f"Estadio: {snapshot.venue or '-'}"
        ),
        (
            f"Marcador: {_team_label(snapshot.away_team, use_color)} {_score(snapshot.away_runs)} - "
            f"{_score(snapshot.home_runs)} {_team_label(snapshot.home_team, use_color)}"
        ),
        f"Inning: {inning_label} | Outs: {snapshot.outs} | Corredores: {snapshot.runners}",
        _style(separator, ANSI_CYAN, use_color),
        "",
        _style("TURNO ACTUAL", ANSI_BOLD, use_color),
        f"- Equipo al bate: {_team_label(snapshot.batting_team, use_color) if snapshot.batting_team else '-'}",
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


def _render_game_stats(summary: GameStatsSummary, use_color: bool) -> str:
    lines = [
        f"Juego {summary.game_pk} | {_team_label(summary.away_team, use_color)} vs {_team_label(summary.home_team, use_color)}",
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
                f"{_team_label(summary.away_team, use_color, width=26)} {_score(summary.away_runs):>2} "
                f"{_score(summary.away_hits):>2} {_score(summary.away_errors):>2} "
                f"{summary.away_avg or '-':>6}"
            ),
            (
                f"{_team_label(summary.home_team, use_color, width=26)} {_score(summary.home_runs):>2} "
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


def _render_play_by_play(
    report: PlayByPlayReport, plays: list[PlayByPlayEntry], compact: bool, with_pitches: bool, use_color: bool
) -> str:
    title = (
        f"Play-by-play | Juego {report.game_pk} | {_team_label(report.away_team, use_color)} vs {_team_label(report.home_team, use_color)} | "
        f"Estado: {report.status}"
    )
    meta = f"Fecha: {report.official_date or '-'} | Estadio: {report.venue or '-'}"

    lines = [title, meta, "-" * 108]
    if not plays:
        lines.append("No hay jugadas para los filtros seleccionados.")
        return "\n".join(lines)

    for play in plays:
        inning = _inning_label(play.half_inning, play.inning)
        score = f"{_score(play.away_score)}-{_score(play.home_score)}"
        scoring_tag = " [SCORING]" if play.is_scoring_play else ""
        if compact:
            compact_line = (
                f"{play.at_bat_index:>3} | {inning:<7} | {play.batter} vs {play.pitcher} | "
                f"{play.result}{scoring_tag} | Score {score}"
            )
            if with_pitches and play.pitch_sequence:
                compact_line += f" | Picheos: {'; '.join(play.pitch_sequence)}"
            lines.append(compact_line)
            continue

        lines.append(
            f"{play.at_bat_index:>3}) {inning} | {_team_label(play.batting_team, use_color) if play.batting_team else '-'} | "
            f"{play.batter} vs {play.pitcher}"
        )
        lines.append(
            f"     Resultado: {play.result}{scoring_tag} | Outs: {play.outs} | "
            f"Score: {_team_label(report.away_team, use_color)} {score} {_team_label(report.home_team, use_color)}"
        )
        lines.append(f"     Picheos en turno: {play.pitch_count}")
        if with_pitches and play.pitch_sequence:
            for event_idx, pitch in enumerate(play.pitch_sequence, start=1):
                lines.append(f"       {event_idx}. {pitch}")
        lines.append("")

    if lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _filter_play_by_play(
    plays: list[PlayByPlayEntry], inning: int | None, team_query: str | None
) -> list[PlayByPlayEntry]:
    filtered = plays
    if inning is not None:
        filtered = [play for play in filtered if play.inning == inning]

    if team_query:
        query = team_query.lower()
        filtered = [
            play
            for play in filtered
            if query in play.batting_team.lower() or query in play.batter.lower()
        ]
    return filtered


def _fetch_filtered_games(
    client: LidomApiClient, date_iso: str, status_filter: str | None, team_filter: str | None
) -> list[LidomGameScore]:
    payload = client.get_schedule(date_iso)
    if not isinstance(payload, dict):
        raise TypeError("Respuesta inválida desde MLB Stats API.")

    games = client.parse_scores(payload)
    statuses = _parse_csv_values(status_filter)
    return _filter_games(games, statuses, team_filter)


def _fetch_filtered_games_range(
    client: LidomApiClient,
    start_date_iso: str,
    end_date_iso: str,
    status_filter: str | None,
    team_filter: str | None,
) -> list[LidomGameScore]:
    payload = client.get_schedule_range(start_date_iso, end_date_iso)
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
    use_color: bool,
) -> None:
    games = _fetch_filtered_games(client, date_iso, status_filter, team_filter)
    if as_json:
        print(json.dumps([asdict(game) for game in games], ensure_ascii=False, indent=2))
        return
    print(_render_table(games, date_iso, compact, show_header, separator, use_color))


def _print_history(
    client: LidomApiClient,
    period: str,
    as_json: bool,
    status_filter: str | None,
    team_filter: str | None,
    compact: bool,
    show_header: bool,
    separator: str,
    use_color: bool,
) -> None:
    start_date, end_date = _resolve_period_dates(period)
    start_date_iso = start_date.isoformat()
    end_date_iso = end_date.isoformat()
    games = _fetch_filtered_games_range(
        client=client,
        start_date_iso=start_date_iso,
        end_date_iso=end_date_iso,
        status_filter=status_filter,
        team_filter=team_filter,
    )
    if as_json:
        print(json.dumps([asdict(game) for game in games], ensure_ascii=False, indent=2))
        return
    print(
        _render_history_table(
            games=games,
            start_date_iso=start_date_iso,
            end_date_iso=end_date_iso,
            compact=compact,
            show_header=show_header,
            separator=separator,
            use_color=use_color,
        )
    )


def _print_schedule(
    client: LidomApiClient,
    period: str,
    anchor_date_iso: str,
    as_json: bool,
    status_filter: str | None,
    team_filter: str | None,
    compact: bool,
    show_header: bool,
    separator: str,
    use_color: bool,
) -> None:
    anchor_date = _parse_iso_date(anchor_date_iso)
    start_date, end_date = _resolve_schedule_dates(period=period, anchor_date=anchor_date)
    effective_status_filter = status_filter or ",".join(DEFAULT_SCHEDULE_STATUSES)
    start_date_iso = start_date.isoformat()
    end_date_iso = end_date.isoformat()
    games = _fetch_filtered_games_range(
        client=client,
        start_date_iso=start_date_iso,
        end_date_iso=end_date_iso,
        status_filter=effective_status_filter,
        team_filter=team_filter,
    )
    if as_json:
        print(json.dumps([asdict(game) for game in games], ensure_ascii=False, indent=2))
        return
    print(
        _render_schedule_table(
            games=games,
            start_date_iso=start_date_iso,
            end_date_iso=end_date_iso,
            compact=compact,
            show_header=show_header,
            separator=separator,
            use_color=use_color,
        )
    )


def _print_at_bat(
    client: LidomApiClient, game_pk: int, as_json: bool, compact: bool, use_color: bool
) -> None:
    snapshot = client.get_current_at_bat(game_pk)
    if as_json:
        print(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2))
        return
    print(_render_at_bat(snapshot, compact=compact, use_color=use_color))


def _watch_at_bat(
    client: LidomApiClient,
    game_pk: int,
    as_json: bool,
    compact: bool,
    use_color: bool,
    interval_seconds: int,
    iterations: int,
    clear_screen: bool,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("El parámetro --interval debe ser mayor que cero.")
    if iterations < 0:
        raise ValueError("El parámetro --iterations no puede ser negativo.")

    loop_count = 0
    while iterations == 0 or loop_count < iterations:
        snapshot = client.get_current_at_bat(game_pk)
        if as_json:
            print(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2))
        else:
            if clear_screen:
                print("\033c", end="")
            print(_render_at_bat(snapshot, compact=compact, use_color=use_color))
        loop_count += 1
        if iterations != 0 and loop_count >= iterations:
            break
        sleep(interval_seconds)


def _print_game_stats(client: LidomApiClient, game_pk: int, as_json: bool, use_color: bool) -> None:
    summary = client.get_game_stats_summary(game_pk)
    if as_json:
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
        return
    print(_render_game_stats(summary, use_color=use_color))


def _print_league_leaders(client: LidomApiClient, season: int, limit: int, as_json: bool) -> None:
    if limit <= 0:
        raise ValueError("El parámetro --limit debe ser mayor que cero.")
    leaders = client.get_league_hitting_leaders(season=season, limit=limit)
    if as_json:
        print(json.dumps([asdict(leader) for leader in leaders], ensure_ascii=False, indent=2))
        return
    print(_render_league_leaders(leaders, season))


def _print_play_by_play(
    client: LidomApiClient,
    game_pk: int,
    as_json: bool,
    compact: bool,
    with_pitches: bool,
    inning_filter: int | None,
    team_filter: str | None,
    use_color: bool,
) -> None:
    report = client.get_play_by_play(game_pk)
    plays = _filter_play_by_play(report.plays, inning=inning_filter, team_query=team_filter)
    if as_json:
        payload = asdict(report)
        payload["plays"] = [asdict(play) for play in plays]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(
        _render_play_by_play(
            report,
            plays=plays,
            compact=compact,
            with_pitches=with_pitches,
            use_color=use_color,
        )
    )


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
    use_color: bool,
) -> None:
    loop_count = 0
    while iterations == 0 or loop_count < iterations:
        games = _fetch_filtered_games(client, date_iso, status_filter, team_filter)
        # Limpia pantalla para mostrar solo la versión más reciente del marcador.
        if clear_screen:
            print("\033c", end="")
        print(_render_table(games, date_iso, compact, show_header, separator, use_color))
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
    now_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

    history_parser = subparsers.add_parser(
        "history",
        help="Muestra resultados para períodos recientes (ayer, última semana, último mes)",
    )
    history_parser.add_argument(
        "--period",
        choices=["yesterday", "last-week", "last-month"],
        default="yesterday",
        help="Período a consultar (default yesterday)",
    )
    history_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    history_parser.add_argument(
        "--status",
        help='Filtra por estado (CSV), por ejemplo: "Final,In Progress"',
    )
    history_parser.add_argument("--team", help="Filtra por equipo (coincidencia parcial)")
    history_parser.add_argument("--compact", action="store_true", help="Usa vista compacta")
    history_parser.add_argument("--no-header", action="store_true", help="Oculta cabecera de la tabla")
    history_parser.add_argument("--separator", default=" | ", help="Separador en modo compacto")
    history_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Muestra juegos programados por día, semana o mes",
    )
    schedule_parser.add_argument(
        "--period",
        choices=["day", "week", "month"],
        default="day",
        help="Rango de schedule a consultar (default day)",
    )
    schedule_parser.add_argument(
        "--date",
        default=get_today_in_dominican_republic(),
        help=f"Fecha ancla YYYY-MM-DD (default hoy en {DOMINICAN_TZ})",
    )
    schedule_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    schedule_parser.add_argument(
        "--status",
        help='Sobrescribe estados programados por defecto con estados CSV, por ejemplo: "Scheduled,Pre-Game"',
    )
    schedule_parser.add_argument("--team", help="Filtra por equipo (coincidencia parcial)")
    schedule_parser.add_argument("--compact", action="store_true", help="Usa vista compacta")
    schedule_parser.add_argument("--no-header", action="store_true", help="Oculta cabecera de la tabla")
    schedule_parser.add_argument("--separator", default=" | ", help="Separador en modo compacto")
    schedule_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

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
    watch_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

    atbat_parser = subparsers.add_parser("atbat", help="Muestra el turno actual (live feed) de un juego")
    atbat_parser.add_argument("--game-pk", type=int, required=True, help="Identificador gamePk del juego")
    atbat_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    atbat_parser.add_argument("--compact", action="store_true", help="Vista de una sola línea")
    atbat_parser.add_argument("--watch", action="store_true", help="Actualiza el turno continuamente")
    atbat_parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Intervalo en segundos entre actualizaciones en modo --watch (default 10)",
    )
    atbat_parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Cantidad de actualizaciones en modo --watch. 0 significa infinito (default 0)",
    )
    atbat_parser.add_argument(
        "--clear",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Limpia pantalla entre actualizaciones en modo --watch (default true)",
    )
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
    game_stats_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

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

    play_by_play_parser = subparsers.add_parser(
        "playbyplay", help="Muestra el play-by-play completo de un juego por gamePk"
    )
    play_by_play_parser.add_argument(
        "--game-pk", type=int, required=True, help="Identificador gamePk del juego"
    )
    play_by_play_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    play_by_play_parser.add_argument("--compact", action="store_true", help="Vista compacta por jugada")
    play_by_play_parser.add_argument(
        "--with-pitches",
        action="store_true",
        help="Incluye secuencia de picheos por turno en la salida de texto",
    )
    play_by_play_parser.add_argument("--inning", type=int, help="Filtra jugadas por inning")
    play_by_play_parser.add_argument(
        "--team", help="Filtra jugadas por equipo al bate o nombre de bateador"
    )
    play_by_play_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

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
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "atbat":
            if args.watch:
                _watch_at_bat(
                    client=client,
                    game_pk=args.game_pk,
                    as_json=args.json,
                    compact=args.compact,
                    use_color=args.color,
                    interval_seconds=args.interval,
                    iterations=args.iterations,
                    clear_screen=args.clear,
                )
            else:
                _print_at_bat(
                    client=client,
                    game_pk=args.game_pk,
                    as_json=args.json,
                    compact=args.compact,
                    use_color=args.color,
                )
            return EXIT_OK

        if args.command == "history":
            _print_history(
                client=client,
                period=args.period,
                as_json=args.json,
                status_filter=args.status,
                team_filter=args.team,
                compact=args.compact,
                show_header=not args.no_header,
                separator=args.separator,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "schedule":
            _print_schedule(
                client=client,
                period=args.period,
                anchor_date_iso=args.date,
                as_json=args.json,
                status_filter=args.status,
                team_filter=args.team,
                compact=args.compact,
                show_header=not args.no_header,
                separator=args.separator,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "game-stats":
            _print_game_stats(client=client, game_pk=args.game_pk, as_json=args.json, use_color=args.color)
            return EXIT_OK

        if args.command == "leaders":
            _print_league_leaders(client=client, season=args.season, limit=args.limit, as_json=args.json)
            return EXIT_OK

        if args.command == "playbyplay":
            _print_play_by_play(
                client=client,
                game_pk=args.game_pk,
                as_json=args.json,
                compact=args.compact,
                with_pitches=args.with_pitches,
                inning_filter=args.inning,
                team_filter=args.team,
                use_color=args.color,
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
            use_color=args.color,
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


def _team_label(team_name: str, use_color: bool, width: int | None = None) -> str:
    if not team_name:
        return team_name
    label = team_name.ljust(width) if width else team_name
    if not use_color:
        return label

    normalized = team_name.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    for token, color in TEAM_COLOR_TOKENS.items():
        if token in normalized:
            return _style(label, color, use_color=True)
    return label


def _resolve_period_dates(period: str, today: date | None = None) -> tuple[date, date]:
    current = today or datetime.now(ZoneInfo(DOMINICAN_TZ)).date()
    if period == "yesterday":
        target = current - timedelta(days=1)
        return target, target
    if period == "last-week":
        return current - timedelta(days=7), current - timedelta(days=1)
    if period == "last-month":
        return current - timedelta(days=30), current - timedelta(days=1)
    raise ValueError(f"Período no soportado: {period}")


def _resolve_schedule_dates(period: str, anchor_date: date) -> tuple[date, date]:
    if period == "day":
        return anchor_date, anchor_date
    if period == "week":
        return anchor_date, anchor_date + timedelta(days=6)
    if period == "month":
        return anchor_date, anchor_date + timedelta(days=29)
    raise ValueError(f"Período de schedule no soportado: {period}")


def _parse_iso_date(date_iso: str) -> date:
    try:
        return datetime.strptime(date_iso, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError(f"Fecha inválida '{date_iso}'. Usa formato YYYY-MM-DD.") from error
