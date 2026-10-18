"""Comandos CLI para consultar resultados en vivo de LIDOM."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from io import StringIO
from time import sleep
from unicodedata import normalize
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

LEADER_CATEGORIES: dict[str, tuple[str, str, str, str]] = {
    "avg": ("hitting", "avg", "desc", "AVG"),
    "hr": ("hitting", "homeRuns", "desc", "HR"),
    "rbi": ("hitting", "rbi", "desc", "RBI"),
    "obp": ("hitting", "obp", "desc", "OBP"),
    "ops": ("hitting", "ops", "desc", "OPS"),
    "era": ("pitching", "era", "asc", "ERA"),
    "k": ("pitching", "strikeOuts", "desc", "K"),
    "saves": ("pitching", "saves", "desc", "SV"),
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
                matchup = (
                    f"{away_team} vs {home_team}"
                    if game.away_score is None and game.home_score is None
                    else f"{away_team} {_score(game.away_score)}-{_score(game.home_score)} {home_team}"
                )
                lines.append(
                    f"{game.game_pk}{separator}{matchup}{separator}{game.status}{separator}{game.start_time_rd}"
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


def _render_standings(rows: list[dict[str, object]], season: int, use_color: bool) -> str:
    lines = [f"Standings LIDOM | Temporada {season}", "-" * 74]
    if not rows:
        lines.append("Sin datos de standings para la temporada indicada.")
        return "\n".join(lines)

    lines.append(f"{'#':>2} {'Equipo':<26} {'W':>3} {'L':>3} {'PCT':>6} {'GB':>6} {'Racha':>7}")
    lines.append("-" * 74)
    for row in rows:
        team_name = _team_label(str(row.get("team", "")), use_color, width=26)
        lines.append(
            f"{int(row.get('rank', 0)):>2} {team_name} "
            f"{int(row.get('wins', 0)):>3} {int(row.get('losses', 0)):>3} "
            f"{row.get('pct', '-')!s:>6} {row.get('gb', '-')!s:>6} {row.get('streak', '-')!s:>7}"
        )
    return "\n".join(lines)


def _render_boxscore(report: dict[str, object], use_color: bool) -> str:
    lines = [
        (
            f"Boxscore | Juego {report.get('game_pk')} | "
            f"{_team_label(str(report.get('away_team', '')), use_color)} vs "
            f"{_team_label(str(report.get('home_team', '')), use_color)}"
        ),
        f"Estado: {report.get('status', '-')}",
        "-" * 92,
    ]

    teams = report.get("teams", [])
    for team in teams if isinstance(teams, list) else []:
        team_name = _team_label(str(team.get("team_name", "")), use_color)
        lines.append(f"\n{team_name}")
        lines.append("Bateo:")
        batting = team.get("batting", [])
        if batting:
            for row in batting[:15]:
                lines.append(f"  - {row.get('player')} ({row.get('position')}): {row.get('summary')}")
        else:
            lines.append("  - Sin líneas de bateo disponibles")

        lines.append("Pitcheo:")
        pitching = team.get("pitching", [])
        if pitching:
            for row in pitching[:10]:
                lines.append(f"  - {row.get('player')} ({row.get('position')}): {row.get('summary')}")
        else:
            lines.append("  - Sin líneas de pitcheo disponibles")
    return "\n".join(lines)


def _render_player_report(player_rows: list[dict[str, object]], season: int) -> str:
    lines = [f"Jugador(es) LIDOM | Temporada {season}", "-" * 88]
    if not player_rows:
        lines.append("No se encontraron jugadores para los filtros indicados.")
        return "\n".join(lines)

    for row in player_rows:
        lines.append(f"{row.get('player_name')} ({row.get('team_name')})")
        lines.append(
            f"  Hitting: G {row.get('h_g', '-')} | AVG {row.get('h_avg', '-')} | "
            f"OBP {row.get('h_obp', '-')} | OPS {row.get('h_ops', '-')} | HR {row.get('h_hr', '-')} | RBI {row.get('h_rbi', '-')}"
        )
        lines.append(
            f"  Pitching: G {row.get('p_g', '-')} | ERA {row.get('p_era', '-')} | "
            f"W-L {row.get('p_w', '-')}-{row.get('p_l', '-')} | SV {row.get('p_sv', '-')} | K {row.get('p_k', '-')}"
        )
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


def _normalize_text(value: str) -> str:
    ascii_value = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return ascii_value.lower().strip()


def _resolve_output_format(format_name: str, json_flag: bool) -> str:
    if json_flag:
        return "json"
    return format_name


def _rows_to_csv(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if value is None else value for key, value in row.items()})
    return output.getvalue().rstrip("\n")


def _rows_to_markdown(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body_lines = []
    for row in rows:
        body_lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return "\n".join([header_line, separator_line, *body_lines])


def _render_rows_output(rows: list[dict[str, object]], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2)
    if output_format == "csv":
        return _rows_to_csv(rows)
    if output_format == "md":
        return _rows_to_markdown(rows)
    raise ValueError(f"Formato de salida no soportado: {output_format}")


def _game_rows(games: list[LidomGameScore]) -> list[dict[str, object]]:
    return [
        {
            "game_pk": game.game_pk,
            "official_date": game.official_date,
            "start_time_rd": game.start_time_rd,
            "away_team": game.away_team,
            "home_team": game.home_team,
            "away_score": game.away_score,
            "home_score": game.home_score,
            "status": game.status,
        }
        for game in games
    ]


def _extract_standings_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    records = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(records, list) or not records:
        return []
    team_records = records[0].get("teamRecords", [])
    if not isinstance(team_records, list):
        return []

    rows: list[dict[str, object]] = []
    for item in team_records:
        if not isinstance(item, dict):
            continue
        rank_raw = item.get("divisionRank") or item.get("leagueRank") or "0"
        try:
            rank = int(str(rank_raw))
        except ValueError:
            rank = 0
        rows.append(
            {
                "rank": rank,
                "team": (item.get("team") or {}).get("name", ""),
                "wins": item.get("wins", 0),
                "losses": item.get("losses", 0),
                "pct": item.get("winningPercentage", "-"),
                "gb": item.get("gamesBack", "-"),
                "streak": ((item.get("streak") or {}).get("streakCode") or "-"),
            }
        )
    return sorted(rows, key=lambda row: int(row.get("rank", 0)))


def _extract_boxscore_report(live_feed_payload: dict[str, object], team_filter: str) -> dict[str, object]:
    game_data = live_feed_payload.get("gameData", {}) if isinstance(live_feed_payload, dict) else {}
    live_data = live_feed_payload.get("liveData", {}) if isinstance(live_feed_payload, dict) else {}
    teams_meta = game_data.get("teams", {}) if isinstance(game_data, dict) else {}
    boxscore = live_data.get("boxscore", {}) if isinstance(live_data, dict) else {}
    box_teams = boxscore.get("teams", {}) if isinstance(boxscore, dict) else {}

    selected_sides = ["away", "home"]
    if team_filter in {"away", "home"}:
        selected_sides = [team_filter]

    teams_output: list[dict[str, object]] = []
    for side in selected_sides:
        side_data = box_teams.get(side, {}) if isinstance(box_teams, dict) else {}
        players_map = side_data.get("players", {}) if isinstance(side_data, dict) else {}
        batting_order = side_data.get("batters", []) if isinstance(side_data, dict) else []
        pitching_order = side_data.get("pitchers", []) if isinstance(side_data, dict) else []

        batting_rows: list[dict[str, object]] = []
        for player_id in batting_order if isinstance(batting_order, list) else []:
            player = players_map.get(f"ID{player_id}", {}) if isinstance(players_map, dict) else {}
            batting_summary = ((player.get("stats") or {}).get("batting") or {}).get("summary")
            if not batting_summary:
                continue
            batting_rows.append(
                {
                    "player": (player.get("person") or {}).get("fullName", ""),
                    "position": ((player.get("position") or {}).get("abbreviation") or "-"),
                    "summary": batting_summary,
                }
            )

        pitching_rows: list[dict[str, object]] = []
        for player_id in pitching_order if isinstance(pitching_order, list) else []:
            player = players_map.get(f"ID{player_id}", {}) if isinstance(players_map, dict) else {}
            pitching_summary = ((player.get("stats") or {}).get("pitching") or {}).get("summary")
            if not pitching_summary:
                continue
            pitching_rows.append(
                {
                    "player": (player.get("person") or {}).get("fullName", ""),
                    "position": ((player.get("position") or {}).get("abbreviation") or "-"),
                    "summary": pitching_summary,
                }
            )

        teams_output.append(
            {
                "side": side,
                "team_name": (teams_meta.get(side) or {}).get("name", ""),
                "batting": batting_rows,
                "pitching": pitching_rows,
            }
        )

    return {
        "game_pk": live_feed_payload.get("gamePk", 0),
        "status": (game_data.get("status") or {}).get("detailedState", ""),
        "away_team": (teams_meta.get("away") or {}).get("name", ""),
        "home_team": (teams_meta.get("home") or {}).get("name", ""),
        "teams": teams_output,
    }


def _extract_stats_splits(payload: dict[str, object]) -> list[dict[str, object]]:
    stats = payload.get("stats", []) if isinstance(payload, dict) else []
    if not isinstance(stats, list) or not stats:
        return []
    splits = stats[0].get("splits", [])
    return splits if isinstance(splits, list) else []


def _build_player_rows(
    hitting_splits: list[dict[str, object]],
    pitching_splits: list[dict[str, object]],
    player_id: int | None,
    name_query: str | None,
) -> list[dict[str, object]]:
    players: dict[int, dict[str, object]] = {}

    def ensure_player(split: dict[str, object]) -> dict[str, object] | None:
        player = split.get("player", {}) if isinstance(split, dict) else {}
        if not isinstance(player, dict):
            return None
        pid = player.get("id")
        if not isinstance(pid, int):
            return None
        entry = players.setdefault(
            pid,
            {
                "player_id": pid,
                "player_name": player.get("fullName", ""),
                "team_name": (split.get("team") or {}).get("name", ""),
            },
        )
        if not entry.get("team_name"):
            entry["team_name"] = (split.get("team") or {}).get("name", "")
        return entry

    for split in hitting_splits:
        entry = ensure_player(split)
        if not entry:
            continue
        stat = split.get("stat", {}) if isinstance(split, dict) else {}
        if not isinstance(stat, dict):
            stat = {}
        entry.update(
            {
                "h_g": stat.get("gamesPlayed"),
                "h_avg": stat.get("avg"),
                "h_obp": stat.get("obp"),
                "h_ops": stat.get("ops"),
                "h_hr": stat.get("homeRuns"),
                "h_rbi": stat.get("rbi"),
            }
        )

    for split in pitching_splits:
        entry = ensure_player(split)
        if not entry:
            continue
        stat = split.get("stat", {}) if isinstance(split, dict) else {}
        if not isinstance(stat, dict):
            stat = {}
        entry.update(
            {
                "p_g": stat.get("gamesPlayed"),
                "p_era": stat.get("era"),
                "p_w": stat.get("wins"),
                "p_l": stat.get("losses"),
                "p_sv": stat.get("saves"),
                "p_k": stat.get("strikeOuts"),
            }
        )

    rows = list(players.values())
    if player_id is not None:
        rows = [row for row in rows if row.get("player_id") == player_id]
    if name_query:
        normalized_query = _normalize_text(name_query)
        rows = [
            row
            for row in rows
            if normalized_query in _normalize_text(str(row.get("player_name", "")))
        ]
    rows.sort(key=lambda row: _normalize_text(str(row.get("player_name", ""))))
    return rows


def _extract_leader_rows(
    payload: dict[str, object], stat_key: str, top: int
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rank, split in enumerate(_extract_stats_splits(payload), start=1):
        if not isinstance(split, dict):
            continue
        stat = split.get("stat", {})
        if not isinstance(stat, dict):
            stat = {}
        rows.append(
            {
                "rank": rank,
                "player_name": (split.get("player") or {}).get("fullName", ""),
                "team_name": (split.get("team") or {}).get("name", ""),
                "value": stat.get(stat_key),
            }
        )
        if len(rows) >= top:
            break
    return rows


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
    output_format: str,
    status_filter: str | None,
    team_filter: str | None,
    compact: bool,
    show_header: bool,
    separator: str,
    use_color: bool,
) -> None:
    games = _fetch_filtered_games(client, date_iso, status_filter, team_filter)
    if output_format != "text":
        print(_render_rows_output(_game_rows(games), output_format))
        return
    print(_render_table(games, date_iso, compact, show_header, separator, use_color))


def _print_history(
    client: LidomApiClient,
    period: str,
    output_format: str,
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
    if output_format != "text":
        print(_render_rows_output(_game_rows(games), output_format))
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
    output_format: str,
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
    if output_format != "text":
        print(_render_rows_output(_game_rows(games), output_format))
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
    alert: bool,
    bell: bool,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("El parámetro --interval debe ser mayor que cero.")
    if iterations < 0:
        raise ValueError("El parámetro --iterations no puede ser negativo.")

    loop_count = 0
    previous_snapshot: AtBatSnapshot | None = None
    while iterations == 0 or loop_count < iterations:
        snapshot = client.get_current_at_bat(game_pk)
        alert_lines: list[str] = []
        if alert and previous_snapshot is not None:
            alert_lines = _detect_atbat_alerts(previous_snapshot, snapshot)
        if as_json:
            print(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2))
        else:
            if clear_screen:
                print("\033c", end="")
            print(_render_at_bat(snapshot, compact=compact, use_color=use_color))
            if alert_lines:
                for line in alert_lines:
                    print(f"ALERTA: {line}")
        if alert_lines and bell:
            print("\a", end="")
        previous_snapshot = snapshot
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


def _print_league_leaders(
    client: LidomApiClient,
    season: int,
    top: int,
    category: str,
    output_format: str,
    use_color: bool,
) -> None:
    if top <= 0:
        raise ValueError("El parámetro --top debe ser mayor que cero.")
    category_meta = LEADER_CATEGORIES.get(category)
    if category_meta is None:
        raise ValueError(f"Categoría no soportada: {category}")
    group, sort_stat, order, label = category_meta
    payload = client.get_season_stats(
        group=group,
        season=season,
        limit=top,
        sort_stat=sort_stat,
        order=order,
    )
    rows = _extract_leader_rows(payload, stat_key=sort_stat, top=top)
    if output_format != "text":
        print(_render_rows_output(rows, output_format))
        return

    lines = [f"Líderes LIDOM ({label}) | Temporada {season}", "-" * 74]
    if not rows:
        lines.append("Sin datos disponibles para la categoría solicitada.")
        print("\n".join(lines))
        return
    lines.append(f"{'#':>2} {'Jugador':<28} {'Equipo':<22} {'Valor':>10}")
    lines.append("-" * 74)
    for row in rows:
        team_name = _team_label(str(row.get("team_name", "")), use_color, width=22)
        lines.append(
            f"{int(row.get('rank', 0)):>2} {row.get('player_name', '')!s:<28} {team_name} "
            f"{row.get('value', '-')!s:>10}"
        )
    print("\n".join(lines))


def _print_standings(
    client: LidomApiClient, season: int, output_format: str, use_color: bool
) -> None:
    payload = client.get_standings(season=season)
    rows = _extract_standings_rows(payload)
    if output_format != "text":
        print(_render_rows_output(rows, output_format))
        return
    print(_render_standings(rows, season=season, use_color=use_color))


def _print_boxscore(
    client: LidomApiClient, game_pk: int, team_filter: str, output_format: str, use_color: bool
) -> None:
    payload = client.get_live_feed(game_pk)
    report = _extract_boxscore_report(payload, team_filter=team_filter)
    if output_format != "text":
        rows: list[dict[str, object]] = []
        teams = report.get("teams", [])
        for team in teams if isinstance(teams, list) else []:
            for row in team.get("batting", []):
                rows.append(
                    {
                        "type": "batting",
                        "team": team.get("team_name"),
                        "player": row.get("player"),
                        "position": row.get("position"),
                        "summary": row.get("summary"),
                    }
                )
            for row in team.get("pitching", []):
                rows.append(
                    {
                        "type": "pitching",
                        "team": team.get("team_name"),
                        "player": row.get("player"),
                        "position": row.get("position"),
                        "summary": row.get("summary"),
                    }
                )
        print(_render_rows_output(rows, output_format))
        return
    print(_render_boxscore(report, use_color=use_color))


def _print_player(
    client: LidomApiClient,
    season: int,
    player_id: int | None,
    player_name: str | None,
    output_format: str,
) -> None:
    if player_id is None and not player_name:
        raise ValueError("Debes indicar --id o --name para el comando player.")

    hitting_payload = client.get_season_stats(group="hitting", season=season, limit=1000)
    pitching_payload = client.get_season_stats(group="pitching", season=season, limit=1000)
    rows = _build_player_rows(
        hitting_splits=_extract_stats_splits(hitting_payload),
        pitching_splits=_extract_stats_splits(pitching_payload),
        player_id=player_id,
        name_query=player_name,
    )
    if output_format != "text":
        print(_render_rows_output(rows, output_format))
        return
    print(_render_player_report(rows, season=season))


def _print_today(
    client: LidomApiClient,
    output_format: str,
    status_filter: str | None,
    team_filter: str | None,
    compact: bool,
    show_header: bool,
    separator: str,
    use_color: bool,
) -> None:
    _print_now(
        client=client,
        date_iso=get_today_in_dominican_republic(),
        output_format=output_format,
        status_filter=status_filter,
        team_filter=team_filter,
        compact=compact,
        show_header=show_header,
        separator=separator,
        use_color=use_color,
    )


def _print_next_games(
    client: LidomApiClient,
    from_date_iso: str,
    team_filter: str | None,
    count: int,
    output_format: str,
    compact: bool,
    show_header: bool,
    separator: str,
    use_color: bool,
) -> None:
    if count <= 0:
        raise ValueError("El parámetro --count debe ser mayor que cero.")
    from_date = _parse_iso_date(from_date_iso)
    to_date = from_date + timedelta(days=30)
    games = _fetch_filtered_games_range(
        client=client,
        start_date_iso=from_date.isoformat(),
        end_date_iso=to_date.isoformat(),
        status_filter=",".join(DEFAULT_SCHEDULE_STATUSES),
        team_filter=team_filter,
    )
    ordered_games = sorted(games, key=lambda game: (game.official_date, game.start_time_rd, game.game_pk))[:count]
    if output_format != "text":
        print(_render_rows_output(_game_rows(ordered_games), output_format))
        return
    print(
        _render_schedule_table(
            games=ordered_games,
            start_date_iso=from_date.isoformat(),
            end_date_iso=to_date.isoformat(),
            compact=compact,
            show_header=show_header,
            separator=separator,
            use_color=use_color,
        )
    )


def _run_tui(client: LidomApiClient, date_iso: str, interval_seconds: int, team_filter: str | None) -> None:
    if interval_seconds <= 0:
        raise ValueError("El parámetro --interval debe ser mayor que cero.")

    try:
        import curses
    except Exception as error:  # pragma: no cover
        raise ValueError("No fue posible cargar curses para el modo TUI.") from error

    def _draw(stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.nodelay(True)
        while True:
            games = _fetch_filtered_games(client, date_iso, status_filter=None, team_filter=team_filter)
            stdscr.erase()
            stdscr.addstr(0, 0, "LIDOM TUI (q para salir)")
            stdscr.addstr(1, 0, f"Fecha: {date_iso} | Actualiza cada {interval_seconds}s")
            stdscr.addstr(2, 0, "-" * 90)
            stdscr.addstr(3, 0, "gamePk   Partido                                    Estado            Hora RD")
            stdscr.addstr(4, 0, "-" * 90)
            row = 5
            for game in games[:15]:
                line = (
                    f"{game.game_pk:<8} {game.away_team} vs {game.home_team}"
                )
                trimmed = f"{line[:50]:<50} {game.status[:16]:<16} {game.start_time_rd}"
                stdscr.addstr(row, 0, trimmed)
                row += 1
            if not games:
                stdscr.addstr(row, 0, "Sin juegos para mostrar.")

            stdscr.refresh()
            for _ in range(interval_seconds * 10):
                key = stdscr.getch()
                if key in {ord("q"), ord("Q")}:
                    return
                sleep(0.1)

    curses.wrapper(_draw)


def _print_play_by_play(
    client: LidomApiClient,
    game_pk: int,
    output_format: str,
    compact: bool,
    with_pitches: bool,
    inning_filter: int | None,
    team_filter: str | None,
    use_color: bool,
) -> None:
    report = client.get_play_by_play(game_pk)
    plays = _filter_play_by_play(report.plays, inning=inning_filter, team_query=team_filter)
    if output_format != "text":
        rows = []
        for play in plays:
            rows.append(
                {
                    "at_bat_index": play.at_bat_index,
                    "inning": _inning_label(play.half_inning, play.inning),
                    "batting_team": play.batting_team,
                    "batter": play.batter,
                    "pitcher": play.pitcher,
                    "result": play.result,
                    "outs": play.outs,
                    "away_score": play.away_score,
                    "home_score": play.home_score,
                    "is_scoring_play": play.is_scoring_play,
                    "pitch_count": play.pitch_count,
                }
            )
        print(_render_rows_output(rows, output_format))
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
    alert: bool,
    bell: bool,
) -> None:
    loop_count = 0
    previous_games_by_pk: dict[int, LidomGameScore] = {}
    while iterations == 0 or loop_count < iterations:
        games = _fetch_filtered_games(client, date_iso, status_filter, team_filter)
        alert_lines: list[str] = []
        if alert and previous_games_by_pk:
            alert_lines = _detect_game_alerts(previous_games_by_pk, games)
        # Limpia pantalla para mostrar solo la versión más reciente del marcador.
        if clear_screen:
            print("\033c", end="")
        print(_render_table(games, date_iso, compact, show_header, separator, use_color))
        if alert_lines:
            for line in alert_lines:
                print(f"ALERTA: {line}")
            if bell:
                print("\a", end="")
        previous_games_by_pk = {game.game_pk: game for game in games}
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
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )
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
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )
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
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )
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
    watch_parser.add_argument("--alert", action="store_true", help="Muestra alertas en cambios de marcador/estado")
    watch_parser.add_argument("--bell", action="store_true", help="Emite campana terminal cuando hay alertas")

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
    atbat_parser.add_argument("--alert", action="store_true", help="Muestra alertas cuando cambia el turno")
    atbat_parser.add_argument("--bell", action="store_true", help="Emite campana terminal cuando hay alertas")

    game_stats_parser = subparsers.add_parser(
        "game-stats", help="Muestra line score y stats clave de un juego por gamePk"
    )
    game_stats_parser.add_argument("--game-pk", type=int, required=True, help="Identificador gamePk del juego")
    game_stats_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    game_stats_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Formato de salida (default text)",
    )
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
    leaders_parser.add_argument(
        "--category",
        choices=list(LEADER_CATEGORIES.keys()),
        default="avg",
        help="Categoría de líderes (default avg)",
    )
    leaders_parser.add_argument("--top", type=int, default=10, help="Cantidad máxima de jugadores (default 10)")
    leaders_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    leaders_parser.add_argument(
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )
    leaders_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

    play_by_play_parser = subparsers.add_parser(
        "playbyplay", help="Muestra el play-by-play completo de un juego por gamePk"
    )
    play_by_play_parser.add_argument(
        "--game-pk", type=int, required=True, help="Identificador gamePk del juego"
    )
    play_by_play_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    play_by_play_parser.add_argument(
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )
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

    standings_parser = subparsers.add_parser("standings", help="Muestra tabla de posiciones LIDOM")
    standings_parser.add_argument(
        "--season",
        type=int,
        default=datetime.now(ZoneInfo(DOMINICAN_TZ)).year,
        help="Temporada (default año actual)",
    )
    standings_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    standings_parser.add_argument(
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )
    standings_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

    boxscore_parser = subparsers.add_parser("boxscore", help="Muestra boxscore de un juego por gamePk")
    boxscore_parser.add_argument("--game-pk", type=int, required=True, help="Identificador gamePk del juego")
    boxscore_parser.add_argument("--team", choices=["all", "away", "home"], default="all", help="Lado del juego")
    boxscore_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    boxscore_parser.add_argument(
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )
    boxscore_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

    player_parser = subparsers.add_parser("player", help="Muestra estadísticas de temporada de un jugador")
    player_parser.add_argument("--id", type=int, help="ID del jugador en MLB Stats API")
    player_parser.add_argument("--name", help="Nombre del jugador (coincidencia parcial)")
    player_parser.add_argument(
        "--season",
        type=int,
        default=datetime.now(ZoneInfo(DOMINICAN_TZ)).year,
        help="Temporada (default año actual)",
    )
    player_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    player_parser.add_argument(
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )

    today_parser = subparsers.add_parser("today", help="Alias de now para la fecha de hoy")
    today_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    today_parser.add_argument(
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )
    today_parser.add_argument(
        "--status",
        help='Filtra por estado (CSV), por ejemplo: "In Progress,Final"',
    )
    today_parser.add_argument("--team", help="Filtra por equipo (coincidencia parcial)")
    today_parser.add_argument("--compact", action="store_true", help="Usa vista compacta")
    today_parser.add_argument("--no-header", action="store_true", help="Oculta cabecera de la tabla")
    today_parser.add_argument("--separator", default=" | ", help="Separador en modo compacto")
    today_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

    next_parser = subparsers.add_parser("next", help="Muestra próximos juegos programados")
    next_parser.add_argument(
        "--from-date",
        default=get_today_in_dominican_republic(),
        help=f"Fecha ancla YYYY-MM-DD (default hoy en {DOMINICAN_TZ})",
    )
    next_parser.add_argument("--team", help="Filtra por equipo (coincidencia parcial)")
    next_parser.add_argument("--count", type=int, default=1, help="Cantidad de juegos próximos a mostrar")
    next_parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    next_parser.add_argument(
        "--format",
        choices=["text", "json", "csv", "md"],
        default="text",
        help="Formato de salida (default text)",
    )
    next_parser.add_argument("--compact", action="store_true", help="Usa vista compacta")
    next_parser.add_argument("--no-header", action="store_true", help="Oculta cabecera de la tabla")
    next_parser.add_argument("--separator", default=" | ", help="Separador en modo compacto")
    next_parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Activa colores ANSI para nombres de equipos (default false)",
    )

    tui_parser = subparsers.add_parser("tui", help="Vista interactiva simple en terminal (q para salir)")
    tui_parser.add_argument(
        "--date",
        default=get_today_in_dominican_republic(),
        help=f"Fecha YYYY-MM-DD (default hoy en {DOMINICAN_TZ})",
    )
    tui_parser.add_argument("--interval", type=int, default=10, help="Intervalo en segundos de refresco")
    tui_parser.add_argument("--team", help="Filtra por equipo (coincidencia parcial)")

    args = parser.parse_args()
    client = LidomApiClient()

    try:
        if args.command == "now":
            output_format = _resolve_output_format(args.format, args.json)
            _print_now(
                client=client,
                date_iso=args.date,
                output_format=output_format,
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
                    alert=args.alert,
                    bell=args.bell,
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
            output_format = _resolve_output_format(args.format, args.json)
            _print_history(
                client=client,
                period=args.period,
                output_format=output_format,
                status_filter=args.status,
                team_filter=args.team,
                compact=args.compact,
                show_header=not args.no_header,
                separator=args.separator,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "schedule":
            output_format = _resolve_output_format(args.format, args.json)
            _print_schedule(
                client=client,
                period=args.period,
                anchor_date_iso=args.date,
                output_format=output_format,
                status_filter=args.status,
                team_filter=args.team,
                compact=args.compact,
                show_header=not args.no_header,
                separator=args.separator,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "game-stats":
            output_format = _resolve_output_format(args.format, args.json)
            if output_format == "json":
                summary = client.get_game_stats_summary(args.game_pk)
                print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
            else:
                _print_game_stats(client=client, game_pk=args.game_pk, as_json=False, use_color=args.color)
            return EXIT_OK

        if args.command == "leaders":
            output_format = _resolve_output_format(args.format, args.json)
            _print_league_leaders(
                client=client,
                season=args.season,
                top=args.top,
                category=args.category,
                output_format=output_format,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "playbyplay":
            output_format = _resolve_output_format(args.format, args.json)
            _print_play_by_play(
                client=client,
                game_pk=args.game_pk,
                output_format=output_format,
                compact=args.compact,
                with_pitches=args.with_pitches,
                inning_filter=args.inning,
                team_filter=args.team,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "standings":
            output_format = _resolve_output_format(args.format, args.json)
            _print_standings(client=client, season=args.season, output_format=output_format, use_color=args.color)
            return EXIT_OK

        if args.command == "boxscore":
            output_format = _resolve_output_format(args.format, args.json)
            _print_boxscore(
                client=client,
                game_pk=args.game_pk,
                team_filter=args.team,
                output_format=output_format,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "player":
            output_format = _resolve_output_format(args.format, args.json)
            _print_player(
                client=client,
                season=args.season,
                player_id=args.id,
                player_name=args.name,
                output_format=output_format,
            )
            return EXIT_OK

        if args.command == "today":
            output_format = _resolve_output_format(args.format, args.json)
            _print_today(
                client=client,
                output_format=output_format,
                status_filter=args.status,
                team_filter=args.team,
                compact=args.compact,
                show_header=not args.no_header,
                separator=args.separator,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "next":
            output_format = _resolve_output_format(args.format, args.json)
            _print_next_games(
                client=client,
                from_date_iso=args.from_date,
                team_filter=args.team,
                count=args.count,
                output_format=output_format,
                compact=args.compact,
                show_header=not args.no_header,
                separator=args.separator,
                use_color=args.color,
            )
            return EXIT_OK

        if args.command == "tui":
            _run_tui(client=client, date_iso=args.date, interval_seconds=args.interval, team_filter=args.team)
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
            alert=args.alert,
            bell=args.bell,
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


def _detect_game_alerts(
    previous_games_by_pk: dict[int, LidomGameScore], current_games: list[LidomGameScore]
) -> list[str]:
    alerts: list[str] = []
    for current in current_games:
        previous = previous_games_by_pk.get(current.game_pk)
        if previous is None:
            alerts.append(f"Juego nuevo detectado: {current.away_team} vs {current.home_team} ({current.status})")
            continue
        if previous.away_score != current.away_score or previous.home_score != current.home_score:
            alerts.append(
                f"Cambio de marcador en {current.away_team} vs {current.home_team}: "
                f"{_score(previous.away_score)}-{_score(previous.home_score)} -> "
                f"{_score(current.away_score)}-{_score(current.home_score)}"
            )
        if previous.status != current.status:
            alerts.append(
                f"Cambio de estado en {current.away_team} vs {current.home_team}: "
                f"{previous.status} -> {current.status}"
            )
    return alerts


def _detect_atbat_alerts(previous: AtBatSnapshot, current: AtBatSnapshot) -> list[str]:
    alerts: list[str] = []
    if previous.last_event != current.last_event:
        alerts.append(f"Nuevo evento: {current.last_event}")
    if previous.balls != current.balls or previous.strikes != current.strikes or previous.outs != current.outs:
        alerts.append(
            f"Conteo actualizado: {previous.balls}-{previous.strikes}/{previous.outs} outs -> "
            f"{current.balls}-{current.strikes}/{current.outs} outs"
        )
    if previous.away_runs != current.away_runs or previous.home_runs != current.home_runs:
        alerts.append(
            f"Marcador cambió: {_score(previous.away_runs)}-{_score(previous.home_runs)} -> "
            f"{_score(current.away_runs)}-{_score(current.home_runs)}"
        )
    return alerts


def _team_label(team_name: str, use_color: bool, width: int | None = None) -> str:
    if not team_name:
        return team_name
    label = team_name.ljust(width) if width else team_name
    if not use_color:
        return label

    normalized = _normalize_text(team_name)
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
