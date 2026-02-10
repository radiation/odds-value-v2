from __future__ import annotations

from pathlib import Path

import typer

from odds_value.cli.common import session_scope
from odds_value.modeling.football.dataset import (
    build_football_game_dataset,
    write_football_game_dataset_csv,
)
from odds_value.modeling.football.splits import split_by_season_year
from odds_value.modeling.football.train_point_diff import train_point_diff_ridge

app = typer.Typer(help="Modeling utilities (dataset export, splits, training scaffolds).")


@app.command("export-football-game-dataset")
def export_football_game_dataset_cmd(
    league_key: str = typer.Option("NFL", "--league-key", help="Canonical league key."),
    season_start_year: int | None = typer.Option(
        None, "--season-start-year", help="Inclusive season start year filter (e.g. 2016)."
    ),
    season_end_year: int | None = typer.Option(
        None, "--season-end-year", help="Inclusive season end year filter (e.g. 2025)."
    ),
    out: str = typer.Option(
        "football_game_dataset.csv",
        "--out",
        help="Output CSV path.",
        dir_okay=False,
        writable=True,
    ),
) -> None:
    """Export a game-level dataset from `football_team_game_state` to CSV.

    This emits one row per game (home+away state merged) with targets like `point_diff` and `home_win`.

    Recommended splitting strategy: time-based (by `season_year`).
    """

    with session_scope() as session:
        rows = build_football_game_dataset(
            session,
            league_key=league_key,
            season_start_year=season_start_year,
            season_end_year=season_end_year,
            require_final=True,
        )

    out_path = Path(out)
    write_football_game_dataset_csv(rows, path=out_path)

    typer.echo(f"Exported {len(rows)} rows to {out_path}")


@app.command("train-football-point-diff")
def train_football_point_diff_cmd(
    league_key: str = typer.Option("NFL", "--league-key", help="Canonical league key."),
    season_start_year: int = typer.Option(
        2016,
        "--season-start-year",
        help="Inclusive season start year filter (default: 2016).",
    ),
    train_end_year: int = typer.Option(
        2023,
        "--train-end-year",
        help="Train on seasons <= this year (default: 2023).",
    ),
    val_year: int = typer.Option(
        2024,
        "--val-year",
        help="Validation season year (default: 2024).",
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
) -> None:
    """Train a baseline model to predict `point_diff`.

    This trains directly from the DB (via `football_team_game_state` + `games`) and uses
    time-based season splits to avoid leakage.
    """

    season_end_year = max(train_end_year, val_year, test_year)

    with session_scope() as session:
        rows = build_football_game_dataset(
            session,
            league_key=league_key,
            season_start_year=season_start_year,
            season_end_year=season_end_year,
            require_final=True,
        )

    split = split_by_season_year(
        rows,
        train_end_year=train_end_year,
        val_year=val_year,
        test_year=test_year,
    )

    if not split.train:
        raise typer.BadParameter("No training rows found for the selected years")
    if not split.val:
        raise typer.BadParameter("No validation rows found for the selected years")
    if not split.test:
        raise typer.BadParameter("No test rows found for the selected years")

    result, _model = train_point_diff_ridge(
        train_rows=split.train,
        val_rows=split.val,
        test_rows=split.test,
        alpha=alpha,
    )

    typer.echo(
        " ".join(
            [
                f"point_diff ridge alpha={alpha}",
                f"train={result.train_size}",
                f"val={result.val_size}",
                f"test={result.test_size}",
            ]
        )
    )
    typer.echo(
        " ".join(
            [
                f"train: MAE={result.train_metrics.mae:.3f}",
                f"RMSE={result.train_metrics.rmse:.3f}",
                f"R2={result.train_metrics.r2:.3f}",
            ]
        )
    )
    typer.echo(
        " ".join(
            [
                f"val:   MAE={result.val_metrics.mae:.3f}",
                f"RMSE={result.val_metrics.rmse:.3f}",
                f"R2={result.val_metrics.r2:.3f}",
            ]
        )
    )
    typer.echo(
        " ".join(
            [
                f"test:  MAE={result.test_metrics.mae:.3f}",
                f"RMSE={result.test_metrics.rmse:.3f}",
                f"R2={result.test_metrics.r2:.3f}",
            ]
        )
    )
