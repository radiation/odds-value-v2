from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

import odds_value.db.models  # noqa: F401
from odds_value.db.base import Base
from odds_value.db.enums import SportEnum
from odds_value.db.models.core.game import Game
from odds_value.db.models.core.league import League
from odds_value.db.models.core.season import Season
from odds_value.db.models.core.team import Team
from odds_value.db.models.core.team_alias import TeamAlias
from odds_value.db.models.odds.odds_snapshot import OddsSnapshot
from odds_value.ingestion.providers.odds_api.ingest.nfl_odds import (
    ingest_odds_api_nfl_odds_as_of_kickoff_minus_hours_for_season,
)


def _make_session() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_ingest_odds_api_nfl_as_of_kickoff_minus_6h_creates_snapshots() -> None:
    session = _make_session()

    nfl = League(league_key="NFL", name="National Football League", sport=SportEnum.FOOTBALL)
    session.add(nfl)
    session.flush()

    season = Season(league_id=nfl.id, year=2021, name="2021")
    session.add(season)
    session.flush()

    home = Team(league_id=nfl.id, provider_team_id="TB", name="Tampa Bay Buccaneers")
    away = Team(league_id=nfl.id, provider_team_id="DAL", name="Dallas Cowboys")
    session.add_all([home, away])
    session.flush()

    # Ensure normalized names match the provider payload.
    session.add_all(
        [
            TeamAlias(
                league_id=nfl.id,
                team_id=home.id,
                alias=home.name,
                alias_norm=TeamAlias.norm(home.name),
            ),
            TeamAlias(
                league_id=nfl.id,
                team_id=away.id,
                alias=away.name,
                alias_norm=TeamAlias.norm(away.name),
            ),
        ]
    )
    session.flush()

    kickoff = datetime(2021, 9, 10, 0, 20, tzinfo=UTC)
    game = Game(
        league_id=nfl.id,
        season_id=season.id,
        provider_game_id="test-1",
        start_time=kickoff,
        home_team_id=home.id,
        away_team_id=away.id,
    )
    session.add(game)
    session.commit()

    sample_path = Path(__file__).parents[1] / "odds-api-repsonse.json"
    items = json.loads(sample_path.read_text())
    assert isinstance(items, list)

    captured_at = kickoff - timedelta(hours=6)
    captured_at = captured_at.replace(minute=0, second=0, microsecond=0)

    result = ingest_odds_api_nfl_odds_as_of_kickoff_minus_hours_for_season(
        session,
        league_key="NFL",
        season_year=2021,
        as_of_hours=6,
        items_by_captured_at={captured_at: items},
        commit_every=0,
    )
    session.commit()

    assert result.games_seen == 1
    assert result.games_matched == 1
    assert result.snapshots_created > 0

    snaps = session.query(OddsSnapshot).all()
    assert len(snaps) == result.snapshots_created

    # Basic sanity: should contain spreads (with line) and moneyline (line is null).
    assert any(s.market_type.value == "SPREAD" and s.line is not None for s in snaps)
    assert any(s.market_type.value == "MONEYLINE" and s.line is None for s in snaps)
