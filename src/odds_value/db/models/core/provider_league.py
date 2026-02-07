from __future__ import annotations

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base
from odds_value.db.enums import ProviderEnum
from odds_value.db.models.core.league import League


class ProviderLeague(Base):
    __tablename__ = "provider_leagues"

    id: Mapped[int] = mapped_column(primary_key=True)

    provider: Mapped[ProviderEnum] = mapped_column(
        Enum(ProviderEnum, name="provider_enum"),
        nullable=False,
        index=True,
    )

    league_id: Mapped[int] = mapped_column(
        ForeignKey("leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider_league_id: Mapped[str] = mapped_column(String(64), nullable=False)

    provider_league_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    league: Mapped[League] = relationship(back_populates="provider_mappings")

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_league_id",
            name="uq_provider_leagues_provider_provider_league_id",
        ),
        UniqueConstraint(
            "provider",
            "league_id",
            name="uq_provider_leagues_provider_league_id",
        ),
    )
