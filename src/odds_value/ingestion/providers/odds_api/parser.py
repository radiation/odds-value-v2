from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from odds_value.core.text import normalize_team_alias
from odds_value.db.enums import MarketTypeEnum, SideTypeEnum

ApiItem = dict[str, Any]


def parse_iso_z(value: str) -> datetime:
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def norm_team_name(name: str) -> str:
    return normalize_team_alias(name)


@dataclass(frozen=True)
class ParsedSnapshot:
    book_key: str
    book_name: str
    market_type: MarketTypeEnum
    side_type: SideTypeEnum
    line: float | None
    price: int


def parse_event_bookmaker_snapshots(
    event_item: ApiItem,
    *,
    expected_home_norms: set[str],
    expected_away_norms: set[str],
) -> list[ParsedSnapshot]:
    """Parse one Odds API event item into book/market snapshots.

    Validates home/away team names using provided normalized alias sets.

    Supports markets:
    - h2h => MONEYLINE (HOME/AWAY)
    - spreads => SPREAD (HOME/AWAY)
    - totals => TOTAL (OVER/UNDER)
    """

    home_team = event_item.get("home_team")
    away_team = event_item.get("away_team")
    if not isinstance(home_team, str) or not isinstance(away_team, str):
        return []

    home_norm = norm_team_name(home_team)
    away_norm = norm_team_name(away_team)

    if home_norm not in expected_home_norms or away_norm not in expected_away_norms:
        return []

    bookmakers = event_item.get("bookmakers")
    if not isinstance(bookmakers, list):
        return []

    parsed: list[ParsedSnapshot] = []

    for book in bookmakers:
        if not isinstance(book, dict):
            continue

        book_key = book.get("key")
        book_title = book.get("title")
        if not isinstance(book_key, str) or not isinstance(book_title, str):
            continue

        markets = book.get("markets")
        if not isinstance(markets, list):
            continue

        for market in markets:
            if not isinstance(market, dict):
                continue
            market_key = market.get("key")
            if not isinstance(market_key, str):
                continue

            outcomes = market.get("outcomes")
            if not isinstance(outcomes, list):
                continue

            if market_key == "h2h":
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        continue
                    name = outcome.get("name")
                    price = outcome.get("price")
                    if not isinstance(name, str) or not isinstance(price, int):
                        continue

                    side_type: SideTypeEnum | None
                    if norm_team_name(name) in expected_home_norms:
                        side_type = SideTypeEnum.HOME
                    elif norm_team_name(name) in expected_away_norms:
                        side_type = SideTypeEnum.AWAY
                    else:
                        side_type = None

                    if side_type is None:
                        continue

                    parsed.append(
                        ParsedSnapshot(
                            book_key=book_key,
                            book_name=book_title,
                            market_type=MarketTypeEnum.MONEYLINE,
                            side_type=side_type,
                            line=None,
                            price=price,
                        )
                    )

            elif market_key == "spreads":
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        continue
                    name = outcome.get("name")
                    price = outcome.get("price")
                    point = outcome.get("point")
                    if not isinstance(name, str) or not isinstance(price, int):
                        continue
                    if not isinstance(point, int | float):
                        continue

                    side_type = None
                    if norm_team_name(name) in expected_home_norms:
                        side_type = SideTypeEnum.HOME
                    elif norm_team_name(name) in expected_away_norms:
                        side_type = SideTypeEnum.AWAY
                    else:
                        side_type = None

                    if side_type is None:
                        continue

                    parsed.append(
                        ParsedSnapshot(
                            book_key=book_key,
                            book_name=book_title,
                            market_type=MarketTypeEnum.SPREAD,
                            side_type=side_type,
                            line=float(point),
                            price=price,
                        )
                    )

            elif market_key == "totals":
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        continue
                    name = outcome.get("name")
                    price = outcome.get("price")
                    point = outcome.get("point")
                    if not isinstance(name, str) or not isinstance(price, int):
                        continue
                    if not isinstance(point, int | float):
                        continue

                    side_type = None
                    n = name.strip().lower()
                    if n == "over":
                        side_type = SideTypeEnum.OVER
                    elif n == "under":
                        side_type = SideTypeEnum.UNDER
                    else:
                        side_type = None

                    if side_type is None:
                        continue

                    parsed.append(
                        ParsedSnapshot(
                            book_key=book_key,
                            book_name=book_title,
                            market_type=MarketTypeEnum.TOTAL,
                            side_type=side_type,
                            line=float(point),
                            price=price,
                        )
                    )

    return parsed
