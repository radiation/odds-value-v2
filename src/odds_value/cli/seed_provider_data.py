from __future__ import annotations

import typer

from odds_value.cli.common import session_scope
from odds_value.db.enums import ProviderEnum, SportEnum
from odds_value.db.models.core.league import League
from odds_value.db.models.core.provider_league import ProviderLeague
from odds_value.db.models.core.provider_sport import ProviderSport

from odds_value.db.repos.core.league_repo import LeagueRepository
from odds_value.db.repos.core.provider_league_repo import ProviderLeagueRepository
from odds_value.db.repos.core.provider_sport_repo import ProviderSportRepository


API_SPORTS_BASEBALL_BASE_URL = "https://v1.baseball.api-sports.io"
API_SPORTS_BASKETBALL_BASE_URL = "https://v1.basketball.api-sports.io"
API_SPORTS_FOOTBALL_BASE_URL = "https://v1.american-football.api-sports.io"

API_SPORTS_BASEBALL_ID = "999"  # TODO: Get actual MLB league ID
API_SPORTS_BASKETBALL_ID = "12"
API_SPORTS_NFL_LEAGUE_ID = "1"

app = typer.Typer(help="Seed basic provider data.")

mlb = League(
    league_key="MLB",
    name="Major League Baseball",
    sport=SportEnum.BASEBALL,
    country="USA",
)
nba = League(
    league_key="NBA",
    name="National Basketball Association",
    sport=SportEnum.BASKETBALL,
    country="USA",
)
nfl = League(
    league_key="NFL",
    name="National Football League",
    sport=SportEnum.FOOTBALL,
    country="USA",
)
leagues_to_seed: list[League] = [mlb, nba, nfl]

provider_sports_to_seed: list[ProviderSport] = [
    ProviderSport(
        provider=ProviderEnum.API_SPORTS,
        sport=SportEnum.BASEBALL,
        base_url=API_SPORTS_BASEBALL_BASE_URL,
    ),
    ProviderSport(
        provider=ProviderEnum.API_SPORTS,
        sport=SportEnum.BASKETBALL,
        base_url=API_SPORTS_BASKETBALL_BASE_URL,
    ),
    ProviderSport(
        provider=ProviderEnum.API_SPORTS,
        sport=SportEnum.FOOTBALL,
        base_url=API_SPORTS_FOOTBALL_BASE_URL,
    ),
]

provider_leagues_to_seed: list[ProviderLeague] = [
    ProviderLeague(
        provider=ProviderEnum.API_SPORTS,
        league=mlb,
        provider_league_id=API_SPORTS_BASEBALL_ID,
        provider_league_name="MLB (API_SPORTS)",
    ),
    ProviderLeague(
        provider=ProviderEnum.API_SPORTS,
        league=nba,
        provider_league_id=API_SPORTS_BASKETBALL_ID,
        provider_league_name="NBA (API_SPORTS)",
    ),
    ProviderLeague(
        provider=ProviderEnum.API_SPORTS,
        league=nfl,
        provider_league_id=API_SPORTS_NFL_LEAGUE_ID,
        provider_league_name="NFL (API_SPORTS)",
    ),
]


@app.command("seed-all")
def seed_provider_data() -> None:
    with session_scope() as session:
        league_repo = LeagueRepository(session)
        provider_sport_repo = ProviderSportRepository(session)
        provider_league_repo = ProviderLeagueRepository(session)

        # ---- Leagues (upsert) ----
        league_by_key: dict[str, League] = {}

        for league in leagues_to_seed:
            existing = league_repo.first_where(League.league_key == league.league_key)
            if existing is None:
                league_repo.add(league, flush=False)
                league_by_key[league.league_key] = league
            else:
                league_repo.patch(
                    existing,
                    {
                        "name": league.name,
                        "sport": league.sport,
                        "country": league.country,
                    },
                    flush=False,
                )
                league_by_key[existing.league_key] = existing

        # ensure IDs exist for provider leagues
        session.flush()

        # ---- Provider sports (upsert) ----
        for ps in provider_sports_to_seed:
            existing = provider_sport_repo.first_where(
                ProviderSport.provider == ps.provider,
                ProviderSport.sport == ps.sport,
            )
            if existing is None:
                provider_sport_repo.add(ps, flush=False)
            else:
                provider_sport_repo.patch(
                    existing,
                    {"base_url": ps.base_url},
                    flush=False,
                )

        # ---- Provider leagues (upsert) ----
        for pl in provider_leagues_to_seed:
            league_key = pl.league.league_key
            league_row = league_by_key.get(league_key)
            if league_row is None:
                league_row = league_repo.one_where(League.league_key == league_key)

            existing = provider_league_repo.first_where(
                ProviderLeague.provider == pl.provider,
                ProviderLeague.league_id == league_row.id,
            )
            if existing is None:
                row = ProviderLeague(
                    provider=pl.provider,
                    league_id=league_row.id,
                    provider_league_id=pl.provider_league_id,
                    provider_league_name=pl.provider_league_name,
                )
                provider_league_repo.add(row, flush=False)
            else:
                provider_league_repo.patch(
                    existing,
                    {
                        "provider_league_id": pl.provider_league_id,
                        "provider_league_name": pl.provider_league_name,
                    },
                    flush=False,
                )

        session.commit()

    typer.echo("Provider & league data seeded.")
