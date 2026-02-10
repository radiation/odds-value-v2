from __future__ import annotations

import typer

from odds_value.cli.common import session_scope
from odds_value.db.enums import ProviderEnum, SportEnum
from odds_value.db.models.core.league import League
from odds_value.db.models.core.provider_league import ProviderLeague
from odds_value.db.models.core.provider_sport import ProviderSport
from odds_value.db.models.core.team import Team
from odds_value.db.models.core.team_alias import TeamAlias
from odds_value.db.repos.core.league_repo import LeagueRepository
from odds_value.db.repos.core.provider_league_repo import ProviderLeagueRepository
from odds_value.db.repos.core.provider_sport_repo import ProviderSportRepository
from odds_value.db.repos.core.team_alias_repo import TeamAliasRepository
from odds_value.db.repos.core.team_repo import TeamRepository

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
            existing_league = league_repo.first_where(League.league_key == league.league_key)
            if existing_league is None:
                league_repo.add(league, flush=False)
                league_by_key[league.league_key] = league
            else:
                league_repo.patch(
                    existing_league,
                    {
                        "name": league.name,
                        "sport": league.sport,
                        "country": league.country,
                    },
                    flush=False,
                )
                league_by_key[existing_league.league_key] = existing_league

        # ensure IDs exist for provider leagues
        session.flush()

        # ---- Provider sports (upsert) ----
        for ps in provider_sports_to_seed:
            existing_provider_sport = provider_sport_repo.first_where(
                ProviderSport.provider == ps.provider,
                ProviderSport.sport == ps.sport,
            )
            if existing_provider_sport is None:
                provider_sport_repo.add(ps, flush=False)
            else:
                provider_sport_repo.patch(
                    existing_provider_sport,
                    {"base_url": ps.base_url},
                    flush=False,
                )

        # ---- Provider leagues (upsert) ----
        for pl in provider_leagues_to_seed:
            league_key = pl.league.league_key
            league_row = league_by_key.get(league_key)
            if league_row is None:
                league_row = league_repo.one_where(League.league_key == league_key)

            existing_provider_league = provider_league_repo.first_where(
                ProviderLeague.provider == pl.provider,
                ProviderLeague.league_id == league_row.id,
            )
            if existing_provider_league is None:
                row = ProviderLeague(
                    provider=pl.provider,
                    league_id=league_row.id,
                    provider_league_id=pl.provider_league_id,
                    provider_league_name=pl.provider_league_name,
                )
                provider_league_repo.add(row, flush=False)
            else:
                provider_league_repo.patch(
                    existing_provider_league,
                    {
                        "provider_league_id": pl.provider_league_id,
                        "provider_league_name": pl.provider_league_name,
                    },
                    flush=False,
                )

        session.commit()

    typer.echo("Provider & league data seeded.")


@app.command("seed-team-aliases")
def seed_team_aliases(
    league_key: str = typer.Option("NFL", "--league-key", help="League key to seed aliases for."),
) -> None:
    """Seed historical name aliases for teams (e.g., relocations/renames)."""

    with session_scope() as session:
        league_repo = LeagueRepository(session)
        team_repo = TeamRepository(session)
        alias_repo = TeamAliasRepository(session)

        league = league_repo.one_where(League.league_key == league_key)

        # Ensure every current team name is also an alias.
        teams = list(session.query(Team).filter(Team.league_id == league.id).all())
        created = 0

        if not teams:
            typer.echo(
                f"No teams found for {league_key}. Seed aliases after ingesting teams (or creating Team rows)."
            )

        existing_alias_norms: set[str] = set(
            row
            for (row,) in session.query(TeamAlias.alias_norm)
            .filter(TeamAlias.league_id == league.id)
            .all()
        )

        def ensure_alias(team_id: int, alias: str) -> None:
            nonlocal created
            alias_norm = TeamAlias.norm(alias)
            if alias_norm in existing_alias_norms:
                return

            existing = alias_repo.first_where(
                TeamAlias.league_id == league.id,
                TeamAlias.alias_norm == alias_norm,
            )
            if existing is None:
                alias_repo.add(
                    TeamAlias(
                        league_id=league.id,
                        team_id=team_id,
                        alias=alias,
                        alias_norm=alias_norm,
                        alias_type="name",
                    ),
                    flush=False,
                )
                existing_alias_norms.add(alias_norm)
                created += 1
            else:
                existing_alias_norms.add(alias_norm)

        for t in teams:
            ensure_alias(t.id, t.name)

        # League-specific historical aliases (NFL)
        if league_key.upper() == "NFL":
            groups: list[tuple[list[str], list[str]]] = [
                (
                    [
                        "Washington Commanders",
                        "Washington Football Team",
                        "Washington Redskins",
                    ],
                    ["Washington Commanders", "Washington Football Team", "Washington Redskins"],
                ),
                (
                    ["Los Angeles Rams", "St. Louis Rams"],
                    ["Los Angeles Rams", "St. Louis Rams"],
                ),
                (
                    ["Los Angeles Chargers", "San Diego Chargers"],
                    ["Los Angeles Chargers", "San Diego Chargers"],
                ),
            ]

            for match_names, aliases in groups:
                team = team_repo.first_where(
                    Team.league_id == league.id,
                    Team.name.in_(match_names),
                )
                if team is None:
                    continue
                for a in aliases:
                    ensure_alias(team.id, a)

        session.commit()

    typer.echo(f"Seeded team aliases for {league_key}. created={created}")
