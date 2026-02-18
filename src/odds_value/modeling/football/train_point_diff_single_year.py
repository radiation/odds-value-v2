from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.modeling.football.commands_types import (
    EchoFn,
    FootballPointDiffTarget,
    SessionScope,
    SweepSplit,
)
from odds_value.modeling.football.dataset import build_football_game_dataset
from odds_value.modeling.football.splits import SeasonSplit, split_by_season_year
from odds_value.modeling.football.train_point_diff import (
    RegressionMetrics,
    compare_point_diff_model_vs_spread_market,
    compare_residual_model_vs_spread_market,
    train_point_diff_ridge,
    train_residual_vs_spread_ridge,
)
from odds_value.modeling.football.train_point_diff_market import (
    SweepCandidate,
    bet_rate,
    choose_best_threshold,
    echo_sweep_header,
    roi,
    win_rate,
)


def train_single_year_workflow(
    *,
    session_scope: SessionScope,
    echo: EchoFn,
    league_key: str,
    season_start_year: int,
    train_end_year: int | None,
    val_year: int | None,
    test_year: int,
    alpha: float,
    target: FootballPointDiffTarget,
    compare_to_market: bool,
    as_of_hours: int,
    min_edge_points: float,
    sweep_thresholds: list[float] | None,
    sweep_min_bets: int,
    sweep_split: SweepSplit,
    odds_window_minutes: int,
    min_market_books: int,
    round_to_hour: bool,
    book_keys: list[str] | None,
    include_market_features: bool,
    include_elo_features: bool,
) -> None:
    resolved_train_end_year, resolved_val_year = _resolve_split_years(
        train_end_year=train_end_year,
        val_year=val_year,
        test_year=test_year,
    )

    season_end_year = max(resolved_train_end_year, resolved_val_year, test_year)

    with session_scope() as session:
        rows = build_football_game_dataset(
            session,
            league_key=league_key,
            season_start_year=season_start_year,
            season_end_year=season_end_year,
            require_final=True,
            include_elo_features=include_elo_features,
        )

        if include_elo_features:
            has_elo = any("elo_diff_pre" in r.features for r in rows)
            if not has_elo:
                echo(
                    "warning: --include-elo-features was set but no Elo feature columns were found in the dataset"
                )

        split = split_by_season_year(
            rows,
            train_end_year=resolved_train_end_year,
            val_year=resolved_val_year,
            test_year=test_year,
        )

        if not split.train:
            raise ValueError("No training rows found for the selected years")
        if not split.val:
            raise ValueError("No validation rows found for the selected years")
        if not split.test:
            raise ValueError("No test rows found for the selected years")

        if target == FootballPointDiffTarget.POINT_DIFF:
            _run_point_diff(
                session=session,
                echo=echo,
                split=split,
                alpha=alpha,
                compare_to_market=compare_to_market,
                as_of_hours=as_of_hours,
                min_edge_points=min_edge_points,
                sweep_thresholds=sweep_thresholds,
                sweep_min_bets=sweep_min_bets,
                sweep_split=sweep_split,
                odds_window_minutes=odds_window_minutes,
                min_market_books=min_market_books,
                round_to_hour=round_to_hour,
                book_keys=book_keys,
            )
        else:
            _run_residual(
                session=session,
                echo=echo,
                split=split,
                alpha=alpha,
                compare_to_market=compare_to_market,
                as_of_hours=as_of_hours,
                min_edge_points=min_edge_points,
                sweep_thresholds=sweep_thresholds,
                sweep_min_bets=sweep_min_bets,
                sweep_split=sweep_split,
                odds_window_minutes=odds_window_minutes,
                min_market_books=min_market_books,
                round_to_hour=round_to_hour,
                book_keys=book_keys,
                include_market_features=include_market_features,
            )


def _resolve_split_years(
    *, train_end_year: int | None, val_year: int | None, test_year: int
) -> tuple[int, int]:
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
        raise ValueError(
            "Require train_end_year < val_year < test_year; "
            f"got train_end_year={resolved_train_end_year}, val_year={resolved_val_year}, test_year={test_year}. "
            "Tip: if you only want to change the test season, set just --test-year and let defaults auto-adjust."
        )

    return resolved_train_end_year, resolved_val_year


