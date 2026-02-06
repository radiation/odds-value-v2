from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from odds_value.db.models.core.game import Game
    from odds_value.db.models.core.team import Team
    from odds_value.db.models.features.baseball_team_game_stats import BaseballTeamGameStats
    from odds_value.db.models.features.football_team_game_stats import FootballTeamGameStats


class TeamGameStats(Base, TimestampMixin):
    __tablename__ = "team_game_stats"

    id: Mapped[int] = mapped_column(primary_key=True)

    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)

    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    game: Mapped[Game] = relationship(back_populates="team_stats")
    team: Mapped[Team] = relationship(back_populates="team_game_stats")

    football: Mapped[FootballTeamGameStats | None] = relationship(
        back_populates="base",
        uselist=False,
        cascade="all, delete-orphan",
    )
    baseball: Mapped[BaseballTeamGameStats | None] = relationship(
        back_populates="base",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("game_id", "team_id", name="uq_team_game_stats_game_team"),
        Index("ix_tgs_game_id", "game_id"),
        Index("ix_tgs_team_id", "team_id"),
    )
