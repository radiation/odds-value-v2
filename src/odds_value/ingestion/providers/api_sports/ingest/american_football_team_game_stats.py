from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from odds_value.core.config import settings
from odds_value.db.enums import GameStatusEnum, ProviderEnum, SportEnum
from odds_value.db.models.core.game import Game
from odds_value.db.models.core.league import League
from odds_value.db.models.core.provider_sport import ProviderSport
from odds_value.db.models.core.season import Season
from odds_value.db.models.core.team import Team
from odds_value.db.models.features.football_team_game_stats import FootballTeamGameStats
from odds_value.db.models.features.team_game_stats import TeamGameStats
from odds_value.db.models.ingestion.ingested_payload import IngestedPayload
from odds_value.db.repos.core.game_repo import GameRepository
from odds_value.db.repos.core.league_repo import LeagueRepository
from odds_value.db.repos.core.provider_sport_repo import ProviderSportRepository
from odds_value.db.repos.core.season_repo import SeasonRepository
from odds_value.db.repos.core.team_repo import TeamRepository
from odds_value.db.repos.features.football_team_game_stats_repo import (
    FootballTeamGameStatsRepository,
)
from odds_value.db.repos.features.team_game_stats_repo import TeamGameStatsRepository
from odds_value.ingestion.providers.api_sports.client import ApiSportsClient
from odds_value.ingestion.providers.base.client import BaseHttpClient
from odds_value.ingestion.providers.base.errors import ProviderResponseError

ApiItem = dict[str, Any]


@dataclass(frozen=True)
class IngestAmericanFootballTeamGameStatsResult:
    provider_game_id: str
    items_seen: int
    team_game_stats_created: int
    team_game_stats_updated: int
    football_stats_created: int
    football_stats_updated: int


@dataclass(frozen=True)
class IngestAmericanFootballTeamGameStatsSeasonResult:
    league_key: str
    season_year: int
    games_seen: int
    games_processed: int
    games_failed: int
    games_skipped_existing: int
    failed_game_ids_sample: list[str]
    failure_reasons: dict[str, int]
    items_seen: int
    team_game_stats_created: int
    team_game_stats_updated: int
    football_stats_created: int
    football_stats_updated: int


def _format_failure_reason(exc: BaseException, *, max_len: int = 300) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    reason = f"{exc.__class__.__name__}: {msg}"
    if len(reason) > max_len:
        return f"{reason[: max_len - 1]}…"
    return reason


def _get_api_sports_base_url(session: Session) -> str:
    provider_sport_repo = ProviderSportRepository(session)
    row = provider_sport_repo.one_where(
        ProviderSport.provider == ProviderEnum.API_SPORTS,
        ProviderSport.sport == SportEnum.FOOTBALL,
    )
    return row.base_url


def fetch_api_sports_american_football_team_stats_for_game(
    session: Session,
    *,
    provider_game_id: str,
    client: ApiSportsClient | None = None,
) -> list[ApiItem]:
    """Fetch API-Sports american-football team stats for a single game."""

    created_http: BaseHttpClient | None = None
    if client is None:
        base_url = _get_api_sports_base_url(session)
        api_key = settings.require_api_sports_key()
        created_http = BaseHttpClient(base_url=base_url)
        client = ApiSportsClient(http=created_http, api_key=api_key)

    try:
        # API-Sports docs/behavior has varied between `game` and `id` params; try both.
        try:
            return client.get_response_items(
                "/games/statistics/teams",
                params={"game": str(provider_game_id)},
            )
        except ProviderResponseError:
            return client.get_response_items(
                "/games/statistics/teams",
                params={"id": str(provider_game_id)},
            )
    finally:
        if created_http is not None:
            created_http.close()


