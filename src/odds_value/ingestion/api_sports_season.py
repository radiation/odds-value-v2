"""Deprecated compatibility shim.

The API-Sports season ingestion logic is provider-specific and sport-specific.
The implementation now lives under the API-Sports provider package:
`odds_value.ingestion.providers.api_sports.ingest.american_football_season`.
"""

from typing import Any

from sqlalchemy.orm import Session

from odds_value.ingestion.providers.api_sports.ingest.american_football_season import (
    IngestAmericanFootballSeasonResult as IngestSeasonResult,
)
from odds_value.ingestion.providers.api_sports.ingest.american_football_season import (
    ingest_api_sports_american_football_season,
)


def ingest_api_sports_season(
    session: Session,
    *,
    league_key: str,
    season_year: int,
    items: list[dict[str, Any]] | None = None,
) -> IngestSeasonResult:
    return ingest_api_sports_american_football_season(
        session,
        league_key=league_key,
        season_year=season_year,
        items=items,
    )
