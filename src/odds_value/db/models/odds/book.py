from __future__ import annotations

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base, TimestampMixin


class Book(Base, TimestampMixin):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)

    key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    odds_snapshots: Mapped[list[OddsSnapshot]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_books_key", "key", unique=True),
        Index("ix_books_is_active", "is_active"),
    )


from odds_value.db.models.odds.odds_snapshot import OddsSnapshot  # noqa: E402
