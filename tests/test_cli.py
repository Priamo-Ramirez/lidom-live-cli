from __future__ import annotations

from datetime import date

from lidom_live_cli.cli import (
    _detect_atbat_alerts,
    _detect_game_alerts,
    _filter_games,
    _filter_play_by_play,
    _normalize_text,
    _parse_csv_values,
    _parse_iso_date,
    _render_at_bat,
    _render_game_stats,
    _render_history_table,
    _render_league_leaders,
    _render_play_by_play,
    _render_schedule_table,
    _render_table,
    _resolve_output_format,
    _resolve_period_dates,
    _resolve_schedule_dates,
    _watch_at_bat,
)
from lidom_live_cli.client import (
    AtBatSnapshot,
    GameStatsSummary,
    LeagueHittingLeader,
    LidomGameScore,
    PlayByPlayEntry,
    PlayByPlayReport,
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
        use_color=False,
    )
    assert "Aguilas Cibaenas" in output
    assert "Gigantes del Cibao" in output
    assert "In Progress" in output
    assert "851509" in output


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
        use_color=False,
    )
    assert "LIDOM | Fecha:" not in output
    assert "851509 / Aguilas Cibaenas 3-2 Gigantes del Cibao / In Progress / 19:00" in output


def test_render_table_compact_scheduled_uses_vs() -> None:
    games = [
        LidomGameScore(
            game_pk=851491,
            official_date="2026-10-16",
            start_time_rd="19:15",
            away_team="Tigres del Licey",
            home_team="Leones del Escogido",
            away_score=None,
            home_score=None,
            status="Scheduled",
        )
    ]

    output = _render_table(
        games=games,
        date_iso="2026-10-16",
        compact=True,
        show_header=False,
        separator=" / ",
        use_color=False,
    )
    assert "Tigres del Licey vs Leones del Escogido" in output


def test_render_history_table_compact_no_header() -> None:
    games = [
        LidomGameScore(
            game_pk=851400,
            official_date="2026-10-15",
            start_time_rd="19:00",
            away_team="Tigres del Licey",
            home_team="Leones del Escogido",
            away_score=5,
            home_score=3,
            status="Final",
        ),
        LidomGameScore(
            game_pk=851401,
            official_date="2026-10-16",
            start_time_rd="19:15",
            away_team="Aguilas Cibaenas",
            home_team="Gigantes del Cibao",
            away_score=2,
            home_score=1,
            status="Final",
        ),
    ]

    output = _render_history_table(
        games=games,
        start_date_iso="2026-10-15",
        end_date_iso="2026-10-16",
        compact=True,
        show_header=False,
        separator=" / ",
        use_color=False,
    )
    assert "LIDOM | Rango:" not in output
    assert "2026-10-15 / 851400 / Tigres del Licey 5-3 Leones del Escogido / Final / 19:00" in output
    assert "2026-10-16 / 851401 / Aguilas Cibaenas 2-1 Gigantes del Cibao / Final / 19:15" in output


