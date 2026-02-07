from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.core.provider_league import ProviderLeague
from odds_value.db.repos.base import BaseRepository


class ProviderLeagueRepository(BaseRepository[ProviderLeague]):
    def __init__(self, session: Session) -> None:
        super().__init__(session=session, model=ProviderLeague)
