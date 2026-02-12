from __future__ import annotations

from enum import StrEnum
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
    compare_residual_model_vs_spread_market,
    train_point_diff_ridge,
    train_residual_vs_spread_ridge,
)

app = typer.Typer(help="Modeling utilities (dataset export, splits, training scaffolds).")


class FootballPointDiffTarget(StrEnum):
    POINT_DIFF = "point-diff"
    RESIDUAL_VS_SPREAD = "residual-vs-spread"


class SweepSplit(StrEnum):
    VAL = "val"
    TEST = "test"


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
    target: FootballPointDiffTarget = typer.Option(  # noqa: B008
        "point-diff",
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

        book_keys = _split_csv(books_csv)

        resolved_target = (
            target
            if isinstance(target, FootballPointDiffTarget)
            else FootballPointDiffTarget(target)
        )

        # Match the default `vig_price=-110` used inside the comparison helpers.
        # -110 => risk 1.0 to win 0.9091, breakeven win rate is 1 / (1 + win_profit)
        win_profit = 100.0 / 110.0
        breakeven_win_rate = 1.0 / (1.0 + win_profit)

        sweep_thresholds = _split_float_csv(sweep_min_edge_points_csv)

        resolved_sweep_split = (
            sweep_split if isinstance(sweep_split, SweepSplit) else SweepSplit(sweep_split)
        )

        if resolved_target == FootballPointDiffTarget.POINT_DIFF:
            pd_result, pd_model = train_point_diff_ridge(
                train_rows=split.train,
                val_rows=split.val,
                test_rows=split.test,
                alpha=alpha,
            )

            typer.echo(
                " ".join(
                    [
                        f"point_diff ridge alpha={alpha}",
                        f"train={pd_result.train_size}",
                        f"val={pd_result.val_size}",
                        f"test={pd_result.test_size}",
                    ]
                )
            )
            typer.echo(
                " ".join(
                    [
                        f"train: MAE={pd_result.train_metrics.mae:.3f}",
                        f"RMSE={pd_result.train_metrics.rmse:.3f}",
                        f"R2={pd_result.train_metrics.r2:.3f}",
                    ]
                )
            )
            typer.echo(
                " ".join(
                    [
                        f"val:   MAE={pd_result.val_metrics.mae:.3f}",
                        f"RMSE={pd_result.val_metrics.rmse:.3f}",
                        f"R2={pd_result.val_metrics.r2:.3f}",
                    ]
                )
            )
            typer.echo(
                " ".join(
                    [
                        f"test:  MAE={pd_result.test_metrics.mae:.3f}",
                        f"RMSE={pd_result.test_metrics.rmse:.3f}",
                        f"R2={pd_result.test_metrics.r2:.3f}",
                    ]
                )
            )

            if compare_to_market:
                effective_min_edge_points = min_edge_points

                if sweep_thresholds is not None:
                    sweep_rows = split.val if resolved_sweep_split == SweepSplit.VAL else split.test
                    if not sweep_rows:
                        typer.echo(
                            f"Sweep skipped: no rows in split={resolved_sweep_split.value!r}"
                        )
                    else:
                        typer.echo(
                            f"sweep(split={resolved_sweep_split.value}): thresholds={','.join(str(t) for t in sweep_thresholds)}"
                        )

                        pd_best_thr: float | None = None
                        pd_best_roi: float | None = None
                        pd_best_profit: float | None = None

                        for thr in sweep_thresholds:
                            pd_sweep_market = compare_point_diff_model_vs_spread_market(
                                session,
                                rows=sweep_rows,
                                model=pd_model,
                                feature_names=pd_result.feature_names,
                                as_of_hours=as_of_hours,
                                round_to_hour=round_to_hour,
                                window_minutes=odds_window_minutes,
                                min_edge_points=thr,
                                book_keys=book_keys,
                            )
                            roi = (
                                pd_sweep_market.profit_units / pd_sweep_market.bets
                                if pd_sweep_market.bets
                                else 0.0
                            )
                            win_rate = (
                                pd_sweep_market.wins
                                / (pd_sweep_market.wins + pd_sweep_market.losses)
                                if (pd_sweep_market.wins + pd_sweep_market.losses)
                                else 0.0
                            )
                            bet_rate = (
                                pd_sweep_market.bets / pd_sweep_market.games_with_market
                                if pd_sweep_market.games_with_market
                                else 0.0
                            )
                            typer.echo(
                                " ".join(
                                    [
                                        f"thr={thr:g}",
                                        f"bets={pd_sweep_market.bets}",
                                        f"bet_rate={bet_rate:.3f}",
                                        f"W-L-P={pd_sweep_market.wins}-{pd_sweep_market.losses}-{pd_sweep_market.pushes}",
                                        f"win_rate={win_rate:.3f}",
                                        f"ROI={roi:.3f}",
                                        f"profit_units={pd_sweep_market.profit_units:.3f}",
                                    ]
                                )
                            )

                            if pd_sweep_market.bets < sweep_min_bets:
                                continue

                            if pd_best_thr is None:
                                pd_best_thr = thr
                                pd_best_roi = roi
                                pd_best_profit = pd_sweep_market.profit_units
                                continue

                            assert pd_best_roi is not None
                            assert pd_best_profit is not None
                            if (roi > pd_best_roi) or (
                                roi == pd_best_roi and pd_sweep_market.profit_units > pd_best_profit
                            ):
                                pd_best_thr = thr
                                pd_best_roi = roi
                                pd_best_profit = pd_sweep_market.profit_units

                        if pd_best_thr is not None:
                            effective_min_edge_points = pd_best_thr
                            typer.echo(
                                f"sweep(best): min_edge_points={effective_min_edge_points:g} (ROI={pd_best_roi:.3f}, min_bets={sweep_min_bets})"
                            )
                        else:
                            typer.echo(
                                f"sweep(best): no thresholds met min_bets={sweep_min_bets}; using min_edge_points={effective_min_edge_points:g}"
                            )

                pd_market = compare_point_diff_model_vs_spread_market(
                    session,
                    rows=split.test,
                    model=pd_model,
                    feature_names=pd_result.feature_names,
                    as_of_hours=as_of_hours,
                    round_to_hour=round_to_hour,
                    window_minutes=odds_window_minutes,
                    min_edge_points=effective_min_edge_points,
                    book_keys=book_keys,
                )

                if pd_market.games_with_market == 0:
                    typer.echo(
                        "No spread snapshots found for test set (did you ingest odds for these seasons?)"
                    )
                else:
                    roi = pd_market.profit_units / pd_market.bets if pd_market.bets else 0.0
                    win_rate = (
                        pd_market.wins / (pd_market.wins + pd_market.losses)
                        if (pd_market.wins + pd_market.losses)
                        else 0.0
                    )
                    bet_rate = (
                        pd_market.bets / pd_market.games_with_market
                        if pd_market.games_with_market
                        else 0.0
                    )
                    typer.echo(
                        " ".join(
                            [
                                f"market(test): games_with_spread={pd_market.games_with_market}",
                                f"RMSE_model={pd_market.rmse_model_vs_actual:.3f}",
                                f"RMSE_market={pd_market.rmse_market_vs_actual:.3f}",
                            ]
                        )
                    )
                    typer.echo(
                        " ".join(
                            [
                                f"bets(edge>={effective_min_edge_points:g})={pd_market.bets}",
                                f"bet_rate={bet_rate:.3f}",
                                f"W-L-P={pd_market.wins}-{pd_market.losses}-{pd_market.pushes}",
                                f"win_rate={win_rate:.3f}",
                                f"breakeven@-110={breakeven_win_rate:.3f}",
                                f"profit_units={pd_market.profit_units:.3f}",
                                f"ROI={roi:.3f}",
                            ]
                        )
                    )
        else:
            res_result, res_model = train_residual_vs_spread_ridge(
                session,
                train_rows=split.train,
                val_rows=split.val,
                test_rows=split.test,
                alpha=alpha,
                as_of_hours=as_of_hours,
                round_to_hour=round_to_hour,
                window_minutes=odds_window_minutes,
                book_keys=book_keys,
            )

            typer.echo(
                " ".join(
                    [
                        f"residual_vs_spread ridge alpha={alpha}",
                        f"train={res_result.train_size} (skipped_no_market={res_result.train_skipped_no_market})",
                        f"val={res_result.val_size} (skipped_no_market={res_result.val_skipped_no_market})",
                        f"test={res_result.test_size} (skipped_no_market={res_result.test_skipped_no_market})",
                    ]
                )
            )
            typer.echo(
                " ".join(
                    [
                        f"train: MAE={res_result.train_metrics.mae:.3f}",
                        f"RMSE={res_result.train_metrics.rmse:.3f}",
                        f"R2={res_result.train_metrics.r2:.3f}",
                    ]
                )
            )
            typer.echo(
                " ".join(
                    [
                        f"val:   MAE={res_result.val_metrics.mae:.3f}",
                        f"RMSE={res_result.val_metrics.rmse:.3f}",
                        f"R2={res_result.val_metrics.r2:.3f}",
                    ]
                )
            )
            typer.echo(
                " ".join(
                    [
                        f"test:  MAE={res_result.test_metrics.mae:.3f}",
                        f"RMSE={res_result.test_metrics.rmse:.3f}",
                        f"R2={res_result.test_metrics.r2:.3f}",
                    ]
                )
            )

            if compare_to_market:
                effective_min_edge_points = min_edge_points

                if sweep_thresholds is not None:
                    sweep_rows = split.val if resolved_sweep_split == SweepSplit.VAL else split.test
                    if not sweep_rows:
                        typer.echo(
                            f"Sweep skipped: no rows in split={resolved_sweep_split.value!r}"
                        )
                    else:
                        typer.echo(
                            f"sweep(split={resolved_sweep_split.value}): thresholds={','.join(str(t) for t in sweep_thresholds)}"
                        )

                        res_best_thr: float | None = None
                        res_best_roi: float | None = None
                        res_best_profit: float | None = None

                        for thr in sweep_thresholds:
                            res_sweep_market = compare_residual_model_vs_spread_market(
                                session,
                                rows=sweep_rows,
                                model=res_model,
                                feature_names=res_result.feature_names,
                                as_of_hours=as_of_hours,
                                round_to_hour=round_to_hour,
                                window_minutes=odds_window_minutes,
                                min_edge_points=thr,
                                book_keys=book_keys,
                            )
                            roi = (
                                res_sweep_market.profit_units / res_sweep_market.bets
                                if res_sweep_market.bets
                                else 0.0
                            )
                            win_rate = (
                                res_sweep_market.wins
                                / (res_sweep_market.wins + res_sweep_market.losses)
                                if (res_sweep_market.wins + res_sweep_market.losses)
                                else 0.0
                            )
                            bet_rate = (
                                res_sweep_market.bets / res_sweep_market.games_with_market
                                if res_sweep_market.games_with_market
                                else 0.0
                            )
                            typer.echo(
                                " ".join(
                                    [
                                        f"thr={thr:g}",
                                        f"bets={res_sweep_market.bets}",
                                        f"bet_rate={bet_rate:.3f}",
                                        f"W-L-P={res_sweep_market.wins}-{res_sweep_market.losses}-{res_sweep_market.pushes}",
                                        f"win_rate={win_rate:.3f}",
                                        f"ROI={roi:.3f}",
                                        f"profit_units={res_sweep_market.profit_units:.3f}",
                                    ]
                                )
                            )

                            if res_sweep_market.bets < sweep_min_bets:
                                continue

                            if res_best_thr is None:
                                res_best_thr = thr
                                res_best_roi = roi
                                res_best_profit = res_sweep_market.profit_units
                                continue

                            assert res_best_roi is not None
                            assert res_best_profit is not None
                            if (roi > res_best_roi) or (
                                roi == res_best_roi
                                and res_sweep_market.profit_units > res_best_profit
                            ):
                                res_best_thr = thr
                                res_best_roi = roi
                                res_best_profit = res_sweep_market.profit_units

                        if res_best_thr is not None:
                            effective_min_edge_points = res_best_thr
                            typer.echo(
                                f"sweep(best): min_edge_points={effective_min_edge_points:g} (ROI={res_best_roi:.3f}, min_bets={sweep_min_bets})"
                            )
                        else:
                            typer.echo(
                                f"sweep(best): no thresholds met min_bets={sweep_min_bets}; using min_edge_points={effective_min_edge_points:g}"
                            )

                res_market = compare_residual_model_vs_spread_market(
                    session,
                    rows=split.test,
                    model=res_model,
                    feature_names=res_result.feature_names,
                    as_of_hours=as_of_hours,
                    round_to_hour=round_to_hour,
                    window_minutes=odds_window_minutes,
                    min_edge_points=effective_min_edge_points,
                    book_keys=book_keys,
                )

                if res_market.games_with_market == 0:
                    typer.echo(
                        "No spread snapshots found for test set (did you ingest odds for these seasons?)"
                    )
                else:
                    roi = res_market.profit_units / res_market.bets if res_market.bets else 0.0
                    win_rate = (
                        res_market.wins / (res_market.wins + res_market.losses)
                        if (res_market.wins + res_market.losses)
                        else 0.0
                    )
                    bet_rate = (
                        res_market.bets / res_market.games_with_market
                        if res_market.games_with_market
                        else 0.0
                    )
                    typer.echo(
                        " ".join(
                            [
                                f"market(test): games_with_spread={res_market.games_with_market}",
                                f"RMSE_residual={res_market.rmse_residual:.3f}",
                                f"RMSE_pointdiff(market+model)={res_market.rmse_pointdiff_from_market_plus_model:.3f}",
                                f"RMSE_market={res_market.rmse_market_vs_actual:.3f}",
                            ]
                        )
                    )
                    typer.echo(
                        " ".join(
                            [
                                f"bets(edge>={effective_min_edge_points:g})={res_market.bets}",
                                f"bet_rate={bet_rate:.3f}",
                                f"W-L-P={res_market.wins}-{res_market.losses}-{res_market.pushes}",
                                f"win_rate={win_rate:.3f}",
                                f"breakeven@-110={breakeven_win_rate:.3f}",
                                f"profit_units={res_market.profit_units:.3f}",
                                f"ROI={roi:.3f}",
                            ]
                        )
                    )
