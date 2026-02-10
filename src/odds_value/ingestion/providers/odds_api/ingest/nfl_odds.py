from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_value.core.config import settings
from odds_value.db.enums import ProviderEnum
from odds_value.db.models.core.game import Game
from odds_value.db.models.core.league import League
from odds_value.db.models.core.season import Season
from odds_value.db.models.core.team import Team
from odds_value.db.models.core.team_alias import TeamAlias
from odds_value.db.models.ingestion.ingested_payload import IngestedPayload
from odds_value.db.models.odds.book import Book
from odds_value.db.models.odds.odds_snapshot import OddsSnapshot
from odds_value.db.repos.core.league_repo import LeagueRepository
from odds_value.db.repos.core.season_repo import SeasonRepository
from odds_value.db.repos.core.team_repo import TeamRepository
from odds_value.db.repos.odds.book_repo import BookRepository
from odds_value.db.repos.odds.odds_snapshot_repo import OddsSnapshotRepository
from odds_value.ingestion.providers.base.client import BaseHttpClient
from odds_value.ingestion.providers.odds_api.client import OddsApiClient
from odds_value.ingestion.providers.odds_api.parser import (
    ParsedSnapshot,
    norm_team_name,
    parse_event_bookmaker_snapshots,
    parse_iso_z,
)

ApiItem = dict[str, Any]


@dataclass(frozen=True)
class IngestOddsApiNflAsOfSeasonResult:
    league_key: str
    season_year: int
    games_seen: int
    games_matched: int
    games_missing_in_provider: int
    snapshots_created: int
    books_created: int
    payloads_created: int


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _sport_key_for_league_key(league_key: str) -> str:
    if league_key.upper() == "NFL":
        return "americanfootball_nfl"
    raise ValueError(f"Unsupported league_key={league_key!r} for odds-api ingestion")


def _build_team_norms(
    session: Session, *, league_id: int, team_id: int, team_repo: TeamRepository
) -> set[str]:
    team = team_repo.one_where(Team.id == team_id)
    norms: set[str] = {TeamAlias.norm(team.name)}

    aliases = (
        session.execute(
            select(TeamAlias).where(TeamAlias.league_id == league_id, TeamAlias.team_id == team_id)
        )
        .scalars()
        .all()
    )
    norms.update({a.alias_norm for a in aliases})
    return norms


