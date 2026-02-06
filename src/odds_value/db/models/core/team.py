from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base, TimestampMixin


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)

    league_id: Mapped[int] = mapped_column(
        ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    provider_team_id: Mapped[str] = mapped_column(String, nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    abbreviation: Mapped[str | None] = mapped_column(String, nullable=True)
    market: Mapped[str | None] = mapped_column(String, nullable=True)
    nickname: Mapped[str | None] = mapped_column(String, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    league: Mapped[League] = relationship(back_populates="teams")

    home_games: Mapped[list[Game]] = relationship(
        back_populates="home_team",
        foreign_keys="Game.home_team_id",
    )
    away_games: Mapped[list[Game]] = relationship(
        back_populates="away_team",
        foreign_keys="Game.away_team_id",
    )

    team_game_stats: Mapped[list[TeamGameStats]] = relationship(back_populates="team")

    __table_args__ = (
        UniqueConstraint("league_id", "provider_team_id", name="uq_teams_league_provider_team_id"),
        Index("ix_teams_league_active", "league_id", "is_active"),
        Index("ix_teams_abbreviation", "abbreviation"),
    )


from odds_value.db.models.core.game import Game  # noqa: E402
from odds_value.db.models.core.league import League  # noqa: E402
from odds_value.db.models.features.team_game_stats import TeamGameStats  # noqa: E402
