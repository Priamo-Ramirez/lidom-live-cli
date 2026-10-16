from __future__ import annotations

from lidom_live_cli.cli import _filter_games, _parse_csv_values, _render_table
from lidom_live_cli.client import LidomGameScore


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
