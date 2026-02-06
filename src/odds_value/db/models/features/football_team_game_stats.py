from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base
from odds_value.db.models.features.team_game_stats import TeamGameStats


class FootballTeamGameStats(Base):
    __tablename__ = "football_team_game_stats"

    # Strict 1:1
    team_game_stats_id: Mapped[int] = mapped_column(
        ForeignKey("team_game_stats.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Initial basic stats
    yards_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turnovers: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Raw payload
    stats_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    # Relationships
    base: Mapped[TeamGameStats] = relationship(back_populates="football")
