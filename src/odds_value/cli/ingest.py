from __future__ import annotations

import typer

from odds_value.cli.common import session_scope
from odds_value.ingestion.providers.api_sports.ingest.american_football_season import (
    ingest_api_sports_american_football_season,
)

app = typer.Typer(help="Ingest provider data into the local DB.")


@app.command("api-sports-season")
def ingest_api_sports_season_cmd(
    league_key: str = typer.Option(..., "--league-key", help="Canonical league key (e.g. NFL)."),
    season_year: int = typer.Option(..., "--season-year", help="Season year (e.g. 2025)."),
) -> None:
    """Deprecated alias for `api-sports-american-football-season`."""

    with session_scope() as session:
        result = ingest_api_sports_american_football_season(
            session,
            league_key=league_key,
            season_year=season_year,
        )

    typer.echo(
        " ".join(
            [
                f"Ingested {result.league_key} {result.season_year}:",
                f"games_seen={result.games_seen}",
                f"games_created={result.games_created}",
                f"games_updated={result.games_updated}",
                f"teams_created={result.teams_created}",
                f"venues_created={result.venues_created}",
            ]
        )
    )


@app.command("api-sports-american-football-season")
def ingest_api_sports_american_football_season_cmd(
    league_key: str = typer.Option(
        ..., "--league-key", help="Canonical league key (e.g. NFL or NCAAF)."
    ),
    season_year: int = typer.Option(..., "--season-year", help="Season year (e.g. 2025)."),
) -> None:
    """Fetch an API-Sports american-football season and upsert teams/venues/games."""

    with session_scope() as session:
        result = ingest_api_sports_american_football_season(
            session,
            league_key=league_key,
            season_year=season_year,
        )

    typer.echo(
        " ".join(
            [
                f"Ingested {result.league_key} {result.season_year}:",
                f"games_seen={result.games_seen}",
                f"games_created={result.games_created}",
                f"games_updated={result.games_updated}",
                f"teams_created={result.teams_created}",
                f"venues_created={result.venues_created}",
            ]
        )
    )
