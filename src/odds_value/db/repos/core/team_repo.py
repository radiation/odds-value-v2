from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_value.db.models.core.team import Team
from odds_value.db.repos.base import BaseRepository


class TeamRepository(BaseRepository[Team]):
    def __init__(self, session: Session) -> None:
        super().__init__(session=session, model=Team)
