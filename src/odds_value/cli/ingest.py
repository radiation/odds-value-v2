from __future__ import annotations

import typer

from odds_value.cli.common import session_scope
from odds_value.ingestion.providers.api_sports.ingest.american_football_season import (
    ingest_api_sports_american_football_season,
)
from odds_value.ingestion.providers.api_sports.ingest.american_football_team_game_stats import (
    ingest_api_sports_american_football_team_game_stats,
    ingest_api_sports_american_football_team_game_stats_for_season,
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


@app.command("api-sports-american-football-team-game-stats")
def ingest_api_sports_american_football_team_game_stats_cmd(
    provider_game_id: str = typer.Option(
        ...,
        "--provider-game-id",
        help="API-Sports provider game id (e.g. 17281).",
    ),
) -> None:
    """Fetch API-Sports team statistics for a game and upsert into stats tables."""

    with session_scope() as session:
        result = ingest_api_sports_american_football_team_game_stats(
            session,
            provider_game_id=provider_game_id,
        )

    typer.echo(
        " ".join(
            [
                f"Ingested game stats provider_game_id={result.provider_game_id}:",
                f"items_seen={result.items_seen}",
                f"team_game_stats_created={result.team_game_stats_created}",
                f"team_game_stats_updated={result.team_game_stats_updated}",
                f"football_stats_created={result.football_stats_created}",
                f"football_stats_updated={result.football_stats_updated}",
            ]
        )
    )


@app.command("api-sports-american-football-team-game-stats-season")
def ingest_api_sports_american_football_team_game_stats_season_cmd(
    league_key: str = typer.Option(
        ..., "--league-key", help="Canonical league key (e.g. NFL or NCAAF)."
    ),
    season_year: int = typer.Option(..., "--season-year", help="Season year (e.g. 2025)."),
    max_games: int | None = typer.Option(
        None,
        "--max-games",
        help="Optional cap on number of games processed (for testing).",
    ),
    include_non_final: bool = typer.Option(
        False,
        "--include-non-final",
        help="When set, also attempt stats fetch for non-final games.",
    ),
    sleep_seconds: float = typer.Option(
        0.0,
        "--sleep-seconds",
        help="Optional sleep between API calls to avoid rate limiting.",
    ),
    commit_every: int = typer.Option(
        25,
        "--commit-every",
        help="Commit after this many games (0 disables intermediate commits).",
    ),
    show_failures: bool = typer.Option(
        False,
        "--show-failures/--no-show-failures",
        help="Print provider_game_id + error for each failed game.",
    ),
    failures_limit: int = typer.Option(
        25,
        "--failures-limit",
        help="Max failed provider_game_id values to retain in the returned summary.",
    ),
    stop_on_failure: bool = typer.Option(
        False,
        "--stop-on-failure",
        help="Stop immediately and raise the underlying exception.",
    ),
) -> None:
    """Fetch API-Sports team statistics for all games in a season and upsert."""

    with session_scope() as session:
        result = ingest_api_sports_american_football_team_game_stats_for_season(
            session,
            league_key=league_key,
            season_year=season_year,
            max_games=max_games,
            only_final=not include_non_final,
            sleep_seconds=sleep_seconds,
            commit_every=commit_every,
            show_failures=show_failures,
            failures_limit=failures_limit,
            stop_on_failure=stop_on_failure,
        )

    typer.echo(
        " ".join(
            [
                f"Ingested season team stats {result.league_key} {result.season_year}:",
                f"games_seen={result.games_seen}",
                f"games_processed={result.games_processed}",
                f"games_failed={result.games_failed}",
                f"failed_ids_sample={len(result.failed_game_ids_sample)}",
                f"items_seen={result.items_seen}",
                f"team_game_stats_created={result.team_game_stats_created}",
                f"team_game_stats_updated={result.team_game_stats_updated}",
                f"football_stats_created={result.football_stats_created}",
                f"football_stats_updated={result.football_stats_updated}",
            ]
        )
    )

    if result.games_failed and result.failure_reasons:
        top = sorted(result.failure_reasons.items(), key=lambda kv: kv[1], reverse=True)[:5]
        typer.echo("Failures (top):")
        for reason, count in top:
            typer.echo(f"  {count}x {reason}")
