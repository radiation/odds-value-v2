from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.models.odds.book import Book
from odds_value.db.repos.base import BaseRepository


class BookRepository(BaseRepository[Book]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Book)
