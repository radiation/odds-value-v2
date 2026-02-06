from __future__ import annotations

from enum import Enum, StrEnum


class ProviderEnum(StrEnum):
    API_SPORTS = "api_sports"
    NFLVERSE = "nflverse"
    ODDS_API = "odds_api"


class SportEnum(str, Enum):
    NFL = "NFL"
    NBA = "NBA"
    MLB = "MLB"
    NHL = "NHL"
    NCAAF = "NCAAF"
    NCAAB = "NCAAB"
    WNBA = "WNBA"
    EPL = "EPL"
    OTHER = "OTHER"


class GameStatusEnum(str, Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    FINAL = "FINAL"
    POSTPONED = "POSTPONED"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"


class RoofTypeEnum(str, Enum):
    DOME = "DOME"
    RETRACTABLE = "RETRACTABLE"
    OPEN = "OPEN"
    UNKNOWN = "UNKNOWN"


class SurfaceTypeEnum(str, Enum):
    GRASS = "GRASS"
    TURF = "TURF"
    HYBRID = "HYBRID"
    UNKNOWN = "UNKNOWN"


class MarketTypeEnum(str, Enum):
    SPREAD = "SPREAD"
    TOTAL = "TOTAL"
    MONEYLINE = "MONEYLINE"


class SideTypeEnum(str, Enum):
    # Spread / Moneyline
    HOME = "HOME"
    AWAY = "AWAY"

    # Totals
    OVER = "OVER"
    UNDER = "UNDER"
