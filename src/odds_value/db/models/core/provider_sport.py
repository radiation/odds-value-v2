from __future__ import annotations

from sqlalchemy import Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from odds_value.db.base import Base
from odds_value.db.enums import ProviderEnum, SportEnum


class ProviderSport(Base):
    __tablename__ = "provider_sports"

    id: Mapped[int] = mapped_column(primary_key=True)

    provider: Mapped[ProviderEnum] = mapped_column(
        Enum(ProviderEnum, name="provider_enum"),
        nullable=False,
        index=True,
    )

    sport: Mapped[SportEnum] = mapped_column(
        Enum(SportEnum, name="sport_enum"),
        nullable=False,
        index=True,
    )

    base_url: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "sport", name="uq_provider_sports_provider_sport"),
    )