def test_render_schedule_table_compact_no_header() -> None:
    games = [
        LidomGameScore(
            game_pk=851490,
            official_date="2026-10-17",
            start_time_rd="19:00",
            away_team="Tigres del Licey",
            home_team="Leones del Escogido",
            away_score=None,
            home_score=None,
            status="Scheduled",
        )
    ]

    output = _render_schedule_table(
        games=games,
        start_date_iso="2026-10-17",
        end_date_iso="2026-10-17",
        compact=True,
        show_header=False,
        separator=" / ",
        use_color=False,
    )
    assert "Schedule programado" not in output
    assert "2026-10-17 / 851490 / Tigres del Licey vs Leones del Escogido / Scheduled / 19:00" in output


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
            official_date="2026-10-16",
            venue="Estadio Quisqueya Juan Marichal",
            away_team="Tigres del Licey",
            home_team="Leones del Escogido",
            away_runs=3,
            home_runs=2,
            inning=4,
            half_inning="top",
            batting_team="Tigres del Licey",
            runners="1B, 2B",
            batter="Juan Soto",
            batter_side="Left",
            pitcher="Wily Peralta",
            pitcher_hand="Right",
            balls=2,
            strikes=1,
            outs=1,
            last_event="Called Strike",
            last_pitch_type="Slider",
            last_pitch_speed=84.1,
            on_deck="Junior Lake",
            batter_today="3-1, BB",
            pitcher_today="1.1 IP, 1 H, 0 ER, 2 K",
            event_sequence=["Ball (Fastball, 95.2 mph)", "Called Strike (Slider, 84.1 mph)"],
        ),
        compact=False,
        use_color=False,
    )

    assert "Juego: Tigres del Licey vs Leones del Escogido" in output
    assert "Marcador: Tigres del Licey 3 - 2 Leones del Escogido" in output
    assert "Inning: Alta 4 | Outs: 1 | Corredores: 1B, 2B" in output
    assert "- Bateador: Juan Soto (L)" in output
    assert "- Pitcher: Wily Peralta (R)" in output
    assert "- Conteo: 2-1" in output
    assert "2) Called Strike (Slider, 84.1 mph)" in output
    assert "- Próximo bateador: Junior Lake" in output


def test_render_at_bat_compact_mode() -> None:
    output = _render_at_bat(
        AtBatSnapshot(
            game_pk=851509,
            status="In Progress",
            official_date="2026-10-16",
            venue="Estadio Quisqueya Juan Marichal",
            away_team="Tigres del Licey",
            home_team="Leones del Escogido",
            away_runs=3,
            home_runs=2,
            inning=7,
            half_inning="bottom",
            batting_team="Leones del Escogido",
            runners="Bases vacías",
            batter="Emilio Bonifacio",
            batter_side="Switch",
            pitcher="Rafael Montero",
            pitcher_hand="Right",
            balls=2,
            strikes=2,
            outs=1,
            last_event="Foul",
            last_pitch_type="Slider",
            last_pitch_speed=84.0,
            on_deck="Junior Lake",
            batter_today="1-3, BB",
            pitcher_today="1.0 IP, 0 ER",
            event_sequence=["Ball", "Called Strike", "Foul"],
        ),
        compact=True,
        use_color=False,
    )

    assert "Tigres del Licey 3-2 Leones del Escogido" in output
    assert "Baja 7" in output
    assert "Emilio Bonifacio (S) vs Rafael Montero (R)" in output
    assert "Conteo 2-2" in output


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
        ),
        use_color=False,
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


def test_watch_at_bat_rejects_non_positive_interval() -> None:
    class DummyClient:
        pass

    try:
        _watch_at_bat(  # type: ignore[arg-type]
            client=DummyClient(),
            game_pk=1,
            as_json=False,
            compact=False,
            use_color=False,
            interval_seconds=0,
            iterations=1,
            clear_screen=False,
            alert=False,
            bell=False,
        )
    except ValueError as error:
        assert "--interval" in str(error)
    else:
        raise AssertionError("Se esperaba ValueError para interval_seconds=0")


def test_watch_at_bat_rejects_negative_iterations() -> None:
    class DummyClient:
        pass

    try:
        _watch_at_bat(  # type: ignore[arg-type]
            client=DummyClient(),
            game_pk=1,
            as_json=False,
            compact=False,
            use_color=False,
            interval_seconds=1,
            iterations=-1,
            clear_screen=False,
            alert=False,
            bell=False,
        )
    except ValueError as error:
        assert "--iterations" in str(error)
    else:
        raise AssertionError("Se esperaba ValueError para iterations=-1")


