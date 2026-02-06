from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base, TimestampMixin


class Season(Base, TimestampMixin):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(primary_key=True)

    league_id: Mapped[int] = mapped_column(
        ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)

    start_date: Mapped[date | None] = mapped_column(nullable=True)
    end_date: Mapped[date | None] = mapped_column(nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    league: Mapped[League] = relationship(back_populates="seasons")
    games: Mapped[list[Game]] = relationship(back_populates="season")

    __table_args__ = (
        UniqueConstraint("league_id", "year", name="uq_seasons_league_year"),
        Index("ix_seasons_league_active", "league_id", "is_active"),
    )


from odds_value.db.models.core.game import Game  # noqa: E402
from odds_value.db.models.core.league import League  # noqa: E402
