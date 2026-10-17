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


def test_parse_scores_handles_multiple_dates() -> None:
    payload = _load_fixture("schedule_scores_range.json")
    games = LidomApiClient.parse_scores(payload)

    assert len(games) == 2
    assert games[0].official_date == "2026-10-15"
    assert games[0].game_pk == 851400
    assert games[1].official_date == "2026-10-16"
    assert games[1].game_pk == 851401


def test_parse_current_at_bat_maps_fields() -> None:
    payload = _load_fixture("live_feed_current_play.json")
    snapshot = LidomApiClient.parse_current_at_bat(payload)

    assert snapshot.game_pk == 851509
    assert snapshot.status == "In Progress"
    assert snapshot.official_date == "2026-10-16"
    assert snapshot.venue == "Estadio Quisqueya Juan Marichal"
    assert snapshot.away_team == "Aguilas Cibaenas"
    assert snapshot.home_team == "Gigantes del Cibao"
    assert snapshot.away_runs == 3
    assert snapshot.home_runs == 2
    assert snapshot.inning == 4
    assert snapshot.half_inning == "top"
    assert snapshot.batting_team == "Aguilas Cibaenas"
    assert snapshot.runners == "1B, 2B"
    assert snapshot.batter == "Juan Soto"
    assert snapshot.batter_side == "Left"
    assert snapshot.pitcher == "Wily Peralta"
    assert snapshot.pitcher_hand == "Right"
    assert snapshot.balls == 2
    assert snapshot.strikes == 1
    assert snapshot.outs == 1
    assert snapshot.last_event == "Called Strike"
    assert snapshot.last_pitch_type == "Slider"
    assert snapshot.last_pitch_speed == 84.1
    assert snapshot.on_deck == "Junior Lake"
    assert snapshot.batter_today == "3-1, BB"
    assert snapshot.pitcher_today == "1.1 IP, 1 H, 0 ER, 2 K"
    assert snapshot.event_sequence == ["Ball (Fastball, 95.2 mph)", "Called Strike (Slider, 84.1 mph)"]


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


def test_parse_play_by_play_maps_entries() -> None:
    payload = _load_fixture("live_feed_play_by_play.json")
    report = LidomApiClient.parse_play_by_play(payload)

    assert report.game_pk == 826278
    assert report.status == "Final"
    assert report.away_team == "Tigres del Licey"
    assert report.home_team == "Leones del Escogido"
    assert len(report.plays) == 2

    first_play = report.plays[0]
    assert first_play.at_bat_index == 0
    assert first_play.inning == 1
    assert first_play.half_inning == "top"
    assert first_play.batting_team == "Tigres del Licey"
    assert first_play.batter == "Gustavo Nunez"
    assert first_play.pitcher == "Johnny Cueto"
    assert first_play.away_score == 0
    assert first_play.home_score == 0
    assert first_play.is_scoring_play is False
    assert first_play.pitch_count == 2
    assert first_play.pitch_sequence == ["Called Strike (Sinker, 95.1 mph)", "In play, out(s) (Sinker, 96.8 mph)"]

    second_play = report.plays[1]
    assert second_play.batting_team == "Leones del Escogido"
    assert second_play.is_scoring_play is True
    assert second_play.away_score == 0
    assert second_play.home_score == 1
    assert second_play.pitch_count == 2
