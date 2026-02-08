from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

import odds_value.db.models  # noqa: F401
from odds_value.db.base import Base
from odds_value.db.enums import ProviderEnum, SportEnum
from odds_value.db.models.core.league import League
from odds_value.db.models.core.provider_league import ProviderLeague
from odds_value.db.models.core.provider_sport import ProviderSport
from odds_value.ingestion.providers.api_sports.ingest.american_football_season import (
    ingest_api_sports_american_football_season,
)


def _make_session() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_ingest_api_sports_season_upserts_games_and_teams() -> None:
    session = _make_session()

    nfl = League(league_key="NFL", name="National Football League", sport=SportEnum.FOOTBALL)
    session.add(nfl)
    session.flush()

    session.add(
        ProviderSport(
            provider=ProviderEnum.API_SPORTS,
            sport=SportEnum.FOOTBALL,
            base_url="https://example.test",
        )
    )
    session.add(
        ProviderLeague(
            provider=ProviderEnum.API_SPORTS,
            league_id=nfl.id,
            provider_league_id="1",
            provider_league_name="NFL",
        )
    )
    session.commit()

    ts = int(datetime(2025, 10, 12, 17, 0, tzinfo=UTC).timestamp())

    items = [
        {
            "game": {
                "id": 17394,
                "date": {"timestamp": ts},
                "venue": {"name": "Lucas Oil Stadium", "city": "Indianapolis"},
                "status": {"short": "FT"},
            },
            "league": {"id": 1, "name": "NFL", "season": "2025"},
            "teams": {
                "home": {"id": 21, "name": "Indianapolis Colts", "logo": "x"},
                "away": {"id": 11, "name": "Arizona Cardinals", "logo": "y"},
            },
            "scores": {"home": {"total": 31}, "away": {"total": 27}},
        }
    ]

    result1 = ingest_api_sports_american_football_season(
        session,
        league_key="NFL",
        season_year=2025,
        items=items,
    )
    session.commit()

    assert result1.games_created == 1
    assert result1.teams_created == 2

    # idempotent re-run
    result2 = ingest_api_sports_american_football_season(
        session,
        league_key="NFL",
        season_year=2025,
        items=items,
    )
    session.commit()

    assert result2.games_created == 0
    assert result2.games_updated == 1
    assert result2.teams_created == 0
