from __future__ import annotations

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base
from odds_value.db.enums import ProviderEnum
from odds_value.db.models.core.team import Team


class ProviderTeam(Base):
    __tablename__ = "provider_teams"

    id: Mapped[int] = mapped_column(primary_key=True)

    provider: Mapped[ProviderEnum] = mapped_column(
        Enum(ProviderEnum, name="provider_enum"),
        nullable=False,
        index=True,
    )

    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider_team_id: Mapped[str] = mapped_column(String(64), nullable=False)

    provider_team_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    team: Mapped[Team] = relationship(back_populates="provider_mappings")

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_team_id",
            name="uq_provider_teams_provider_provider_team_id",
        ),
        UniqueConstraint(
            "provider",
            "team_id",
            name="uq_provider_teams_provider_team_id",
        ),
    )
