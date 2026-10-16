"""Cliente de datos para obtener resultados de LIDOM desde MLB Stats API."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

BASE_URL = "https://statsapi.mlb.com/api/v1"
WINTER_LEAGUES_SPORT_ID = 17
LIDOM_LEAGUE_ID = 131
DOMINICAN_TZ = "America/Santo_Domingo"


@dataclass(frozen=True)
class LidomGameScore:
    """Modelo tipado para resultados de un juego."""

    game_pk: int
    official_date: str
    start_time_rd: str
    away_team: str
    home_team: str
    away_score: int | None
    home_score: int | None
    status: str


@dataclass(frozen=True)
class AtBatSnapshot:
    """Estado del turno actual en un juego en vivo."""

    game_pk: int
    status: str
    inning: int | None
    half_inning: str
    batter: str
    pitcher: str
    balls: int
    strikes: int
    outs: int
    last_event: str


@dataclass(frozen=True)
class GameStatsSummary:
    """Resumen de line score y estadísticas clave del juego."""

    game_pk: int
    status: str
    inning_state: str
    current_inning: int | None
    away_team: str
    home_team: str
    away_runs: int | None
    home_runs: int | None
    away_hits: int | None
    home_hits: int | None
    away_errors: int | None
    home_errors: int | None
    away_avg: str | None
    home_avg: str | None


@dataclass(frozen=True)
class LeagueHittingLeader:
    """Líder de bateo en la temporada de LIDOM."""

    rank: int
    player_name: str
    team_name: str
    avg: str
    at_bats: int | None
    hits: int | None
    ops: str | None


def get_today_in_dominican_republic() -> str:
    """Fecha actual en zona horaria de RD (YYYY-MM-DD)."""
    return datetime.now(ZoneInfo(DOMINICAN_TZ)).strftime("%Y-%m-%d")


def _to_rd_time(iso_utc: str) -> str:
    if not iso_utc:
        return "--:--"
    utc_dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    rd_dt = utc_dt.astimezone(ZoneInfo(DOMINICAN_TZ))
    return rd_dt.strftime("%H:%M")


class LidomApiClient:
    """Cliente mínimo con reintentos para consultar schedule de LIDOM."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout_seconds: int = 15,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(url, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                last_error = error
                should_retry = error.code in {429, 500, 502, 503, 504}
                if not should_retry or attempt >= self.max_retries:
                    raise
            except URLError as error:
                last_error = error
                if attempt >= self.max_retries:
                    raise

            time.sleep(self.backoff_seconds * (2**attempt))

        if last_error is not None:
            raise last_error
        raise RuntimeError("No se pudo completar la solicitud a MLB Stats API.")

    def get_schedule(self, date_iso: str) -> dict[str, Any]:
        return self._get_json(
            "/schedule",
            params={
                "sportId": WINTER_LEAGUES_SPORT_ID,
                "leagueId": LIDOM_LEAGUE_ID,
                "date": date_iso,
            },
        )

    def get_today_schedule(self) -> dict[str, Any]:
        return self.get_schedule(get_today_in_dominican_republic())

    def get_live_feed(self, game_pk: int) -> dict[str, Any]:
        return self._get_json(f".1/game/{game_pk}/feed/live")

    def get_current_at_bat(self, game_pk: int) -> AtBatSnapshot:
        payload = self.get_live_feed(game_pk)
        return self.parse_current_at_bat(payload)

    def get_game_stats_summary(self, game_pk: int) -> GameStatsSummary:
        payload = self.get_live_feed(game_pk)
        return self.parse_game_stats_summary(payload)

    def get_league_hitting_leaders(self, season: int, limit: int = 10) -> list[LeagueHittingLeader]:
        payload = self._get_json(
            "/stats",
            params={
                "stats": "season",
                "group": "hitting",
                "sportIds": WINTER_LEAGUES_SPORT_ID,
                "leagueIds": LIDOM_LEAGUE_ID,
                "gameType": "R",
                "season": season,
                "sortStat": "avg",
                "order": "desc",
                "limit": limit,
            },
        )
        if not isinstance(payload, dict):
            raise TypeError("Respuesta inválida desde MLB Stats API.")
        return self.parse_league_hitting_leaders(payload)

    @staticmethod
    def parse_scores(schedule_payload: dict[str, Any]) -> list[LidomGameScore]:
        dates = schedule_payload.get("dates", [])
        if not dates:
            return []

        games: list[LidomGameScore] = []
        for item in dates[0].get("games", []):
            away_info = item.get("teams", {}).get("away", {})
            home_info = item.get("teams", {}).get("home", {})
            games.append(
                LidomGameScore(
                    game_pk=item.get("gamePk", 0),
                    official_date=item.get("officialDate", ""),
                    start_time_rd=_to_rd_time(item.get("gameDate", "")),
                    away_team=away_info.get("team", {}).get("name", ""),
                    home_team=home_info.get("team", {}).get("name", ""),
                    away_score=away_info.get("score"),
                    home_score=home_info.get("score"),
                    status=item.get("status", {}).get("detailedState", ""),
                )
            )
        return games

    @staticmethod
    def parse_current_at_bat(live_feed_payload: dict[str, Any]) -> AtBatSnapshot:
        current_play = ((live_feed_payload.get("liveData") or {}).get("plays") or {}).get("currentPlay")
        if not current_play:
            raise ValueError("No hay turno activo para este juego.")

        game_data = live_feed_payload.get("gameData") or {}
        matchup = current_play.get("matchup") or {}
        count = current_play.get("count") or {}
        about = current_play.get("about") or {}
        events = current_play.get("playEvents") or []

        return AtBatSnapshot(
            game_pk=live_feed_payload.get("gamePk", 0),
            status=(game_data.get("status") or {}).get("detailedState", ""),
            inning=about.get("inning"),
            half_inning=about.get("halfInning", ""),
            batter=(matchup.get("batter") or {}).get("fullName", ""),
            pitcher=(matchup.get("pitcher") or {}).get("fullName", ""),
            balls=count.get("balls", 0),
            strikes=count.get("strikes", 0),
            outs=count.get("outs", 0),
            last_event=_last_event_description(events),
        )

    @staticmethod
    def parse_game_stats_summary(live_feed_payload: dict[str, Any]) -> GameStatsSummary:
        game_data = live_feed_payload.get("gameData") or {}
        live_data = live_feed_payload.get("liveData") or {}
        linescore = live_data.get("linescore") or {}
        line_teams = linescore.get("teams") or {}
        boxscore = (live_data.get("boxscore") or {}).get("teams") or {}
        game_teams = game_data.get("teams") or {}
        away_box = boxscore.get("away") or {}
        home_box = boxscore.get("home") or {}
        away_batting = (away_box.get("teamStats") or {}).get("batting") or {}
        home_batting = (home_box.get("teamStats") or {}).get("batting") or {}

        return GameStatsSummary(
            game_pk=live_feed_payload.get("gamePk", 0),
            status=(game_data.get("status") or {}).get("detailedState", ""),
            inning_state=linescore.get("inningState", ""),
            current_inning=linescore.get("currentInning"),
            away_team=(game_teams.get("away") or {}).get("name", ""),
            home_team=(game_teams.get("home") or {}).get("name", ""),
            away_runs=(line_teams.get("away") or {}).get("runs"),
            home_runs=(line_teams.get("home") or {}).get("runs"),
            away_hits=(line_teams.get("away") or {}).get("hits"),
            home_hits=(line_teams.get("home") or {}).get("hits"),
            away_errors=(line_teams.get("away") or {}).get("errors"),
            home_errors=(line_teams.get("home") or {}).get("errors"),
            away_avg=away_batting.get("avg"),
            home_avg=home_batting.get("avg"),
        )

    @staticmethod
    def parse_league_hitting_leaders(stats_payload: dict[str, Any]) -> list[LeagueHittingLeader]:
        stats = stats_payload.get("stats", [])
        if not stats:
            return []

        leaders: list[LeagueHittingLeader] = []
        for rank, split in enumerate(stats[0].get("splits", []), start=1):
            player_name = (split.get("player") or {}).get("fullName", "")
            if not player_name:
                continue
            stat = split.get("stat") or {}
            leaders.append(
                LeagueHittingLeader(
                    rank=rank,
                    player_name=player_name,
                    team_name=(split.get("team") or {}).get("name", ""),
                    avg=stat.get("avg", "-"),
                    at_bats=stat.get("atBats"),
                    hits=stat.get("hits"),
                    ops=stat.get("ops"),
                )
            )
        return leaders


def _last_event_description(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        description = (event.get("details") or {}).get("description")
        if description:
            return str(description)
    return "Sin eventos registrados"
