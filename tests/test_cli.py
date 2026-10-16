from __future__ import annotations

from lidom_live_cli.cli import (
    _filter_games,
    _parse_csv_values,
    _render_at_bat,
    _render_game_stats,
    _render_league_leaders,
    _render_table,
)
from lidom_live_cli.client import (
    AtBatSnapshot,
    GameStatsSummary,
    LeagueHittingLeader,
    LidomGameScore,
)


def test_render_table_contains_key_fields() -> None:
    games = [
        LidomGameScore(
            game_pk=851509,
            official_date="2026-10-16",
            start_time_rd="19:00",
            away_team="Aguilas Cibaenas",
            home_team="Gigantes del Cibao",
            away_score=3,
            home_score=2,
            status="In Progress",
        )
    ]

    output = _render_table(
        games=games,
        date_iso="2026-10-16",
        compact=False,
        show_header=True,
        separator=" | ",
    )
    assert "Aguilas Cibaenas" in output
    assert "Gigantes del Cibao" in output
    assert "In Progress" in output


def test_render_table_compact_no_header() -> None:
    games = [
        LidomGameScore(
            game_pk=851509,
            official_date="2026-10-16",
            start_time_rd="19:00",
            away_team="Aguilas Cibaenas",
            home_team="Gigantes del Cibao",
            away_score=3,
            home_score=2,
            status="In Progress",
        )
    ]

    output = _render_table(
        games=games,
        date_iso="2026-10-16",
        compact=True,
        show_header=False,
        separator=" / ",
    )
    assert "LIDOM | Fecha:" not in output
    assert "Aguilas Cibaenas 3-2 Gigantes del Cibao / In Progress / 19:00" in output


def test_filter_games_by_status_and_team() -> None:
    games = [
        LidomGameScore(
            game_pk=1,
            official_date="2026-10-16",
            start_time_rd="19:00",
            away_team="Aguilas Cibaenas",
            home_team="Gigantes del Cibao",
            away_score=1,
            home_score=0,
            status="In Progress",
        ),
        LidomGameScore(
            game_pk=2,
            official_date="2026-10-16",
            start_time_rd="19:15",
            away_team="Tigres del Licey",
            home_team="Leones del Escogido",
            away_score=None,
            home_score=None,
            status="Scheduled",
        ),
    ]

    statuses = _parse_csv_values("in progress,final")
    filtered = _filter_games(games, statuses, "aguilas")

    assert len(filtered) == 1
    assert filtered[0].game_pk == 1


def test_render_at_bat_contains_core_fields() -> None:
    output = _render_at_bat(
        AtBatSnapshot(
            game_pk=851509,
            status="In Progress",
            inning=4,
            half_inning="top",
            batter="Juan Soto",
            pitcher="Wily Peralta",
            balls=2,
            strikes=1,
            outs=1,
            last_event="Called Strike",
        )
    )

    assert "Juego 851509" in output
    assert "Bateador: Juan Soto" in output
    assert "Pitcher: Wily Peralta" in output
    assert "Conteo: 2-1 | Outs: 1" in output


def test_render_game_stats_contains_line_score_and_avg() -> None:
    output = _render_game_stats(
        GameStatsSummary(
            game_pk=851509,
            status="In Progress",
            inning_state="Top",
            current_inning=4,
            away_team="Aguilas Cibaenas",
            home_team="Gigantes del Cibao",
            away_runs=3,
            home_runs=2,
            away_hits=7,
            home_hits=5,
            away_errors=0,
            home_errors=1,
            away_avg=".278",
            home_avg=".262",
        )
    )

    assert "Aguilas Cibaenas vs Gigantes del Cibao" in output
    assert "Inning: Top 4" in output
    assert ".278" in output
    assert ".262" in output


def test_render_league_leaders_contains_ranking() -> None:
    output = _render_league_leaders(
        [
            LeagueHittingLeader(
                rank=1,
                player_name="Ismael Munguia",
                team_name="Tigres del Licey",
                avg=".368",
                at_bats=95,
                hits=35,
                ops=".927",
            )
        ],
        season=2025,
    )

    assert "Temporada 2025" in output
    assert "Ismael Munguia" in output
    assert "Tigres del Licey" in output
    assert ".368" in output
