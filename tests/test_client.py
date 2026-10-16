from __future__ import annotations

import json
from pathlib import Path

from lidom_live_cli.client import LidomApiClient


def _load_fixture(name: str) -> dict:
    fixture_path = Path(__file__).parent / "fixtures" / name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_parse_scores_maps_fields() -> None:
    payload = _load_fixture("schedule_scores.json")
    games = LidomApiClient.parse_scores(payload)

    assert len(games) == 2
    assert games[0].game_pk == 851509
    assert games[0].away_team == "Aguilas Cibaenas"
    assert games[0].away_score == 3
    assert games[1].home_team == "Leones del Escogido"
    assert games[1].away_score is None