def ingest_api_sports_american_football_team_game_stats(
    session: Session,
    *,
    provider_game_id: str,
    items: list[ApiItem] | None = None,
    client: ApiSportsClient | None = None,
) -> IngestAmericanFootballTeamGameStatsResult:
    """Upsert team-game stats for a single API-Sports american-football game."""

    game_repo = GameRepository(session)
    team_repo = TeamRepository(session)
    team_game_stats_repo = TeamGameStatsRepository(session)
    football_repo = FootballTeamGameStatsRepository(session)

    game = game_repo.one_where(
        Game.provider == ProviderEnum.API_SPORTS,
        Game.provider_game_id == str(provider_game_id),
    )

    if items is None:
        items = fetch_api_sports_american_football_team_stats_for_game(
            session,
            provider_game_id=str(provider_game_id),
            client=client,
        )

    now = datetime.now(tz=UTC)

    tgs_created = 0
    tgs_updated = 0
    fb_created = 0
    fb_updated = 0

    for item in items:
        team_obj = item.get("team")
        stats_obj = item.get("statistics")
        if not isinstance(team_obj, dict) or not isinstance(stats_obj, dict):
            continue

        provider_team_id = str(team_obj.get("id"))
        if provider_team_id == "None":
            continue

        team = team_repo.first_where(
            Team.league_id == game.league_id,
            Team.provider_team_id == provider_team_id,
        )
        if team is None:
            team = team_repo.add(
                Team(
                    league_id=game.league_id,
                    provider_team_id=provider_team_id,
                    name=str(team_obj.get("name") or provider_team_id),
                    logo_url=team_obj.get("logo"),
                ),
                flush=True,
            )

        is_home: bool
        if team.id == game.home_team_id:
            is_home = True
        elif team.id == game.away_team_id:
            is_home = False
        else:
            # Defensive: skip stats that don't match the expected home/away teams.
            continue

        score = game.home_score if is_home else game.away_score

        existing_tgs = team_game_stats_repo.first_where(
            TeamGameStats.game_id == game.id,
            TeamGameStats.team_id == team.id,
        )

        if existing_tgs is None:
            existing_tgs = team_game_stats_repo.add(
                TeamGameStats(
                    game_id=game.id,
                    team_id=team.id,
                    is_home=is_home,
                    score=score,
                ),
                flush=True,
            )
            tgs_created += 1
        else:
            team_game_stats_repo.patch(
                existing_tgs,
                {
                    "is_home": is_home,
                    "score": score,
                },
                flush=True,
            )
            tgs_updated += 1

        yards_total: int | None = None
        yards = stats_obj.get("yards")
        if isinstance(yards, dict):
            yt = yards.get("total")
            if isinstance(yt, int):
                yards_total = yt

        turnovers: int | None = None
        to_obj = stats_obj.get("turnovers")
        if isinstance(to_obj, dict):
            tv = to_obj.get("total")
            if isinstance(tv, int):
                turnovers = tv

        existing_fb = football_repo.get(existing_tgs.id)
        if existing_fb is None:
            football_repo.add(
                FootballTeamGameStats(
                    team_game_stats_id=existing_tgs.id,
                    yards_total=yards_total,
                    turnovers=turnovers,
                    stats_json=stats_obj,
                ),
                flush=True,
            )
            fb_created += 1
        else:
            football_repo.patch(
                existing_fb,
                {
                    "yards_total": yards_total,
                    "turnovers": turnovers,
                    "stats_json": stats_obj,
                },
                flush=True,
            )
            fb_updated += 1

        if settings.store_ingested_payloads:
            session.add(
                IngestedPayload(
                    provider=ProviderEnum.API_SPORTS.value,
                    entity_type="team_game_statistics",
                    entity_key=f"{provider_game_id}:{provider_team_id}",
                    fetched_at=now,
                    payload_json=item,
                )
            )

    return IngestAmericanFootballTeamGameStatsResult(
        provider_game_id=str(provider_game_id),
        items_seen=len(items),
        team_game_stats_created=tgs_created,
        team_game_stats_updated=tgs_updated,
        football_stats_created=fb_created,
        football_stats_updated=fb_updated,
    )


