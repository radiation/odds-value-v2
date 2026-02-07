from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.core.league import League
from odds_value.db.repos.base import BaseRepository


class LeagueRepository(BaseRepository[League]):
    def __init__(self, session: Session) -> None:
        super().__init__(session=session, model=League)
