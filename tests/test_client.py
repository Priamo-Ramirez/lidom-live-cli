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


def test_parse_current_at_bat_maps_fields() -> None:
    payload = _load_fixture("live_feed_current_play.json")
    snapshot = LidomApiClient.parse_current_at_bat(payload)

    assert snapshot.game_pk == 851509
    assert snapshot.status == "In Progress"
    assert snapshot.inning == 4
    assert snapshot.half_inning == "top"
    assert snapshot.batter == "Juan Soto"
    assert snapshot.pitcher == "Wily Peralta"
    assert snapshot.balls == 2
    assert snapshot.strikes == 1
    assert snapshot.outs == 1
    assert snapshot.last_event == "Called Strike"


def test_parse_game_stats_summary_maps_linescore_and_avg() -> None:
    payload = _load_fixture("live_feed_current_play.json")
    summary = LidomApiClient.parse_game_stats_summary(payload)

    assert summary.game_pk == 851509
    assert summary.away_team == "Aguilas Cibaenas"
    assert summary.home_team == "Gigantes del Cibao"
    assert summary.away_runs == 3
    assert summary.home_runs == 2
    assert summary.away_hits == 7
    assert summary.home_hits == 5
    assert summary.away_errors == 0
    assert summary.home_errors == 1
    assert summary.away_avg == ".278"
    assert summary.home_avg == ".262"


def test_parse_league_hitting_leaders_maps_players() -> None:
    payload = _load_fixture("league_hitting_stats.json")
    leaders = LidomApiClient.parse_league_hitting_leaders(payload)

    assert len(leaders) == 2
    assert leaders[0].rank == 1
    assert leaders[0].player_name == "Ismael Munguia"
    assert leaders[0].team_name == "Tigres del Licey"
    assert leaders[0].avg == ".368"
    assert leaders[0].at_bats == 95
    assert leaders[0].hits == 35
    assert leaders[0].ops == ".927"