def ingest_odds_api_nfl_odds_as_of_kickoff_minus_hours_for_season(
    session: Session,
    *,
    league_key: str,
    season_year: int,
    as_of_hours: int = 6,
    round_to_hour: bool = True,
    regions: str = "us",
    markets: list[str] | None = None,
    bookmakers: list[str] | None = None,
    items_by_captured_at: dict[datetime, list[ApiItem]] | None = None,
    commit_every: int = 250,
) -> IngestOddsApiNflAsOfSeasonResult:
    """Ingest spreads/totals/moneyline from The Odds API for NFL games in a season.

    Strategy: group games by `captured_at = start_time - as_of_hours` and fetch a batch odds response
    for each unique captured_at using `date=...` historical parameter.

    Matching: events are matched to DB games using commence_time (with tolerance) + team alias norms.
    """

    if markets is None:
        markets = ["spreads", "totals", "h2h"]

    if league_key.upper() != "NFL":
        raise ValueError("Only NFL is supported for now")

    league_repo = LeagueRepository(session)
    season_repo = SeasonRepository(session)
    team_repo = TeamRepository(session)
    book_repo = BookRepository(session)
    snap_repo = OddsSnapshotRepository(session)

    league = league_repo.one_where(League.league_key == league_key)
    season = season_repo.one_where(Season.league_id == league.id, Season.year == season_year)

    games = (
        session.execute(
            select(Game)
            .where(Game.league_id == league.id, Game.season_id == season.id)
            .order_by(Game.start_time)
        )
        .scalars()
        .all()
    )

    # Group games by captured_at timestamp.
    #
    # Note: The Odds API "date" historical parameter appears to return discrete snapshots
    # (commonly hourly). Querying at minute-level timestamps (e.g., kickoff 00:20 => date 18:20)
    # can yield empty responses even when odds exist, so we round to the top of the hour by default.
    games_by_captured_at: dict[datetime, list[Game]] = defaultdict(list)
    for g in games:
        if g.start_time is None:
            continue
        captured_at = _as_utc(g.start_time) - timedelta(hours=as_of_hours)
        if round_to_hour:
            captured_at = captured_at.replace(minute=0, second=0, microsecond=0)
        else:
            captured_at = captured_at.replace(second=0, microsecond=0)
        games_by_captured_at[captured_at].append(g)

    http = (
        None
        if items_by_captured_at is not None
        else BaseHttpClient(base_url=settings.odds_api_base_url)
    )
    client = None if http is None else OddsApiClient(http=http)

    sport_key = _sport_key_for_league_key(league_key)

    snapshots_created = 0
    books_created = 0
    payloads_created = 0
    games_matched = 0
    games_missing_in_provider = 0

    # Cache books by key for upsert.
    book_by_key: dict[str, Book] = {b.key: b for b in session.execute(select(Book)).scalars().all()}

    processed_games = 0
    team_norms_cache: dict[int, set[str]] = {}

    try:
        for captured_at, batch_games in sorted(games_by_captured_at.items(), key=lambda kv: kv[0]):
            if items_by_captured_at is not None:
                provider_snapshot_at = captured_at
                items = items_by_captured_at.get(captured_at, [])
            else:
                assert client is not None
                snapshot = client.get_historical_odds(
                    sport_key=sport_key,
                    regions=regions,
                    markets=markets,
                    odds_format="american",
                    date=captured_at,
                    bookmakers=bookmakers,
                )
                provider_snapshot_at = snapshot.timestamp
                items = snapshot.items

            if settings.store_ingested_payloads:
                session.add(
                    IngestedPayload(
                        provider=ProviderEnum.ODDS_API,
                        entity_type="odds_api_batch",
                        entity_key=f"{sport_key}:{captured_at.isoformat()}",
                        fetched_at=datetime.now(tz=UTC),
                        payload_json={
                            "requested_date": captured_at.isoformat(),
                            "snapshot_timestamp": provider_snapshot_at.isoformat(),
                            "items": items,
                        },
                    )
                )
                payloads_created += 1

            # Index provider items by (commence_time, home_norm, away_norm)
            indexed: dict[tuple[datetime, str, str], ApiItem] = {}
            for it in items:
                commence = it.get("commence_time")
                home = it.get("home_team")
                away = it.get("away_team")
                if (
                    not isinstance(commence, str)
                    or not isinstance(home, str)
                    or not isinstance(away, str)
                ):
                    continue
                try:
                    commence_dt = parse_iso_z(commence)
                except ValueError:
                    continue
                indexed[(commence_dt, norm_team_name(home), norm_team_name(away))] = it

            for game in batch_games:
                if (
                    game.id is None
                    or game.start_time is None
                    or game.home_team_id is None
                    or game.away_team_id is None
                ):
                    continue

                expected_home_norms = _build_team_norms(
                    session,
                    league_id=league.id,
                    team_id=game.home_team_id,
                    team_repo=team_repo,
                )
                if game.home_team_id not in team_norms_cache:
                    team_norms_cache[game.home_team_id] = expected_home_norms
                else:
                    expected_home_norms = team_norms_cache[game.home_team_id]

                expected_away_norms = team_norms_cache.get(game.away_team_id)
                if expected_away_norms is None:
                    expected_away_norms = _build_team_norms(
                        session,
                        league_id=league.id,
                        team_id=game.away_team_id,
                        team_repo=team_repo,
                    )
                    team_norms_cache[game.away_team_id] = expected_away_norms

                commence_dt = _as_utc(game.start_time)

                # Try exact match first.
                matched_item: ApiItem | None = None
                for hn in expected_home_norms:
                    for an in expected_away_norms:
                        matched_item = indexed.get((commence_dt, hn, an))
                        if matched_item is not None:
                            break
                    if matched_item is not None:
                        break

                if matched_item is None:
                    # Tolerant match by time within 30 minutes.
                    for (it_commence, it_home, it_away), it in indexed.items():
                        if it_home not in expected_home_norms or it_away not in expected_away_norms:
                            continue
                        delta_s = abs((_as_utc(it_commence) - commence_dt).total_seconds())
                        if delta_s <= 30 * 60:
                            matched_item = it
                            break

                if matched_item is None:
                    games_missing_in_provider += 1
                    continue

                games_matched += 1

                parsed_snapshots: list[ParsedSnapshot] = parse_event_bookmaker_snapshots(
                    matched_item,
                    expected_home_norms=expected_home_norms,
                    expected_away_norms=expected_away_norms,
                )

                for ps in parsed_snapshots:
                    book = book_by_key.get(ps.book_key)
                    if book is None:
                        existing = book_repo.first_where(Book.key == ps.book_key)
                        if existing is None:
                            book = book_repo.add(
                                Book(key=ps.book_key, name=ps.book_name), flush=True
                            )
                            books_created += 1
                        else:
                            book = existing
                            if existing.name != ps.book_name:
                                book_repo.patch(existing, {"name": ps.book_name}, flush=True)
                        book_by_key[ps.book_key] = book

                    existing_snap = snap_repo.first_where(
                        OddsSnapshot.game_id == game.id,
                        OddsSnapshot.book_id == book.id,
                        OddsSnapshot.market_type == ps.market_type,
                        OddsSnapshot.side_type == ps.side_type,
                        OddsSnapshot.captured_at == provider_snapshot_at,
                    )
                    if existing_snap is None:
                        snap_repo.add(
                            OddsSnapshot(
                                game_id=game.id,
                                book_id=book.id,
                                captured_at=provider_snapshot_at,
                                market_type=ps.market_type,
                                side_type=ps.side_type,
                                line=ps.line,
                                price=ps.price,
                                is_closing=False,
                                provider=str(ProviderEnum.ODDS_API),
                            ),
                            flush=False,
                        )
                        snapshots_created += 1

                processed_games += 1
                if commit_every and processed_games % commit_every == 0:
                    session.commit()

            session.commit()

    finally:
        if http is not None:
            http.close()

    return IngestOddsApiNflAsOfSeasonResult(
        league_key=league_key,
        season_year=season_year,
        games_seen=len(games),
        games_matched=games_matched,
        games_missing_in_provider=games_missing_in_provider,
        snapshots_created=snapshots_created,
        books_created=books_created,
        payloads_created=payloads_created,
    )
