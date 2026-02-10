from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from odds_value.core.config import settings
from odds_value.db.enums import GameStatusEnum, ProviderEnum, SportEnum
from odds_value.db.models.core.game import Game
from odds_value.db.models.core.league import League
from odds_value.db.models.core.provider_league import ProviderLeague
from odds_value.db.models.core.provider_sport import ProviderSport
from odds_value.db.models.core.provider_team import ProviderTeam
from odds_value.db.models.core.season import Season
from odds_value.db.models.core.team import Team
from odds_value.db.models.core.team_alias import TeamAlias
from odds_value.db.models.core.venue import Venue
from odds_value.db.models.ingestion.ingested_payload import IngestedPayload
from odds_value.db.repos.core.game_repo import GameRepository
from odds_value.db.repos.core.league_repo import LeagueRepository
from odds_value.db.repos.core.provider_league_repo import ProviderLeagueRepository
from odds_value.db.repos.core.provider_sport_repo import ProviderSportRepository
from odds_value.db.repos.core.provider_team_repo import ProviderTeamRepository
from odds_value.db.repos.core.season_repo import SeasonRepository
from odds_value.db.repos.core.team_alias_repo import TeamAliasRepository
from odds_value.db.repos.core.team_repo import TeamRepository
from odds_value.db.repos.core.venue_repo import VenueRepository
from odds_value.ingestion.dates import parse_api_sports_game_datetime
from odds_value.ingestion.football.nfl_calendar import in_nfl_regular_season_window
from odds_value.ingestion.providers.api_sports.client import ApiSportsClient
from odds_value.ingestion.providers.base.client import BaseHttpClient

ApiItem = dict[str, Any]


@dataclass(frozen=True)
class IngestAmericanFootballSeasonResult:
    league_key: str
    season_year: int
    games_seen: int
    games_created: int
    games_updated: int
    teams_created: int
    venues_created: int


def _map_status(short: str | None) -> GameStatusEnum:
    if not short:
        return GameStatusEnum.UNKNOWN

    s = short.upper()

    if s in {"NS"}:
        return GameStatusEnum.SCHEDULED
    if s in {"FT", "AOT", "FINAL"}:
        return GameStatusEnum.FINAL
    if s in {"PST", "PPD"}:
        return GameStatusEnum.POSTPONED
    if s in {"CANC", "CAN", "ABD"}:
        return GameStatusEnum.CANCELED

    return GameStatusEnum.IN_PROGRESS


def _get_api_sports_base_url(session: Session) -> str:
    provider_sport_repo = ProviderSportRepository(session)
    row = provider_sport_repo.one_where(
        ProviderSport.provider == ProviderEnum.API_SPORTS,
        ProviderSport.sport == SportEnum.FOOTBALL,
    )
    return row.base_url


def _get_api_sports_provider_league_id(session: Session, *, league_key: str) -> str:
    league_repo = LeagueRepository(session)
    provider_league_repo = ProviderLeagueRepository(session)

    league = league_repo.one_where(League.league_key == league_key)
    pl = provider_league_repo.one_where(
        ProviderLeague.provider == ProviderEnum.API_SPORTS,
        ProviderLeague.league_id == league.id,
    )
    return pl.provider_league_id


def fetch_api_sports_american_football_games_for_season(
    session: Session,
    *,
    league_key: str,
    season_year: int,
) -> list[ApiItem]:
    """Fetch API-Sports *american-football* games for a league+season.

    Note: This uses the provider sport row for `SportEnum.FOOTBALL`, which in this project
    corresponds to API-Sports' american-football base URL.
    """

    base_url = _get_api_sports_base_url(session)
    provider_league_id = _get_api_sports_provider_league_id(session, league_key=league_key)

    api_key = settings.require_api_sports_key()

    http = BaseHttpClient(base_url=base_url)
    client = ApiSportsClient(http=http, api_key=api_key)
    try:
        return client.get_response_items(
            "/games",
            params={"league": provider_league_id, "season": str(season_year)},
        )
    finally:
        http.close()


