from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from odds_value.db.base import Base


class IngestedPayload(Base):
    __tablename__ = "ingested_payloads"

    id: Mapped[int] = mapped_column(primary_key=True)

    provider: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "api-sports"
    entity_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "league", "team", "game", "stats"
    entity_key: Mapped[str] = mapped_column(
        String, nullable=False
    )  # provider ids or composite keys

    fetched_at: Mapped[datetime] = mapped_column(nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_ingested_payloads_lookup", "provider", "entity_type", "entity_key", "fetched_at"),
    )
