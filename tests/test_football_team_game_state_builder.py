from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

import odds_value.db.models  # noqa: F401
from odds_value.db.base import Base
from odds_value.db.enums import GameStatusEnum, ProviderEnum, SportEnum
from odds_value.db.models.core.game import Game
from odds_value.db.models.core.league import League
from odds_value.db.models.core.season import Season
from odds_value.db.models.core.team import Team
from odds_value.db.models.features.football_team_game_state import FootballTeamGameState
from odds_value.db.models.features.football_team_game_stats import FootballTeamGameStats
from odds_value.db.models.features.team_game_stats import TeamGameStats
from odds_value.features.football.team_game_state_builder import (
    build_football_team_game_state_for_season,
)


def _make_session() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_build_football_team_game_state_is_asof_kickoff_and_idempotent() -> None:
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

    # Week 5 bucket in 2025 (Tue Sep 30 -> Mon Oct 6)
    game1 = Game(
        league_id=nfl.id,
        season_id=season.id,
        provider=ProviderEnum.API_SPORTS,
        provider_game_id="g1",
        start_time=datetime(2025, 10, 1, 17, 0, tzinfo=UTC),
        status=GameStatusEnum.FINAL,
        is_neutral_site=False,
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=10,
        away_score=7,
    )

    # Week 6 bucket in 2025 (Tue Oct 7 -> Mon Oct 13)
    game2 = Game(
        league_id=nfl.id,
        season_id=season.id,
        provider=ProviderEnum.API_SPORTS,
        provider_game_id="g2",
        start_time=datetime(2025, 10, 8, 17, 0, tzinfo=UTC),
        status=GameStatusEnum.SCHEDULED,
        is_neutral_site=False,
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=None,
        away_score=None,
    )

    session.add_all([game1, game2])
    session.flush()

    tgs1_home = TeamGameStats(game_id=game1.id, team_id=home.id, is_home=True, score=10)
    tgs1_away = TeamGameStats(game_id=game1.id, team_id=away.id, is_home=False, score=7)
    session.add_all([tgs1_home, tgs1_away])
    session.flush()

    session.add_all(
        [
            FootballTeamGameStats(team_game_stats_id=tgs1_home.id, yards_total=350, turnovers=1),
            FootballTeamGameStats(team_game_stats_id=tgs1_away.id, yards_total=300, turnovers=2),
        ]
    )
    session.commit()

    result1 = build_football_team_game_state_for_season(session, league_key="NFL", season_year=2025)

    assert result1.games_seen == 2
    assert result1.team_games_seen == 4
    assert result1.states_created == 4

    states = list(session.execute(select(FootballTeamGameState)).scalars().all())
    assert len(states) == 4

    # For game1, both teams have no history.
    s_game1_home = session.execute(
        select(FootballTeamGameState).where(
            FootballTeamGameState.game_id == game1.id,
            FootballTeamGameState.team_id == home.id,
        )
    ).scalar_one()
    assert s_game1_home.week == 5
    assert s_game1_home.games_played == 0
    assert s_game1_home.rest_days is None

    # For game2, both teams have history from game1 only.
    s_game2_home = session.execute(
        select(FootballTeamGameState).where(
            FootballTeamGameState.game_id == game2.id,
            FootballTeamGameState.team_id == home.id,
        )
    ).scalar_one()
    assert s_game2_home.week == 6
    assert s_game2_home.games_played == 1
    assert s_game2_home.games_l3 == 1
    assert s_game2_home.games_l5 == 1
    assert s_game2_home.rest_days == 7

    assert s_game2_home.off_pts_season == 10.0
    assert s_game2_home.off_diff_season == 3.0
    assert s_game2_home.off_yards_season == 350.0
    assert s_game2_home.off_turnovers_season == 1.0

    assert s_game2_home.def_pa_season == 7.0
    assert s_game2_home.def_yards_allowed_season == 300.0
    assert s_game2_home.def_takeaways_season == 2.0

    # Idempotent second run should update existing rows.
    result2 = build_football_team_game_state_for_season(session, league_key="NFL", season_year=2025)
    assert result2.states_created == 0
    assert result2.states_updated == 4
