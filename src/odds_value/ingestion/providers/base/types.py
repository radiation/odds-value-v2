from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

Json = dict[str, Any]


@dataclass(frozen=True)
class IngestQuery:
    """
    Standardized request used by orchestration.
    Adapters can extend this class as needed.
    """
    league_key: str | None = None
    season_year: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    provider_game_id: str | int | None = None
    provider_hint: str | None = None


@dataclass(frozen=True)
class EntityBundle:
    """
    Provider adapters return a bundle of canonical entities.
    """
    leagues: list[Mapping[str, Any]]
    seasons: list[Mapping[str, Any]]
    teams: list[Mapping[str, Any]]
    games: list[Mapping[str, Any]]
