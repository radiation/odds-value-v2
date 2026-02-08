from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def parse_api_sports_game_datetime(value: Any, *, provider_game_id: str) -> datetime:
    """
    Parse api-sports 'game.date' field into tz-aware UTC datetime.

    Supports:
      - ISO string: "2025-09-07T20:20:00Z" / "+00:00"
      - Dict:
        {"timezone":"UTC","date":"YYYY-MM-DD","time":"HH:MM","timestamp": 123}
    """
    if isinstance(value, dict):
        ts = value.get("timestamp")
        if isinstance(ts, int):
            return datetime.fromtimestamp(ts, tz=UTC)

        date_part = value.get("date")
        time_part = value.get("time") or "00:00"
        if not isinstance(date_part, str) or not isinstance(time_part, str):
            raise ValueError(
                f"Missing/invalid game.date dict for provider_game_id={provider_game_id}: {value!r}"
            )

        # Treat as UTC; timestamp is preferred when present.
        return datetime.fromisoformat(f"{date_part}T{time_part}:00+00:00")

    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    raise ValueError(
        f"Missing/invalid game.date for provider_game_id={provider_game_id}: {value!r}"
    )


def parse_odds_api_datetime(value: Any) -> datetime | None:
    """
    Best-effort parser for Odds API timestamps.

    Uses parse_api_sports_game_datetime when possible,
    but returns None instead of raising on bad input.
    """
    if value in (None, ""):
        return None

    try:
        return parse_api_sports_game_datetime(value, provider_game_id="odds-api")
    except Exception:
        return None
