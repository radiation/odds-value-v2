from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.core.provider_team import ProviderTeam
from odds_value.db.repos.base import BaseRepository


class ProviderTeamRepository(BaseRepository[ProviderTeam]):
    def __init__(self, session: Session) -> None:
        super().__init__(session=session, model=ProviderTeam)