def test_render_play_by_play_contains_core_fields() -> None:
    report = PlayByPlayReport(
        game_pk=826278,
        status="Final",
        official_date="2025-12-05",
        venue="Estadio Quisqueya Juan Marichal",
        away_team="Tigres del Licey",
        home_team="Leones del Escogido",
        plays=[
            PlayByPlayEntry(
                at_bat_index=0,
                inning=1,
                half_inning="top",
                batting_team="Tigres del Licey",
                batter="Gustavo Nunez",
                pitcher="Johnny Cueto",
                result="Gustavo Nunez grounds out.",
                outs=1,
                away_score=0,
                home_score=0,
                is_scoring_play=False,
                pitch_count=2,
                pitch_sequence=["Called Strike (Sinker, 95.1 mph)", "In play, out(s) (Sinker, 96.8 mph)"],
            ),
            PlayByPlayEntry(
                at_bat_index=1,
                inning=1,
                half_inning="bottom",
                batting_team="Leones del Escogido",
                batter="Junior Lake",
                pitcher="Anderson Severino",
                result="Junior Lake singles, one run scores.",
                outs=2,
                away_score=0,
                home_score=1,
                is_scoring_play=True,
                pitch_count=2,
                pitch_sequence=["Ball (Changeup, 86.4 mph)", "In play, run(s) (Fastball, 94.7 mph)"],
            ),
        ],
    )

    output = _render_play_by_play(
        report,
        plays=report.plays,
        compact=False,
        with_pitches=True,
        use_color=False,
    )
    assert "Play-by-play | Juego 826278" in output
    assert "Gustavo Nunez vs Johnny Cueto" in output
    assert "Junior Lake singles, one run scores. [SCORING]" in output
    assert "1. Ball (Changeup, 86.4 mph)" in output

    compact_output = _render_play_by_play(
        report,
        plays=report.plays,
        compact=True,
        with_pitches=True,
        use_color=False,
    )
    assert "Picheos: Called Strike (Sinker, 95.1 mph); In play, out(s) (Sinker, 96.8 mph)" in compact_output


def test_render_table_colors_team_names() -> None:
    games = [
        LidomGameScore(
            game_pk=1,
            official_date="2026-10-16",
            start_time_rd="19:00",
            away_team="Tigres del Licey",
            home_team="Leones del Escogido",
            away_score=None,
            home_score=None,
            status="Scheduled",
        )
    ]

    output = _render_table(
        games=games,
        date_iso="2026-10-16",
        compact=True,
        show_header=False,
        separator=" | ",
        use_color=True,
    )
    assert "\033[94mTigres del Licey\033[0m" in output
    assert "\033[91mLeones del Escogido\033[0m" in output


def test_filter_play_by_play_supports_inning_and_team() -> None:
    plays = [
        PlayByPlayEntry(
            at_bat_index=0,
            inning=1,
            half_inning="top",
            batting_team="Tigres del Licey",
            batter="Gustavo Nunez",
            pitcher="Johnny Cueto",
            result="Out",
            outs=1,
            away_score=0,
            home_score=0,
            is_scoring_play=False,
            pitch_count=1,
            pitch_sequence=[],
        ),
        PlayByPlayEntry(
            at_bat_index=1,
            inning=2,
            half_inning="bottom",
            batting_team="Leones del Escogido",
            batter="Junior Lake",
            pitcher="Anderson Severino",
            result="Single",
            outs=0,
            away_score=0,
            home_score=1,
            is_scoring_play=True,
            pitch_count=2,
            pitch_sequence=[],
        ),
    ]

    by_inning = _filter_play_by_play(plays, inning=2, team_query=None)
    assert len(by_inning) == 1
    assert by_inning[0].at_bat_index == 1

    by_team = _filter_play_by_play(plays, inning=None, team_query="licey")
    assert len(by_team) == 1
    assert by_team[0].at_bat_index == 0


def test_resolve_period_dates() -> None:
    base_day = date(2026, 10, 17)
    assert _resolve_period_dates("yesterday", today=base_day) == (date(2026, 10, 16), date(2026, 10, 16))
    assert _resolve_period_dates("last-week", today=base_day) == (date(2026, 10, 10), date(2026, 10, 16))
    assert _resolve_period_dates("last-month", today=base_day) == (date(2026, 9, 17), date(2026, 10, 16))


