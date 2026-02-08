from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.features.team_game_stats import TeamGameStats
from odds_value.db.repos.base import BaseRepository


class TeamGameStatsRepository(BaseRepository[TeamGameStats]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, TeamGameStats)
