from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from odds_value.db.base import Base, TimestampMixin
from odds_value.db.enums import MarketTypeEnum, SideTypeEnum


class OddsSnapshot(Base, TimestampMixin):
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)

    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), nullable=False)

    captured_at: Mapped[datetime] = mapped_column(nullable=False)

    market_type: Mapped[MarketTypeEnum] = mapped_column(nullable=False)
    side_type: Mapped[SideTypeEnum] = mapped_column(nullable=False)

    # SPREAD/TOTAL => numeric value (e.g., -3.5, 44.5). MONEYLINE => NULL.
    line: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    # American odds: -110, +120, etc.
    price: Mapped[int] = mapped_column(Integer, nullable=False)

    is_closing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Keep provider as a string for now (enum later if you want it).
    provider: Mapped[str] = mapped_column(
        String, nullable=False, default="odds-api", server_default="odds-api"
    )

    game: Mapped[Game] = relationship(back_populates="odds_snapshots")
    book: Mapped[Book] = relationship(back_populates="odds_snapshots")

    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "book_id",
            "market_type",
            "side_type",
            "captured_at",
            name="uq_odds_snapshots_identity",
        ),
        Index("ix_odds_snapshots_game_captured_at", "game_id", "captured_at"),
        Index("ix_odds_snapshots_book_captured_at", "book_id", "captured_at"),
        Index(
            "ix_odds_snapshots_game_market_side_captured_at",
            "game_id",
            "market_type",
            "side_type",
            "captured_at",
        ),
        Index(
            "ix_odds_snapshots_lookup",
            "game_id",
            "book_id",
            "market_type",
            "side_type",
            "captured_at",
        ),
        Index(
            "ix_odds_snapshots_closing_by_game_market_side",
            "game_id",
            "market_type",
            "side_type",
            postgresql_where=text("is_closing = true"),
        ),
    )


from odds_value.db.models.core.game import Game  # noqa: E402
from odds_value.db.models.odds.book import Book  # noqa: E402
