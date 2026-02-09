from __future__ import annotations

import typer

from odds_value.cli.common import session_scope
from odds_value.features.football.team_game_state_builder import (
    build_football_team_game_state_for_season,
)

app = typer.Typer(help="Build derived feature tables/state from ingested facts.")


@app.command("build-football-team-game-state")
def build_football_team_game_state_cmd(
    league_key: str = typer.Option(..., "--league-key", help="Canonical league key (e.g. NFL)."),
    season_year: int = typer.Option(..., "--season-year", help="Season year (e.g. 2025)."),
    rebuild: bool = typer.Option(
        False,
        "--rebuild",
        help="When set, delete existing rows for the season and rebuild.",
    ),
    include_non_regular_season: bool = typer.Option(
        False,
        "--include-non-regular-season",
        help="When set, also build rows for games outside the NFL regular season window.",
    ),
    commit_every: int = typer.Option(
        500,
        "--commit-every",
        help="Commit after this many games (0 disables intermediate commits).",
    ),
) -> None:
    """Build `football_team_game_state` for a season (as-of kickoff, no leakage)."""

    with session_scope() as session:
        result = build_football_team_game_state_for_season(
            session,
            league_key=league_key,
            season_year=season_year,
            rebuild=rebuild,
            include_non_regular_season=include_non_regular_season,
            commit_every=commit_every,
        )

    typer.echo(
        " ".join(
            [
                f"Built football team game state {result.league_key} {result.season_year}:",
                f"games_seen={result.games_seen}",
                f"games_skipped={result.games_skipped}",
                f"team_games_seen={result.team_games_seen}",
                f"states_created={result.states_created}",
                f"states_updated={result.states_updated}",
            ]
        )
    )
