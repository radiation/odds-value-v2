from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.core.provider_sport import ProviderSport
from odds_value.db.repos.base import BaseRepository


class ProviderSportRepository(BaseRepository[ProviderSport]):
    def __init__(self, session: Session) -> None:
        super().__init__(session=session, model=ProviderSport)
