from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from odds_value.core.config import settings
from odds_value.ingestion.providers.base.client import BaseHttpClient
from odds_value.ingestion.providers.base.errors import ProviderRequestError

ApiItem = dict[str, Any]


def _iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _parse_optional_iso_z(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


@dataclass(frozen=True)
class HistoricalOddsSnapshot:
    timestamp: datetime
    previous_timestamp: datetime | None
    next_timestamp: datetime | None
    items: list[ApiItem]


class OddsApiClient:
    def __init__(self, *, http: BaseHttpClient, api_key: str | None = None) -> None:
        self.http = http
        self.api_key = api_key or settings.require_odds_api_key()

    def get_odds(
        self,
        *,
        sport_key: str,
        regions: str,
        markets: Sequence[str],
        odds_format: str = "american",
        bookmakers: Sequence[str] | None = None,
    ) -> list[ApiItem]:
        """Current odds for upcoming/live events."""

        params: dict[str, str] = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": ",".join(markets),
            "oddsFormat": odds_format,
        }
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers)

        value = self.http.get_json_value(f"/sports/{sport_key}/odds", params=params)
        if not isinstance(value, list):
            raise ProviderRequestError(f"Expected list response, got {type(value)}")

        items: list[ApiItem] = []
        for v in value:
            if isinstance(v, dict):
                items.append(v)
        return items

    def get_historical_odds(
        self,
        *,
        sport_key: str,
        regions: str,
        markets: Sequence[str],
        date: datetime,
        odds_format: str = "american",
        bookmakers: Sequence[str] | None = None,
    ) -> HistoricalOddsSnapshot:
        """Historical odds snapshot.

        Endpoint: GET /v4/historical/sports/{sport}/odds?date=...
        Response: wrapper object containing `timestamp`, `previous_timestamp`, `next_timestamp`, and `data`.
        """

        params: dict[str, str] = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": ",".join(markets),
            "oddsFormat": odds_format,
            "date": _iso_z(date),
        }
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers)

        payload = self.http.get_json(f"/historical/sports/{sport_key}/odds", params=params)

        ts = _parse_optional_iso_z(payload.get("timestamp"))
        if ts is None:
            raise ProviderRequestError("Historical odds response missing/invalid timestamp")

        prev_ts = _parse_optional_iso_z(payload.get("previous_timestamp"))
        next_ts = _parse_optional_iso_z(payload.get("next_timestamp"))

        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderRequestError("Historical odds response missing/invalid data list")

        items: list[ApiItem] = []
        for v in data:
            if isinstance(v, dict):
                items.append(v)

        return HistoricalOddsSnapshot(
            timestamp=ts,
            previous_timestamp=prev_ts,
            next_timestamp=next_ts,
            items=items,
        )