def test_resolve_schedule_dates() -> None:
    anchor = date(2026, 10, 17)
    assert _resolve_schedule_dates("day", anchor_date=anchor) == (date(2026, 10, 17), date(2026, 10, 17))
    assert _resolve_schedule_dates("week", anchor_date=anchor) == (date(2026, 10, 17), date(2026, 10, 23))
    assert _resolve_schedule_dates("month", anchor_date=anchor) == (date(2026, 10, 17), date(2026, 11, 15))


def test_parse_iso_date_valid_and_invalid() -> None:
    assert _parse_iso_date("2026-10-17") == date(2026, 10, 17)
    try:
        _parse_iso_date("17-10-2026")
    except ValueError as error:
        assert "YYYY-MM-DD" in str(error)
    else:
        raise AssertionError("Se esperaba ValueError para formato de fecha inválido")


def test_resolve_output_format_json_flag() -> None:
    assert _resolve_output_format("text", json_flag=True) == "json"
    assert _resolve_output_format("csv", json_flag=False) == "csv"


def test_normalize_text_removes_accents() -> None:
    assert _normalize_text("Aguilás Cibaeñas") == "aguilas cibaenas"


def test_detect_game_alerts_and_atbat_alerts() -> None:
    previous = {
        1: LidomGameScore(
            game_pk=1,
            official_date="2026-10-16",
            start_time_rd="19:00",
            away_team="Tigres del Licey",
            home_team="Leones del Escogido",
            away_score=1,
            home_score=1,
            status="In Progress",
        )
    }
    current = [
        LidomGameScore(
            game_pk=1,
            official_date="2026-10-16",
            start_time_rd="19:00",
            away_team="Tigres del Licey",
            home_team="Leones del Escogido",
            away_score=2,
            home_score=1,
            status="Final",
        )
    ]
    game_alerts = _detect_game_alerts(previous, current)
    assert any("Cambio de marcador" in alert for alert in game_alerts)
    assert any("Cambio de estado" in alert for alert in game_alerts)

    previous_atbat = AtBatSnapshot(
        game_pk=1,
        status="In Progress",
        official_date="2026-10-16",
        venue="Estadio",
        away_team="Tigres del Licey",
        home_team="Leones del Escogido",
        away_runs=1,
        home_runs=1,
        inning=7,
        half_inning="bottom",
        batting_team="Leones del Escogido",
        runners="Bases vacías",
        batter="Jugador A",
        batter_side="Right",
        pitcher="Jugador B",
        pitcher_hand="Right",
        balls=1,
        strikes=1,
        outs=1,
        last_event="Ball",
        last_pitch_type="Fastball",
        last_pitch_speed=95.0,
        on_deck="Jugador C",
        batter_today="1-2",
        pitcher_today="1.0 IP",
        event_sequence=[],
    )
    current_atbat = AtBatSnapshot(
        game_pk=1,
        status="In Progress",
        official_date="2026-10-16",
        venue="Estadio",
        away_team="Tigres del Licey",
        home_team="Leones del Escogido",
        away_runs=2,
        home_runs=1,
        inning=7,
        half_inning="bottom",
        batting_team="Leones del Escogido",
        runners="Bases vacías",
        batter="Jugador A",
        batter_side="Right",
        pitcher="Jugador B",
        pitcher_hand="Right",
        balls=1,
        strikes=2,
        outs=1,
        last_event="Swinging Strike",
        last_pitch_type="Slider",
        last_pitch_speed=84.0,
        on_deck="Jugador C",
        batter_today="1-2",
        pitcher_today="1.0 IP",
        event_sequence=[],
    )
    atbat_alerts = _detect_atbat_alerts(previous_atbat, current_atbat)
    assert any("Nuevo evento" in alert for alert in atbat_alerts)
    assert any("Conteo actualizado" in alert for alert in atbat_alerts)
