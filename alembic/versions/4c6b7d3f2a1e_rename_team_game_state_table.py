"""Rename team_game_state to football_team_game_state

Revision ID: 4c6b7d3f2a1e
Revises: 806d78e24b6f
Create Date: 2026-02-08

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c6b7d3f2a1e"
down_revision: Union[str, Sequence[str], None] = "806d78e24b6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.rename_table("team_game_state", "football_team_game_state")

    with op.batch_alter_table("football_team_game_state") as batch:
        batch.drop_constraint("uq_team_game_state_team_game", type_="unique")
        batch.create_unique_constraint(
            "uq_football_team_game_state_team_game",
            ["team_id", "game_id"],
        )

    op.drop_index("ix_team_game_state_game", table_name="football_team_game_state")
    op.drop_index("ix_team_game_state_season_week", table_name="football_team_game_state")
    op.drop_index("ix_team_game_state_team_start_time", table_name="football_team_game_state")

    op.create_index(
        "ix_football_team_game_state_game",
        "football_team_game_state",
        ["game_id"],
        unique=False,
    )
    op.create_index(
        "ix_football_team_game_state_season_week",
        "football_team_game_state",
        ["season_id", "week"],
        unique=False,
    )
    op.create_index(
        "ix_football_team_game_state_team_start_time",
        "football_team_game_state",
        ["team_id", "start_time"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("football_team_game_state") as batch:
        batch.drop_constraint("uq_football_team_game_state_team_game", type_="unique")
        batch.create_unique_constraint(
            "uq_team_game_state_team_game",
            ["team_id", "game_id"],
        )

    op.drop_index(
        "ix_football_team_game_state_team_start_time",
        table_name="football_team_game_state",
    )
    op.drop_index(
        "ix_football_team_game_state_season_week",
        table_name="football_team_game_state",
    )
    op.drop_index("ix_football_team_game_state_game", table_name="football_team_game_state")

    op.create_index(
        "ix_team_game_state_team_start_time",
        "football_team_game_state",
        ["team_id", "start_time"],
        unique=False,
    )
    op.create_index(
        "ix_team_game_state_season_week",
        "football_team_game_state",
        ["season_id", "week"],
        unique=False,
    )
    op.create_index(
        "ix_team_game_state_game",
        "football_team_game_state",
        ["game_id"],
        unique=False,
    )

    op.rename_table("football_team_game_state", "team_game_state")
