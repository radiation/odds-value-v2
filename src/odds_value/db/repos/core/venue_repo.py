from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.core.venue import Venue
from odds_value.db.repos.base import BaseRepository


class VenueRepository(BaseRepository[Venue]):
    def __init__(self, session: Session) -> None:
        super().__init__(session=session, model=Venue)
