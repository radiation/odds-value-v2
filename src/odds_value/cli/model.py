from __future__ import annotations

from pathlib import Path

import typer

from odds_value.cli.common import session_scope
from odds_value.modeling.football.dataset import (
    build_football_game_dataset,
    write_football_game_dataset_csv,
)
from odds_value.modeling.football.splits import split_by_season_year
from odds_value.modeling.football.train_point_diff import (
    compare_point_diff_model_vs_spread_market,
    train_point_diff_ridge,
)

app = typer.Typer(help="Modeling utilities (dataset export, splits, training scaffolds).")


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


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
    odds_window_minutes: int = typer.Option(
        180,
        "--odds-window-minutes",
        help="Search window (+/- minutes) around kickoff-Nh to find the closest provider snapshot.",
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
) -> None:
    """Train a baseline model to predict `point_diff`.

    This trains directly from the DB (via `football_team_game_state` + `games`) and uses
    time-based season splits to avoid leakage.
    """

    # Default split: train <= (test_year - 2), val = (test_year - 1), test = test_year.
    if val_year is None and train_end_year is None:
        resolved_val_year = test_year - 1
        resolved_train_end_year = resolved_val_year - 1
    elif val_year is None:
        assert train_end_year is not None
        resolved_train_end_year = train_end_year
        resolved_val_year = train_end_year + 1
    elif train_end_year is None:
        resolved_val_year = val_year
        resolved_train_end_year = val_year - 1
    else:
        resolved_train_end_year = train_end_year
        resolved_val_year = val_year

    if not (resolved_train_end_year < resolved_val_year < test_year):
        raise typer.BadParameter(
            "Require train_end_year < val_year < test_year; "
            f"got train_end_year={resolved_train_end_year}, val_year={resolved_val_year}, test_year={test_year}. "
            "Tip: if you only want to change the test season, set just --test-year and let defaults auto-adjust."
        )

    season_end_year = max(resolved_train_end_year, resolved_val_year, test_year)

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
            train_end_year=resolved_train_end_year,
            val_year=resolved_val_year,
            test_year=test_year,
        )

        if not split.train:
            raise typer.BadParameter("No training rows found for the selected years")
        if not split.val:
            raise typer.BadParameter("No validation rows found for the selected years")
        if not split.test:
            raise typer.BadParameter("No test rows found for the selected years")

        result, model = train_point_diff_ridge(
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

        if compare_to_market:
            book_keys = _split_csv(books_csv)
            market = compare_point_diff_model_vs_spread_market(
                session,
                rows=split.test,
                model=model,
                feature_names=result.feature_names,
                as_of_hours=as_of_hours,
                round_to_hour=round_to_hour,
                window_minutes=odds_window_minutes,
                min_edge_points=min_edge_points,
                book_keys=book_keys,
            )

            if market.games_with_market == 0:
                typer.echo(
                    "No spread snapshots found for test set (did you ingest odds for these seasons?)"
                )
            else:
                roi = market.profit_units / market.bets if market.bets else 0.0
                win_rate = (
                    market.wins / (market.wins + market.losses)
                    if (market.wins + market.losses)
                    else 0.0
                )
                typer.echo(
                    " ".join(
                        [
                            f"market(test): games_with_spread={market.games_with_market}",
                            f"RMSE_model={market.rmse_model_vs_actual:.3f}",
                            f"RMSE_market={market.rmse_market_vs_actual:.3f}",
                        ]
                    )
                )
                typer.echo(
                    " ".join(
                        [
                            f"bets(edge>={min_edge_points:g})={market.bets}",
                            f"W-L-P={market.wins}-{market.losses}-{market.pushes}",
                            f"win_rate={win_rate:.3f}",
                            f"profit_units={market.profit_units:.3f}",
                            f"ROI={roi:.3f}",
                        ]
                    )
                )
