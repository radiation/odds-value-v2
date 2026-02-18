"""Modeling CLI commands.

This module should stay mostly as Typer option definitions.
Implementation lives in `odds_value.modeling.football.commands`.
"""

from __future__ import annotations

import typer

from odds_value.cli.common import session_scope
from odds_value.modeling.football.commands import (
    FootballPointDiffTarget,
    SweepSplit,
    export_football_game_dataset,
    train_football_point_diff,
)

app = typer.Typer(help="Modeling utilities (dataset export, splits, training scaffolds).")


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


def _split_float_csv(value: str | None) -> list[float] | None:
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    floats: list[float] = []
    for p in parts:
        if not p:
            continue
        floats.append(float(p))
    return floats or None


@app.command("export-football-game-dataset")
def export_football_game_dataset_cmd(
    league_key: str = typer.Option("NFL", "--league-key", help="Canonical league key."),
    season_start_year: int | None = typer.Option(
        None, "--season-start-year", help="Inclusive season start year filter (e.g. 2016)."
    ),
    season_end_year: int | None = typer.Option(
        None, "--season-end-year", help="Inclusive season end year filter (e.g. 2025)."
    ),
    include_elo_features: bool = typer.Option(
        False,
        "--include-elo-features/--no-include-elo-features",
        help="Include Elo pregame ratings as features (derived from prior results only).",
    ),
    out: str = typer.Option(
        "football_game_dataset.csv",
        "--out",
        help="Output CSV path.",
        dir_okay=False,
        writable=True,
    ),
) -> None:
    """Export a game-level dataset from `football_team_game_state` to CSV."""

    export_football_game_dataset(
        session_scope=session_scope,
        echo=typer.echo,
        league_key=league_key,
        season_start_year=season_start_year,
        season_end_year=season_end_year,
        include_elo_features=include_elo_features,
        out=out,
    )


@app.command("train-football-point-diff")
def train_football_point_diff_cmd(
    league_key: str = typer.Option("NFL", "--league-key", help="Canonical league key."),
    season_start_year: int = typer.Option(
        2016,
        "--season-start-year",
        help="Inclusive season start year filter (default: 2016).",
    ),
    train_end_year: int | None = typer.Option(
        None,
        "--train-end-year",
        help="Train on seasons <= this year (default: val_year - 1).",
    ),
    val_year: int | None = typer.Option(
        None,
        "--val-year",
        help="Validation season year (default: test_year - 1).",
    ),
    test_year: int = typer.Option(
        2025,
        "--test-year",
        help="Test season year (default: 2025).",
    ),
    alpha: float = typer.Option(
        1.0,
        "--alpha",
        help="Ridge regularization strength.",
        min=0.0,
    ),
    target: FootballPointDiffTarget = typer.Option(  # noqa: B008
        FootballPointDiffTarget.POINT_DIFF,
        "--target",
        help="Training target: point-diff (baseline) or residual-vs-spread (learn market error).",
        case_sensitive=False,
    ),
    compare_to_market: bool = typer.Option(
        True,
        "--compare-to-market/--no-compare-to-market",
        help="Compare test predictions to decision-time spreads and print a simple ATS/ROI summary.",
    ),
    as_of_hours: int = typer.Option(
        6,
        "--as-of-hours",
        help="Decision-time offset for market lookup: captured_at ≈ kickoff - N hours.",
        min=0,
    ),
    min_edge_points: float = typer.Option(
        1.0,
        "--min-edge-points",
        help="Only bet when (model - market) exceeds this threshold in points.",
        min=0.0,
    ),
    sweep_min_edge_points_csv: str | None = typer.Option(
        None,
        "--sweep-min-edge-points",
        help="Optional comma-separated edge thresholds to evaluate on the validation split (e.g. 1,1.5,2,2.5,3).",
    ),
    sweep_min_bets: int = typer.Option(
        50,
        "--sweep-min-bets",
        help="Minimum number of bets required for a threshold to be eligible when selecting best ROI.",
        min=0,
    ),
    sweep_split: SweepSplit = typer.Option(  # noqa: B008
        SweepSplit.VAL,
        "--sweep-split",
        help="Which split to use for the edge threshold sweep (default: val).",
        case_sensitive=False,
    ),
    walk_forward: bool = typer.Option(
        False,
        "--walk-forward/--no-walk-forward",
        help="Run walk-forward evaluation over a range of test years (tune edge threshold on val, then evaluate on test).",
    ),
    walk_forward_start_test_year: int | None = typer.Option(
        None,
        "--walk-forward-start-test-year",
        help="Inclusive start year for walk-forward test years (e.g. 2020).",
    ),
    walk_forward_end_test_year: int | None = typer.Option(
        None,
        "--walk-forward-end-test-year",
        help="Inclusive end year for walk-forward test years (e.g. 2025).",
    ),
    walk_forward_val_window_years: int = typer.Option(
        1,
        "--walk-forward-val-window-years",
        help="In walk-forward mode, tune thresholds on the last N seasons before each test season (default: 1).",
        min=1,
    ),
    odds_window_minutes: int = typer.Option(
        180,
        "--odds-window-minutes",
        help="Search window (+/- minutes) around kickoff-Nh to find the closest provider snapshot.",
        min=1,
    ),
    min_market_books: int = typer.Option(
        1,
        "--min-market-books",
        help="Only compare/bet when the decision-time snapshot includes at least this many books.",
        min=1,
    ),
    round_to_hour: bool = typer.Option(
        True,
        "--round-to-hour/--no-round-to-hour",
        help="Round kickoff-Nh to the top of the hour when looking up spreads.",
    ),
    books_csv: str | None = typer.Option(
        None,
        "--books",
        help="Optional comma-separated book keys to use for consensus spreads (e.g. draftkings,fanduel,betmgm).",
    ),
    include_market_features: bool = typer.Option(
        False,
        "--include-market-features/--no-include-market-features",
        help="For residual-vs-spread only: include decision-time market spread info as model features.",
    ),
    include_elo_features: bool = typer.Option(
        False,
        "--include-elo-features/--no-include-elo-features",
        help="Include Elo pregame ratings as features (derived from prior results only).",
    ),
) -> None:
    sweep_thresholds = _split_float_csv(sweep_min_edge_points_csv)
    book_keys = _split_csv(books_csv)

    try:
        train_football_point_diff(
            session_scope=session_scope,
            echo=typer.echo,
            league_key=league_key,
            season_start_year=season_start_year,
            train_end_year=train_end_year,
            val_year=val_year,
            test_year=test_year,
            alpha=alpha,
            target=target,
            compare_to_market=compare_to_market,
            as_of_hours=as_of_hours,
            min_edge_points=min_edge_points,
            sweep_thresholds=sweep_thresholds,
            sweep_min_bets=sweep_min_bets,
            sweep_split=sweep_split,
            walk_forward=walk_forward,
            walk_forward_start_test_year=walk_forward_start_test_year,
            walk_forward_end_test_year=walk_forward_end_test_year,
            walk_forward_val_window_years=walk_forward_val_window_years,
            odds_window_minutes=odds_window_minutes,
            min_market_books=min_market_books,
            round_to_hour=round_to_hour,
            book_keys=book_keys,
            include_market_features=include_market_features,
            include_elo_features=include_elo_features,
        )
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e


__all__ = [
    "FootballPointDiffTarget",
    "SweepSplit",
    "app",
    "export_football_game_dataset_cmd",
    "train_football_point_diff_cmd",
]
