"""Adjust feature tables

Revision ID: efc138bc0f7c
Revises: 4c6b7d3f2a1e
Create Date: 2026-02-08 16:21:51.581384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'efc138bc0f7c'
down_revision: Union[str, Sequence[str], None] = '4c6b7d3f2a1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("football_team_game_state") as batch:
        batch.add_column(sa.Column("rest_days", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "games_l3",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "games_l5",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )

        batch.drop_column("avg_points_for")
        batch.drop_column("avg_points_against")
        batch.drop_column("avg_point_diff")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("football_team_game_state") as batch:
        batch.add_column(
            sa.Column(
                "avg_point_diff",
                sa.Float(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "avg_points_against",
                sa.Float(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "avg_points_for",
                sa.Float(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )

        batch.drop_column("games_l5")
        batch.drop_column("games_l3")
        batch.drop_column("rest_days")
