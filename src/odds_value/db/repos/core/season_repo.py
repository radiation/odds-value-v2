from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.core.game import Season
from odds_value.db.repos.base import BaseRepository


class SeasonRepository(BaseRepository[Season]):
    def __init__(self, session: Session) -> None:
        super().__init__(session=session, model=Season)
