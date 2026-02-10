from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.odds.odds_snapshot import OddsSnapshot
from odds_value.db.repos.base import BaseRepository


class OddsSnapshotRepository(BaseRepository[OddsSnapshot]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, OddsSnapshot)
