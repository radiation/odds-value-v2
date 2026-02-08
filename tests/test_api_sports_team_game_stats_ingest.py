from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

import odds_value.db.models  # noqa: F401
from odds_value.db.base import Base
from odds_value.db.enums import GameStatusEnum, ProviderEnum, SportEnum
from odds_value.db.models.core.game import Game
from odds_value.db.models.core.league import League
from odds_value.db.models.core.season import Season
from odds_value.db.models.core.team import Team
from odds_value.ingestion.providers.api_sports.ingest.american_football_team_game_stats import (
    ingest_api_sports_american_football_team_game_stats,
    ingest_api_sports_american_football_team_game_stats_for_season,
)


def _make_session() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_ingest_api_sports_team_game_stats_upserts_team_game_stats_and_football() -> None:
    session = _make_session()

    nfl = League(league_key="NFL", name="National Football League", sport=SportEnum.FOOTBALL)
    session.add(nfl)
    session.flush()

    season = Season(league_id=nfl.id, year=2025, name="2025")
    session.add(season)
    session.flush()

    home = Team(league_id=nfl.id, provider_team_id="12", name="Philadelphia Eagles")
    away = Team(league_id=nfl.id, provider_team_id="10", name="Cincinnati Bengals")
    session.add_all([home, away])
    session.flush()

    game = Game(
        league_id=nfl.id,
        season_id=season.id,
        provider=ProviderEnum.API_SPORTS,
        provider_game_id="17281",
        start_time=datetime(2025, 10, 12, 17, 0, tzinfo=UTC),
        status=GameStatusEnum.FINAL,
        is_neutral_site=False,
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=34,
        away_score=27,
    )
    session.add(game)
    session.commit()

    items = [
        {
            "team": {"id": 12, "name": "Philadelphia Eagles", "logo": "x"},
            "statistics": {
                "yards": {"total": 432},
                "turnovers": {"total": 1},
            },
        },
        {
            "team": {"id": 10, "name": "Cincinnati Bengals", "logo": "y"},
            "statistics": {
                "yards": {"total": 325},
                "turnovers": {"total": 1},
            },
        },
    ]

    result1 = ingest_api_sports_american_football_team_game_stats(
        session,
        provider_game_id="17281",
        items=items,
    )
    session.commit()

    assert result1.items_seen == 2
    assert result1.team_game_stats_created == 2
    assert result1.football_stats_created == 2

    # idempotent re-run updates
    result2 = ingest_api_sports_american_football_team_game_stats(
        session,
        provider_game_id="17281",
        items=items,
    )
    session.commit()

    assert result2.team_game_stats_created == 0
    assert result2.team_game_stats_updated == 2
    assert result2.football_stats_created == 0
    assert result2.football_stats_updated == 2


def test_ingest_api_sports_team_game_stats_for_season_uses_db_games() -> None:
    session = _make_session()

    nfl = League(league_key="NFL", name="National Football League", sport=SportEnum.FOOTBALL)
    session.add(nfl)
    session.flush()

    season = Season(league_id=nfl.id, year=2025, name="2025")
    session.add(season)
    session.flush()

    home = Team(league_id=nfl.id, provider_team_id="12", name="Philadelphia Eagles")
    away = Team(league_id=nfl.id, provider_team_id="10", name="Cincinnati Bengals")
    session.add_all([home, away])
    session.flush()

    session.add_all(
        [
            Game(
                league_id=nfl.id,
                season_id=season.id,
                provider=ProviderEnum.API_SPORTS,
                provider_game_id="20001",
                start_time=datetime(2025, 10, 1, 0, 0, tzinfo=UTC),
                status=GameStatusEnum.FINAL,
                is_neutral_site=False,
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=1,
                away_score=2,
            ),
            Game(
                league_id=nfl.id,
                season_id=season.id,
                provider=ProviderEnum.API_SPORTS,
                provider_game_id="20002",
                start_time=datetime(2025, 10, 2, 0, 0, tzinfo=UTC),
                status=GameStatusEnum.FINAL,
                is_neutral_site=False,
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=3,
                away_score=4,
            ),
        ]
    )
    session.commit()

    items_by_game = {
        "20001": [
            {
                "team": {"id": 12, "name": "Philadelphia Eagles", "logo": "x"},
                "statistics": {"yards": {"total": 111}, "turnovers": {"total": 1}},
            },
            {
                "team": {"id": 10, "name": "Cincinnati Bengals", "logo": "y"},
                "statistics": {"yards": {"total": 222}, "turnovers": {"total": 2}},
            },
        ],
        "20002": [
            {
                "team": {"id": 12, "name": "Philadelphia Eagles", "logo": "x"},
                "statistics": {"yards": {"total": 333}, "turnovers": {"total": 3}},
            },
            {
                "team": {"id": 10, "name": "Cincinnati Bengals", "logo": "y"},
                "statistics": {"yards": {"total": 444}, "turnovers": {"total": 4}},
            },
        ],
    }

    result = ingest_api_sports_american_football_team_game_stats_for_season(
        session,
        league_key="NFL",
        season_year=2025,
        items_by_provider_game_id=items_by_game,
        sleep_seconds=0.0,
        commit_every=0,
    )

    assert result.games_seen == 2
    assert result.games_processed == 2
    assert result.games_failed == 0
    assert result.items_seen == 4
    assert result.team_game_stats_created == 4
    assert result.football_stats_created == 4