def _run_point_diff(
    *,
    session: Session,
    echo: EchoFn,
    split: SeasonSplit,
    alpha: float,
    compare_to_market: bool,
    as_of_hours: int,
    min_edge_points: float,
    sweep_thresholds: list[float] | None,
    sweep_min_bets: int,
    sweep_split: SweepSplit,
    odds_window_minutes: int,
    min_market_books: int,
    round_to_hour: bool,
    book_keys: list[str] | None,
) -> None:
    pd_result, pd_model = train_point_diff_ridge(
        train_rows=split.train,
        val_rows=split.val,
        test_rows=split.test,
        alpha=alpha,
    )

    echo(
        " ".join(
            [
                f"point_diff ridge alpha={alpha}",
                f"train={pd_result.train_size}",
                f"val={pd_result.val_size}",
                f"test={pd_result.test_size}",
            ]
        )
    )
    _echo_regression_metrics(
        echo=echo,
        train=pd_result.train_metrics,
        val=pd_result.val_metrics,
        test=pd_result.test_metrics,
    )

    if not compare_to_market:
        return

    effective_min_edge_points = min_edge_points
    if sweep_thresholds is not None:
        sweep_rows = split.val if sweep_split == SweepSplit.VAL else split.test
        if sweep_rows:
            echo_sweep_header(
                echo=echo,
                split_name=sweep_split.value,
                thresholds=sweep_thresholds,
                min_bets=sweep_min_bets,
            )

            def _eval_thr(thr: float) -> SweepCandidate:
                m = compare_point_diff_model_vs_spread_market(
                    session,
                    rows=sweep_rows,
                    model=pd_model,
                    feature_names=pd_result.feature_names,
                    as_of_hours=as_of_hours,
                    round_to_hour=round_to_hour,
                    window_minutes=odds_window_minutes,
                    min_edge_points=thr,
                    min_market_books=min_market_books,
                    book_keys=book_keys,
                )
                _echo_threshold_row(
                    echo=echo,
                    thr=thr,
                    bets=m.bets,
                    games_with_market=m.games_with_market,
                    wins=m.wins,
                    losses=m.losses,
                    pushes=m.pushes,
                    profit_units=m.profit_units,
                )
                return SweepCandidate(bets=m.bets, profit_units=m.profit_units)

            best = choose_best_threshold(
                thresholds=sweep_thresholds,
                min_bets=sweep_min_bets,
                eval_threshold=_eval_thr,
            )
            if best is not None:
                effective_min_edge_points = best.threshold
                echo(
                    f"sweep(best): min_edge_points={effective_min_edge_points:g} (ROI={best.roi:.3f}, min_bets={sweep_min_bets})"
                )
            else:
                echo(
                    f"sweep(best): no thresholds met min_bets={sweep_min_bets}; using min_edge_points={effective_min_edge_points:g}"
                )
        else:
            echo(f"Sweep skipped: no rows in split={sweep_split.value!r}")

    pd_market = compare_point_diff_model_vs_spread_market(
        session,
        rows=split.test,
        model=pd_model,
        feature_names=pd_result.feature_names,
        as_of_hours=as_of_hours,
        round_to_hour=round_to_hour,
        window_minutes=odds_window_minutes,
        min_edge_points=effective_min_edge_points,
        min_market_books=min_market_books,
        book_keys=book_keys,
    )

    if pd_market.games_with_market == 0:
        echo("No spread snapshots found for test set (did you ingest odds for these seasons?)")
        return

    echo(
        " ".join(
            [
                f"market(test): games_with_spread={pd_market.games_with_market}",
                f"RMSE_model={pd_market.rmse_model_vs_actual:.3f}",
                f"RMSE_market={pd_market.rmse_market_vs_actual:.3f}",
            ]
        )
    )

    roi_ = roi(bets=pd_market.bets, profit_units=pd_market.profit_units)
    win_rate_ = win_rate(wins=pd_market.wins, losses=pd_market.losses)
    bet_rate_ = bet_rate(bets=pd_market.bets, games_with_market=pd_market.games_with_market)

    echo(
        " ".join(
            [
                f"bets(edge>={effective_min_edge_points:g})={pd_market.bets}",
                f"bet_rate={bet_rate_:.3f}",
                f"W-L-P={pd_market.wins}-{pd_market.losses}-{pd_market.pushes}",
                f"win_rate={win_rate_:.3f}",
                f"breakeven={pd_market.breakeven_win_rate:.3f}",
                f"profit_units={pd_market.profit_units:.3f}",
                f"ROI={roi_:.3f}",
            ]
        )
    )


