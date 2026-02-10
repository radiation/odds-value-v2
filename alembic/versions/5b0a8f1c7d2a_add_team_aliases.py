"""Add team aliases

Revision ID: 5b0a8f1c7d2a
Revises: efc138bc0f7c
Create Date: 2026-02-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5b0a8f1c7d2a"
down_revision: Union[str, Sequence[str], None] = "efc138bc0f7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=120), nullable=False),
        sa.Column("alias_norm", sa.String(length=120), nullable=False),
        sa.Column(
            "alias_type", sa.String(length=32), server_default=sa.text("'name'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "league_id",
            "alias_norm",
            name="uq_team_aliases_league_alias_norm",
        ),
    )
    op.create_index(
        "ix_team_aliases_league_id",
        "team_aliases",
        ["league_id"],
        unique=False,
    )
    op.create_index(
        "ix_team_aliases_team_id",
        "team_aliases",
        ["team_id"],
        unique=False,
    )
    op.create_index(
        "ix_team_aliases_league_alias_norm",
        "team_aliases",
        ["league_id", "alias_norm"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_team_aliases_league_alias_norm", table_name="team_aliases")
    op.drop_index("ix_team_aliases_team_id", table_name="team_aliases")
    op.drop_index("ix_team_aliases_league_id", table_name="team_aliases")
    op.drop_table("team_aliases")
