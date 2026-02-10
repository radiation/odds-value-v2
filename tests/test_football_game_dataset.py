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
from odds_value.db.models.features.football_team_game_state import FootballTeamGameState
from odds_value.modeling.football.dataset import build_football_game_dataset


def _make_session() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_build_football_game_dataset_builds_one_row_with_targets() -> None:
    session = _make_session()

    nfl = League(league_key="NFL", name="National Football League", sport=SportEnum.FOOTBALL)
    session.add(nfl)
    session.flush()

    season = Season(league_id=nfl.id, year=2025, name="2025")
    session.add(season)
    session.flush()

    home = Team(league_id=nfl.id, provider_team_id="H", name="Home Team")
    away = Team(league_id=nfl.id, provider_team_id="A", name="Away Team")
    session.add_all([home, away])
    session.flush()

    game = Game(
        league_id=nfl.id,
        season_id=season.id,
        provider=ProviderEnum.API_SPORTS,
        provider_game_id="g1",
        start_time=datetime(2025, 9, 7, 17, 0, tzinfo=UTC),
        status=GameStatusEnum.FINAL,
        is_neutral_site=False,
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=24,
        away_score=17,
    )
    session.add(game)
    session.flush()

    # Minimal state rows; most numeric columns can be defaults.
    session.add(
        FootballTeamGameState(
            team_id=home.id,
            game_id=game.id,
            start_time=game.start_time,
            season_id=season.id,
            week=1,
            games_played=0,
            rest_days=None,
        )
    )
    session.add(
        FootballTeamGameState(
            team_id=away.id,
            game_id=game.id,
            start_time=game.start_time,
            season_id=season.id,
            week=1,
            games_played=0,
            rest_days=None,
        )
    )
    session.commit()

    rows = build_football_game_dataset(session, league_key="NFL")

    assert len(rows) == 1
    r = rows[0]

    assert r.season_year == 2025
    assert r.week == 1
    assert r.home_score == 24
    assert r.away_score == 17
    assert r.point_diff == 7
    assert r.total_points == 41
    assert r.home_win == 1

    # A couple smoke-check feature columns exist.
    assert "diff_off_pts_l3" in r.features
    assert "home_games_played" in r.features
    assert "away_games_played" in r.features
