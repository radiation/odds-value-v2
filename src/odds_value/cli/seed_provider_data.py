from __future__ import annotations

import typer

from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_value.cli.common import session_scope
from odds_value.db.enums import ProviderEnum, SportEnum
from odds_value.db.models.core.league import League
from odds_value.db.models.core.provider_league import ProviderLeague
from odds_value.db.models.core.provider_sport import ProviderSport


API_SPORTS_BASEBALL_BASE_URL = "https://v1.baseball.api-sports.io"
API_SPORTS_BASKETBALL_BASE_URL = "https://v1.basketball.api-sports.io"
API_SPORTS_FOOTBALL_BASE_URL = "https://v1.american-football.api-sports.io"
API_SPORTS_BASEBALL_ID = "999" # TODO: Get actual MLB league ID
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

def upsert_league(session: Session, league: League) -> League:
    existing = session.execute(
        select(League).where(League.league_key == league.league_key)
    ).scalar_one_or_none()

    if existing is None:
        session.add(league)
        return league

    # Optional: keep names/country updated
    existing.name = league.name
    existing.sport = league.sport
    existing.country = league.country
    return existing


def upsert_provider_sport(session: Session, ps: ProviderSport) -> ProviderSport:
    existing = session.execute(
        select(ProviderSport).where(
            ProviderSport.provider == ps.provider,
            ProviderSport.sport == ps.sport,
        )
    ).scalar_one_or_none()

    if existing is None:
        session.add(ps)
        return ps

    existing.base_url = ps.base_url
    return existing


def upsert_provider_league(session: Session, pl: ProviderLeague) -> ProviderLeague:
    # Ensure League row exists
    league = session.execute(
        select(League).where(League.league_key == pl.league.league_key)
    ).scalar_one()

    existing = session.execute(
        select(ProviderLeague).where(
            ProviderLeague.provider == pl.provider,
            ProviderLeague.league_id == league.id,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = ProviderLeague(
            provider=pl.provider,
            league_id=league.id,
            provider_league_id=pl.provider_league_id,
            provider_league_name=pl.provider_league_name,
        )
        session.add(row)
        return row

    existing.provider_league_id = pl.provider_league_id
    existing.provider_league_name = pl.provider_league_name
    return existing


@app.command("seed-all")
def seed_provider_data() -> None:
    with session_scope() as session:
        for league in leagues_to_seed:
            upsert_league(session, league)
        session.flush()  # Ensure leagues have IDs for provider league foreign keys
        for provider_sport in provider_sports_to_seed:
            upsert_provider_sport(session, provider_sport)
        for provider_league in provider_leagues_to_seed:
            upsert_provider_league(session, provider_league)

    typer.echo("Provider & league data seeded.")
