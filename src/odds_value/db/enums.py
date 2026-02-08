from __future__ import annotations

from enum import StrEnum


class ProviderEnum(StrEnum):
    API_SPORTS = "api_sports"
    NFLVERSE = "nflverse"
    ODDS_API = "odds_api"


class SportEnum(StrEnum):
    BASEBALL = "BASEBALL"
    BASKETBALL = "BASKETBALL"
    FOOTBALL = "FOOTBALL"
    HOCKEY = "HOCKEY"
    SOCCER = "SOCCER"


class GameStatusEnum(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    FINAL = "FINAL"
    POSTPONED = "POSTPONED"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"


class RoofTypeEnum(StrEnum):
    DOME = "DOME"
    RETRACTABLE = "RETRACTABLE"
    OPEN = "OPEN"
    UNKNOWN = "UNKNOWN"


class SurfaceTypeEnum(StrEnum):
    GRASS = "GRASS"
    TURF = "TURF"
    HYBRID = "HYBRID"
    UNKNOWN = "UNKNOWN"


class MarketTypeEnum(StrEnum):
    SPREAD = "SPREAD"
    TOTAL = "TOTAL"
    MONEYLINE = "MONEYLINE"


class SideTypeEnum(StrEnum):
    # Spread / Moneyline
    HOME = "HOME"
    AWAY = "AWAY"

    # Totals
    OVER = "OVER"
    UNDER = "UNDER"
