from __future__ import annotations

from lidom_live_cli.client import LidomGameScore
from lidom_live_cli.cli import _render_table


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

    output = _render_table(games, "2026-10-16")
    assert "Aguilas Cibaenas" in output
    assert "Gigantes del Cibao" in output
    assert "In Progress" in output