def _run_residual(
    *,
    session: Session,
    echo: EchoFn,
    split: SeasonSplit,
    alpha: float,
    compare_to_market: bool,
    as_of_hours: int,
    min_edge_points: float,
    sweep_thresholds: list[float] | None,
    sweep_min_bets: int,
    sweep_split: SweepSplit,
    odds_window_minutes: int,
    min_market_books: int,
    round_to_hour: bool,
    book_keys: list[str] | None,
    include_market_features: bool,
) -> None:
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
        include_market_features=include_market_features,
    )

    echo(
        " ".join(
            [
                f"residual_vs_spread ridge alpha={alpha}",
                f"train={res_result.train_size} (skipped_no_market={res_result.train_skipped_no_market})",
                f"val={res_result.val_size} (skipped_no_market={res_result.val_skipped_no_market})",
                f"test={res_result.test_size} (skipped_no_market={res_result.test_skipped_no_market})",
            ]
        )
    )
    _echo_regression_metrics(
        echo=echo,
        train=res_result.train_metrics,
        val=res_result.val_metrics,
        test=res_result.test_metrics,
    )

    if not compare_to_market:
        return

    effective_min_edge_points = min_edge_points
    if sweep_thresholds is not None:
        sweep_rows = split.val if sweep_split == SweepSplit.VAL else split.test
        if sweep_rows:
            echo_sweep_header(
                echo=echo,
                split_name=sweep_split.value,
                thresholds=sweep_thresholds,
                min_bets=sweep_min_bets,
            )

            def _eval_thr(thr: float) -> SweepCandidate:
                m = compare_residual_model_vs_spread_market(
                    session,
                    rows=sweep_rows,
                    model=res_model,
                    feature_names=res_result.feature_names,
                    as_of_hours=as_of_hours,
                    round_to_hour=round_to_hour,
                    window_minutes=odds_window_minutes,
                    min_edge_points=thr,
                    min_market_books=min_market_books,
                    book_keys=book_keys,
                    include_market_features=include_market_features,
                )
                _echo_threshold_row(
                    echo=echo,
                    thr=thr,
                    bets=m.bets,
                    games_with_market=m.games_with_market,
                    wins=m.wins,
                    losses=m.losses,
                    pushes=m.pushes,
                    profit_units=m.profit_units,
                )
                return SweepCandidate(bets=m.bets, profit_units=m.profit_units)

            best = choose_best_threshold(
                thresholds=sweep_thresholds,
                min_bets=sweep_min_bets,
                eval_threshold=_eval_thr,
            )
            if best is not None:
                effective_min_edge_points = best.threshold
                echo(
                    f"sweep(best): min_edge_points={effective_min_edge_points:g} (ROI={best.roi:.3f}, min_bets={sweep_min_bets})"
                )
            else:
                echo(
                    f"sweep(best): no thresholds met min_bets={sweep_min_bets}; using min_edge_points={effective_min_edge_points:g}"
                )
        else:
            echo(f"Sweep skipped: no rows in split={sweep_split.value!r}")

    res_market = compare_residual_model_vs_spread_market(
        session,
        rows=split.test,
        model=res_model,
        feature_names=res_result.feature_names,
        as_of_hours=as_of_hours,
        round_to_hour=round_to_hour,
        window_minutes=odds_window_minutes,
        min_edge_points=effective_min_edge_points,
        min_market_books=min_market_books,
        book_keys=book_keys,
        include_market_features=include_market_features,
    )

    if res_market.games_with_market == 0:
        echo("No spread snapshots found for test set (did you ingest odds for these seasons?)")
        return

    echo(
        " ".join(
            [
                f"market(test): games_with_spread={res_market.games_with_market}",
                f"RMSE_residual={res_market.rmse_residual:.3f}",
                f"RMSE_pointdiff(market+model)={res_market.rmse_pointdiff_from_market_plus_model:.3f}",
                f"RMSE_market={res_market.rmse_market_vs_actual:.3f}",
            ]
        )
    )

    roi_ = roi(bets=res_market.bets, profit_units=res_market.profit_units)
    win_rate_ = win_rate(wins=res_market.wins, losses=res_market.losses)
    bet_rate_ = bet_rate(bets=res_market.bets, games_with_market=res_market.games_with_market)

    echo(
        " ".join(
            [
                f"bets(edge>={effective_min_edge_points:g})={res_market.bets}",
                f"bet_rate={bet_rate_:.3f}",
                f"W-L-P={res_market.wins}-{res_market.losses}-{res_market.pushes}",
                f"win_rate={win_rate_:.3f}",
                f"breakeven={res_market.breakeven_win_rate:.3f}",
                f"profit_units={res_market.profit_units:.3f}",
                f"ROI={roi_:.3f}",
            ]
        )
    )


def _echo_regression_metrics(
    *,
    echo: EchoFn,
    train: RegressionMetrics,
    val: RegressionMetrics,
    test: RegressionMetrics,
) -> None:
    echo(
        " ".join(
            [
                f"train: MAE={train.mae:.3f}",
                f"RMSE={train.rmse:.3f}",
                f"R2={train.r2:.3f}",
            ]
        )
    )
    echo(
        " ".join(
            [
                f"val:   MAE={val.mae:.3f}",
                f"RMSE={val.rmse:.3f}",
                f"R2={val.r2:.3f}",
            ]
        )
    )
    echo(
        " ".join(
            [
                f"test:  MAE={test.mae:.3f}",
                f"RMSE={test.rmse:.3f}",
                f"R2={test.r2:.3f}",
            ]
        )
    )


def _echo_threshold_row(
    *,
    echo: EchoFn,
    thr: float,
    bets: int,
    games_with_market: int,
    wins: int,
    losses: int,
    pushes: int,
    profit_units: float,
) -> None:
    roi_ = roi(bets=bets, profit_units=profit_units)
    win_rate_ = win_rate(wins=wins, losses=losses)
    bet_rate_ = bet_rate(bets=bets, games_with_market=games_with_market)
    echo(
        " ".join(
            [
                f"thr={thr:g}",
                f"bets={bets}",
                f"bet_rate={bet_rate_:.3f}",
                f"W-L-P={wins}-{losses}-{pushes}",
                f"win_rate={win_rate_:.3f}",
                f"ROI={roi_:.3f}",
                f"profit_units={profit_units:.3f}",
            ]
        )
    )
