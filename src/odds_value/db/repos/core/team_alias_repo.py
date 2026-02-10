from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.core.team_alias import TeamAlias
from odds_value.db.repos.base import BaseRepository


class TeamAliasRepository(BaseRepository[TeamAlias]):
    def __init__(self, session: Session) -> None:
        super().__init__(session=session, model=TeamAlias)
