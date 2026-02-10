from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.core.text import normalize_team_alias
from odds_value.db.base import Base, TimestampMixin


class TeamAlias(Base, TimestampMixin):
    __tablename__ = "team_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)

    league_id: Mapped[int] = mapped_column(
        ForeignKey("leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    alias: Mapped[str] = mapped_column(String(120), nullable=False)
    alias_norm: Mapped[str] = mapped_column(String(120), nullable=False)

    alias_type: Mapped[str] = mapped_column(String(32), nullable=False, default="name")

    team: Mapped[Team] = relationship("Team")

    __table_args__ = (
        UniqueConstraint("league_id", "alias_norm", name="uq_team_aliases_league_alias_norm"),
        Index("ix_team_aliases_league_alias_norm", "league_id", "alias_norm"),
    )

    @staticmethod
    def norm(value: str) -> str:
        return normalize_team_alias(value)


from odds_value.db.models.core.team import Team  # noqa: E402