def ingest_api_sports_american_football_team_game_stats_for_season(
    session: Session,
    *,
    league_key: str,
    season_year: int,
    max_games: int | None = None,
    only_final: bool = True,
    sleep_seconds: float = 0.0,
    commit_every: int = 25,
    skip_existing: bool = True,
    show_failures: bool = False,
    failures_limit: int = 25,
    stop_on_failure: bool = False,
    items_by_provider_game_id: dict[str, list[ApiItem]] | None = None,
) -> IngestAmericanFootballTeamGameStatsSeasonResult:
    """Fetch and upsert team-game stats for every game in a season.

    This is intentionally provider-agnostic in data modeling, but provider-specific
    in the fetch implementation.
    """

    league_repo = LeagueRepository(session)
    season_repo = SeasonRepository(session)

    league = league_repo.one_where(League.league_key == league_key)
    season = season_repo.one_where(Season.league_id == league.id, Season.year == season_year)

    stmt = (
        select(Game)
        .where(
            Game.provider == ProviderEnum.API_SPORTS,
            Game.league_id == league.id,
            Game.season_id == season.id,
        )
        .order_by(Game.start_time)
    )
    if only_final:
        stmt = stmt.where(Game.status == GameStatusEnum.FINAL)
    if max_games is not None:
        stmt = stmt.limit(max_games)

    games = list(session.execute(stmt).scalars().all())

    games_processed = 0
    games_failed = 0
    games_skipped_existing = 0
    failed_game_ids_sample: list[str] = []
    failure_reasons: dict[str, int] = {}
    items_seen = 0
    tgs_created = 0
    tgs_updated = 0
    fb_created = 0
    fb_updated = 0

    http: BaseHttpClient | None = None
    api_client: ApiSportsClient | None = None
    if items_by_provider_game_id is None:
        base_url = _get_api_sports_base_url(session)
        api_key = settings.require_api_sports_key()
        http = BaseHttpClient(base_url=base_url)
        api_client = ApiSportsClient(http=http, api_key=api_key)

    complete_game_ids: set[int] = set()
    if skip_existing and games:
        # A game is considered "complete" for our purposes if both teams have
        # football stats rows already present (2 per NFL game).
        complete_stmt = (
            select(TeamGameStats.game_id)
            .select_from(TeamGameStats)
            .join(
                FootballTeamGameStats,
                FootballTeamGameStats.team_game_stats_id == TeamGameStats.id,
            )
            .where(TeamGameStats.game_id.in_([g.id for g in games]))
            .group_by(TeamGameStats.game_id)
            .having(func.count(TeamGameStats.id) >= 2)
        )
        complete_game_ids = set(session.execute(complete_stmt).scalars().all())

    try:
        for idx, game in enumerate(games, start=1):
            if skip_existing and game.id in complete_game_ids:
                games_skipped_existing += 1
                continue
            try:
                per_game_items = None
                if items_by_provider_game_id is not None:
                    per_game_items = items_by_provider_game_id.get(game.provider_game_id)

                # Isolate each game in a SAVEPOINT so a single failure doesn't poison
                # the whole batch or force us to rollback prior successes.
                with session.begin_nested():
                    result = ingest_api_sports_american_football_team_game_stats(
                        session,
                        provider_game_id=game.provider_game_id,
                        items=per_game_items,
                        client=api_client,
                    )

                items_seen += result.items_seen
                tgs_created += result.team_game_stats_created
                tgs_updated += result.team_game_stats_updated
                fb_created += result.football_stats_created
                fb_updated += result.football_stats_updated
                games_processed += 1
            except Exception as exc:
                games_failed += 1
                reason = _format_failure_reason(exc)
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                if len(failed_game_ids_sample) < max(0, failures_limit):
                    failed_game_ids_sample.append(str(game.provider_game_id))
                if show_failures:
                    print(f"FAILED provider_game_id={game.provider_game_id} | {reason}")
                if stop_on_failure:
                    raise
                # If SQLAlchemy marked the session as inactive due to a DB error,
                # we must rollback to proceed.
                if not session.is_active:
                    session.rollback()

            if commit_every > 0 and idx % commit_every == 0:
                session.commit()

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    finally:
        if http is not None:
            http.close()

    session.commit()

    return IngestAmericanFootballTeamGameStatsSeasonResult(
        league_key=league_key,
        season_year=season_year,
        games_seen=len(games),
        games_processed=games_processed,
        games_failed=games_failed,
        games_skipped_existing=games_skipped_existing,
        failed_game_ids_sample=failed_game_ids_sample,
        failure_reasons=failure_reasons,
        items_seen=items_seen,
        team_game_stats_created=tgs_created,
        team_game_stats_updated=tgs_updated,
        football_stats_created=fb_created,
        football_stats_updated=fb_updated,
    )
