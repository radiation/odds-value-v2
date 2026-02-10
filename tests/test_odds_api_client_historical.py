from __future__ import annotations

from datetime import UTC, datetime

import httpx

from odds_value.ingestion.providers.base.client import BaseHttpClient
from odds_value.ingestion.providers.odds_api.client import OddsApiClient


def test_odds_api_client_parses_historical_wrapper() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v4/historical/sports/americanfootball_nfl/odds")
        data = {
            "timestamp": "2021-10-18T11:55:00Z",
            "previous_timestamp": "2021-10-18T11:45:00Z",
            "next_timestamp": "2021-10-18T12:05:00Z",
            "data": [
                {
                    "id": "evt1",
                    "sport_key": "americanfootball_nfl",
                    "commence_time": "2021-10-19T00:15:00Z",
                    "home_team": "Tennessee Titans",
                    "away_team": "Buffalo Bills",
                    "bookmakers": [],
                }
            ],
        }
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    http = BaseHttpClient(base_url="https://api.the-odds-api.com/v4", transport=transport)

    client = OddsApiClient(http=http, api_key="test")
    snap = client.get_historical_odds(
        sport_key="americanfootball_nfl",
        regions="us",
        markets=["h2h"],
        odds_format="american",
        date=datetime(2021, 10, 18, 12, 0, tzinfo=UTC),
    )

    assert snap.timestamp == datetime(2021, 10, 18, 11, 55, tzinfo=UTC)
    assert len(snap.items) == 1
    assert snap.items[0]["id"] == "evt1"
