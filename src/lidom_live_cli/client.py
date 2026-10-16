"""Cliente de datos para obtener resultados de LIDOM desde MLB Stats API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import time
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
