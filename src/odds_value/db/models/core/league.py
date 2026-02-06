from __future__ import annotations

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base, TimestampMixin
from odds_value.db.enums import SportEnum


class League(Base, TimestampMixin):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_league_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    sport: Mapped[SportEnum] = mapped_column(nullable=False)

    country: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    seasons: Mapped[list[Season]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )
    teams: Mapped[list[Team]] = relationship(back_populates="league", cascade="all, delete-orphan")
    venues: Mapped[list[Venue]] = relationship(back_populates="league")
    games: Mapped[list[Game]] = relationship(back_populates="league")

    __table_args__ = (Index("ix_leagues_sport_active", "sport", "is_active"),)


from odds_value.db.models.core.game import Game  # noqa: E402
from odds_value.db.models.core.season import Season  # noqa: E402
from odds_value.db.models.core.team import Team  # noqa: E402
from odds_value.db.models.core.venue import Venue  # noqa: E402