def ingest_api_sports_american_football_season(
    session: Session,
    *,
    league_key: str,
    season_year: int,
    items: list[ApiItem] | None = None,
) -> IngestAmericanFootballSeasonResult:
    """Upsert an API-Sports american-football season into the DB."""

    league_repo = LeagueRepository(session)
    season_repo = SeasonRepository(session)
    team_repo = TeamRepository(session)
    provider_team_repo = ProviderTeamRepository(session)
    team_alias_repo = TeamAliasRepository(session)
    venue_repo = VenueRepository(session)
    game_repo = GameRepository(session)

    league = league_repo.one_where(League.league_key == league_key)

    season = season_repo.first_where(Season.league_id == league.id, Season.year == season_year)
    if season is None:
        season = season_repo.add(
            Season(league_id=league.id, year=season_year, name=str(season_year)),
            flush=True,
        )

    if items is None:
        items = fetch_api_sports_american_football_games_for_season(
            session, league_key=league_key, season_year=season_year
        )

    games_created = 0
    games_updated = 0
    teams_created = 0
    venues_created = 0

    now = datetime.now(tz=UTC)

    for item in items:
        game_obj = item.get("game")
        teams_obj = item.get("teams")
        scores_obj = item.get("scores")

        if not isinstance(game_obj, dict) or not isinstance(teams_obj, dict):
            continue

        provider_game_id = str(game_obj.get("id"))
        if provider_game_id == "None":
            continue

        home = teams_obj.get("home")
        away = teams_obj.get("away")
        if not isinstance(home, dict) or not isinstance(away, dict):
            continue

        def upsert_team(team_data: dict[str, Any]) -> Team:
            nonlocal teams_created
            provider_team_id = str(team_data.get("id"))
            provider_team_name = str(team_data.get("name") or provider_team_id)

            mapped = provider_team_repo.first_where(
                ProviderTeam.provider == ProviderEnum.API_SPORTS,
                ProviderTeam.provider_team_id == provider_team_id,
            )
            if mapped is not None:
                team_row = team_repo.one_where(Team.id == mapped.team_id)
                # Keep canonical team row fresh.
                team_repo.patch(
                    team_row,
                    {
                        "name": provider_team_name,
                        "logo_url": team_data.get("logo"),
                        "is_active": True,
                    },
                    flush=True,
                )
                if mapped.provider_team_name != provider_team_name:
                    provider_team_repo.patch(
                        mapped,
                        {"provider_team_name": provider_team_name},
                        flush=True,
                    )
                # Ensure an alias exists for the current name.
                alias_norm = TeamAlias.norm(provider_team_name)
                if (
                    team_alias_repo.first_where(
                        TeamAlias.league_id == league.id,
                        TeamAlias.alias_norm == alias_norm,
                    )
                    is None
                ):
                    team_alias_repo.add(
                        TeamAlias(
                            league_id=league.id,
                            team_id=team_row.id,
                            alias=provider_team_name,
                            alias_norm=alias_norm,
                            alias_type="name",
                        ),
                        flush=True,
                    )
                return team_row

            existing = team_repo.first_where(
                Team.league_id == league.id,
                Team.provider_team_id == provider_team_id,
            )
            if existing is None:
                teams_created += 1
                existing = team_repo.add(
                    Team(
                        league_id=league.id,
                        provider_team_id=provider_team_id,
                        name=provider_team_name,
                        logo_url=team_data.get("logo"),
                    ),
                    flush=True,
                )

                provider_team_repo.add(
                    ProviderTeam(
                        provider=ProviderEnum.API_SPORTS,
                        team_id=existing.id,
                        provider_team_id=provider_team_id,
                        provider_team_name=provider_team_name,
                    ),
                    flush=True,
                )
            else:
                team_repo.patch(
                    existing,
                    {
                        "name": provider_team_name,
                        "logo_url": team_data.get("logo"),
                        "is_active": True,
                    },
                    flush=True,
                )

                mapped_existing = provider_team_repo.first_where(
                    ProviderTeam.provider == ProviderEnum.API_SPORTS,
                    ProviderTeam.provider_team_id == provider_team_id,
                )
                if mapped_existing is None:
                    provider_team_repo.add(
                        ProviderTeam(
                            provider=ProviderEnum.API_SPORTS,
                            team_id=existing.id,
                            provider_team_id=provider_team_id,
                            provider_team_name=provider_team_name,
                        ),
                        flush=True,
                    )
                elif mapped_existing.team_id != existing.id:
                    raise RuntimeError(
                        "ProviderTeam mapping mismatch: "
                        f"provider_team_id={provider_team_id} "
                        f"mapped_team_id={mapped_existing.team_id} "
                        f"existing_team_id={existing.id}"
                    )
                else:
                    provider_team_repo.patch(
                        mapped_existing,
                        {"provider_team_name": provider_team_name},
                        flush=True,
                    )

            alias_norm = TeamAlias.norm(provider_team_name)
            if (
                team_alias_repo.first_where(
                    TeamAlias.league_id == league.id,
                    TeamAlias.alias_norm == alias_norm,
                )
                is None
            ):
                team_alias_repo.add(
                    TeamAlias(
                        league_id=league.id,
                        team_id=existing.id,
                        alias=provider_team_name,
                        alias_norm=alias_norm,
                        alias_type="name",
                    ),
                    flush=True,
                )
            return existing

        home_team = upsert_team(home)
        away_team = upsert_team(away)

        venue_id: int | None = None
        venue_obj = game_obj.get("venue")
        if isinstance(venue_obj, dict):
            venue_name = venue_obj.get("name")
            venue_city = venue_obj.get("city")
            if isinstance(venue_name, str) and venue_name.strip():
                existing_venue = venue_repo.first_where(
                    Venue.league_id == league.id,
                    Venue.name == venue_name,
                    Venue.city == venue_city,
                )
                if existing_venue is None:
                    venues_created += 1
                    existing_venue = venue_repo.add(
                        Venue(
                            league_id=league.id,
                            name=venue_name,
                            city=venue_city if isinstance(venue_city, str) else None,
                        ),
                        flush=True,
                    )
                venue_id = existing_venue.id

        status_short: str | None = None
        status_obj = game_obj.get("status")
        if isinstance(status_obj, dict):
            ss = status_obj.get("short")
            if isinstance(ss, str):
                status_short = ss

        date_obj = game_obj.get("date")
        try:
            start_time = parse_api_sports_game_datetime(date_obj, provider_game_id=provider_game_id)
        except ValueError:
            continue

        # Payload-agnostic filter: only persist NFL regular season games.
        if league_key == "NFL" and not in_nfl_regular_season_window(start_time, season_year):
            continue

        home_total: int | None = None
        away_total: int | None = None
        if isinstance(scores_obj, dict):
            home_scores = scores_obj.get("home")
            away_scores = scores_obj.get("away")
            if isinstance(home_scores, dict):
                ht = home_scores.get("total")
                if isinstance(ht, int):
                    home_total = ht
            if isinstance(away_scores, dict):
                at = away_scores.get("total")
                if isinstance(at, int):
                    away_total = at

        existing_game = game_repo.first_where(
            Game.provider == ProviderEnum.API_SPORTS,
            Game.provider_game_id == provider_game_id,
        )

        changes = {
            "league_id": league.id,
            "season_id": season.id,
            "start_time": start_time,
            "venue_id": venue_id,
            "status": _map_status(status_short),
            "home_team_id": home_team.id,
            "away_team_id": away_team.id,
            "home_score": home_total,
            "away_score": away_total,
            "source_last_seen_at": now,
        }

        if existing_game is None:
            game_repo.add(
                Game(
                    league_id=league.id,
                    season_id=season.id,
                    provider=ProviderEnum.API_SPORTS,
                    provider_game_id=provider_game_id,
                    start_time=start_time,
                    venue_id=venue_id,
                    status=changes["status"],
                    is_neutral_site=False,
                    home_team_id=home_team.id,
                    away_team_id=away_team.id,
                    home_score=home_total,
                    away_score=away_total,
                    source_last_seen_at=now,
                ),
                flush=True,
            )
            games_created += 1
        else:
            game_repo.patch(existing_game, changes, flush=True)
            games_updated += 1

        if settings.store_ingested_payloads:
            session.add(
                IngestedPayload(
                    provider=ProviderEnum.API_SPORTS.value,
                    entity_type="game",
                    entity_key=provider_game_id,
                    fetched_at=now,
                    payload_json=item,
                )
            )

    return IngestAmericanFootballSeasonResult(
        league_key=league_key,
        season_year=season_year,
        games_seen=len(items),
        games_created=games_created,
        games_updated=games_updated,
        teams_created=teams_created,
        venues_created=venues_created,
    )
