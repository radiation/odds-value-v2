from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base, TimestampMixin


class TeamGameState(Base, TimestampMixin):
    __tablename__ = "team_game_state"

    id: Mapped[int] = mapped_column(primary_key=True)

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)

    start_time: Mapped[datetime] = mapped_column(nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)

    games_played: Mapped[int] = mapped_column(Integer, nullable=False)

    # Legacy, scheduled to be removed
    avg_points_for: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    avg_points_against: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    avg_point_diff: Mapped[float | None] = mapped_column(nullable=False, default=0.0)

    # Offensive/Defensive splits
    off_pts_l3: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    off_pts_l5: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    off_pts_season: Mapped[float | None] = mapped_column(nullable=False, default=0.0)

    off_diff_l3: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    off_diff_l5: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    off_diff_season: Mapped[float | None] = mapped_column(nullable=False, default=0.0)

    off_yards_l3: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    off_yards_l5: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    off_yards_season: Mapped[float | None] = mapped_column(nullable=False, default=0.0)

    off_turnovers_l3: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    off_turnovers_l5: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    off_turnovers_season: Mapped[float | None] = mapped_column(nullable=False, default=0.0)

    def_pa_l3: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    def_pa_l5: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    def_pa_season: Mapped[float | None] = mapped_column(nullable=False, default=0.0)

    def_diff_l3: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    def_diff_l5: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    def_diff_season: Mapped[float | None] = mapped_column(nullable=False, default=0.0)

    def_yards_allowed_l3: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    def_yards_allowed_l5: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    def_yards_allowed_season: Mapped[float | None] = mapped_column(nullable=False, default=0.0)

    def_takeaways_l3: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    def_takeaways_l5: Mapped[float | None] = mapped_column(nullable=False, default=0.0)
    def_takeaways_season: Mapped[float | None] = mapped_column(nullable=False, default=0.0)

    # Relationships
    team: Mapped[Team] = relationship("Team")
    game: Mapped[Game] = relationship("Game")
    season: Mapped[Season] = relationship("Season")

    __table_args__ = (
        UniqueConstraint("team_id", "game_id", name="uq_team_game_state_team_game"),
        Index("ix_team_game_state_team_start_time", "team_id", "start_time"),
        Index("ix_team_game_state_game", "game_id"),
        Index("ix_team_game_state_season_week", "season_id", "week"),
    )


from odds_value.db.models.core.game import Game  # noqa: E402
from odds_value.db.models.core.season import Season  # noqa: E402
from odds_value.db.models.core.team import Team  # noqa: E402
