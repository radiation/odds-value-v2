from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.features.football_team_game_stats import FootballTeamGameStats
from odds_value.db.repos.base import BaseRepository


class FootballTeamGameStatsRepository(BaseRepository[FootballTeamGameStats]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, FootballTeamGameStats)
