from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base, TimestampMixin
from odds_value.db.enums import RoofTypeEnum, SurfaceTypeEnum


class Venue(Base, TimestampMixin):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)

    league_id: Mapped[int | None] = mapped_column(
        ForeignKey("leagues.id", ondelete="SET NULL"), nullable=True
    )
    provider_venue_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)

    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)

    latitude: Mapped[Decimal | None] = mapped_column(nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)

    is_indoor: Mapped[bool | None] = mapped_column(nullable=True)
    roof_type: Mapped[RoofTypeEnum | None] = mapped_column(nullable=True)
    surface_type: Mapped[SurfaceTypeEnum | None] = mapped_column(nullable=True)
    altitude_m: Mapped[int | None] = mapped_column(nullable=True)

    league: Mapped[League | None] = relationship(back_populates="venues")
    games: Mapped[list[Game]] = relationship(back_populates="venue")

    __table_args__ = (
        UniqueConstraint("league_id", "name", "city", name="uq_venues_league_name_city"),
        Index("ix_venues_league_name", "league_id", "name"),
        Index("ix_venues_lat_lon", "latitude", "longitude"),
    )


from odds_value.db.models.core.game import Game  # noqa: E402
from odds_value.db.models.core.league import League  # noqa: E402
