from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from odds_value.modeling.football.commands_types import (
    EchoFn,
    FootballPointDiffTarget,
    SessionScope,
    SweepSplit,
)
from odds_value.modeling.football.dataset import FootballGameDatasetRow, build_football_game_dataset
from odds_value.modeling.football.splits import SeasonSplit, split_by_season_year_window
from odds_value.modeling.football.train_point_diff import (
    ResidualMarketComparisonResult,
    SpreadMarketComparisonResult,
    compare_point_diff_model_vs_spread_market,
    compare_residual_model_vs_spread_market,
    train_point_diff_ridge,
    train_residual_vs_spread_ridge,
)
from odds_value.modeling.football.train_point_diff_market import (
    SweepCandidate,
    bet_rate,
    breakeven_win_rate,
    choose_best_threshold,
    roi,
    win_rate,
)


@dataclass
class WalkForwardTotals:
    bets: int = 0
    profit_units: float = 0.0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    sum_win_profit_units: float = 0.0
    games_with_market: int = 0


class _SkipWalkForwardYear(Exception):
    pass


def train_walk_forward_workflow(
    *,
    session_scope: SessionScope,
    echo: EchoFn,
    league_key: str,
    season_start_year: int,
    alpha: float,
    target: FootballPointDiffTarget,
    compare_to_market: bool,
    as_of_hours: int,
    min_edge_points: float,
    sweep_thresholds: list[float] | None,
    sweep_min_bets: int,
    sweep_split: SweepSplit,
    walk_forward_start_test_year: int | None,
    walk_forward_end_test_year: int | None,
    walk_forward_val_window_years: int,
    odds_window_minutes: int,
    min_market_books: int,
    round_to_hour: bool,
    book_keys: list[str] | None,
    include_market_features: bool,
    include_elo_features: bool,
    train_end_year: int | None,
    val_year: int | None,
) -> None:
    _validate_walk_forward_args(
        compare_to_market=compare_to_market,
        sweep_split=sweep_split,
        season_start_year=season_start_year,
        walk_forward_start_test_year=walk_forward_start_test_year,
        walk_forward_end_test_year=walk_forward_end_test_year,
        train_end_year=train_end_year,
        val_year=val_year,
    )

    assert walk_forward_start_test_year is not None
    assert walk_forward_end_test_year is not None

    start_test_year = walk_forward_start_test_year
    end_test_year = walk_forward_end_test_year
    season_end_year = end_test_year

    with session_scope() as session:
        rows = build_football_game_dataset(
            session,
            league_key=league_key,
            season_start_year=season_start_year,
            season_end_year=season_end_year,
            require_final=True,
            include_elo_features=include_elo_features,
        )

        echo(
            " ".join(
                [
                    f"walk_forward target={target.value}",
                    f"years={start_test_year}-{end_test_year}",
                    f"season_start_year={season_start_year}",
                    f"books={','.join(book_keys) if book_keys else 'ALL'}",
                    f"min_market_books={min_market_books}",
                    f"val_window_years={walk_forward_val_window_years}",
                    f"include_market_features={int(include_market_features)}",
                    f"include_elo_features={int(include_elo_features)}",
                ]
            )
        )

        earliest_supported_test_year = season_start_year + walk_forward_val_window_years + 1
        if start_test_year < earliest_supported_test_year:
            echo(
                "warning: "
                + " ".join(
                    [
                        f"start_test_year={start_test_year} is earlier than",
                        f"season_start_year+val_window_years+1={earliest_supported_test_year};",
                        "early test years may be skipped due to no market-labeled training rows.",
                    ]
                )
            )

        if sweep_thresholds is None:
            echo(
                f"walk_forward: no sweep thresholds provided; using min_edge_points={min_edge_points:g}"
            )
        else:
            echo(
                f"walk_forward: sweep thresholds={','.join(str(t) for t in sweep_thresholds)} (min_bets={sweep_min_bets})"
            )

        totals = WalkForwardTotals()

        for wf_test_year in range(start_test_year, end_test_year + 1):
            try:
                outcome = _eval_walk_forward_year(
                    session=session,
                    echo=echo,
                    rows=rows,
                    season_start_year=season_start_year,
                    wf_test_year=wf_test_year,
                    walk_forward_val_window_years=walk_forward_val_window_years,
                    alpha=alpha,
                    target=target,
                    as_of_hours=as_of_hours,
                    min_edge_points=min_edge_points,
                    sweep_thresholds=sweep_thresholds,
                    sweep_min_bets=sweep_min_bets,
                    odds_window_minutes=odds_window_minutes,
                    min_market_books=min_market_books,
                    round_to_hour=round_to_hour,
                    book_keys=book_keys,
                    include_market_features=include_market_features,
                )
            except _SkipWalkForwardYear as e:
                echo(f"wf(test_year={wf_test_year}): skipped {e}")
                continue

            _echo_year_outcome(
                echo=echo, wf_test_year=wf_test_year, thr=outcome.thr, market=outcome.market
            )
            _accumulate_totals(totals=totals, market=outcome.market)

        _echo_totals(echo=echo, totals=totals)


@dataclass(frozen=True)
class _YearOutcome:
    thr: float
    market: SpreadMarketComparisonResult | ResidualMarketComparisonResult


def _eval_walk_forward_year(
    *,
    session: Session,
    echo: EchoFn,
    rows: list[FootballGameDatasetRow],
    season_start_year: int,
    wf_test_year: int,
    walk_forward_val_window_years: int,
    alpha: float,
    target: FootballPointDiffTarget,
    as_of_hours: int,
    min_edge_points: float,
    sweep_thresholds: list[float] | None,
    sweep_min_bets: int,
    odds_window_minutes: int,
    min_market_books: int,
    round_to_hour: bool,
    book_keys: list[str] | None,
    include_market_features: bool,
) -> _YearOutcome:
    wf_val_end_year = wf_test_year - 1
    wf_val_start_year = wf_test_year - walk_forward_val_window_years
    wf_train_end_year = wf_val_start_year - 1

    if wf_train_end_year < season_start_year:
        raise _SkipWalkForwardYear(
            f"(train_end_year={wf_train_end_year} < season_start_year={season_start_year})"
        )

    split = split_by_season_year_window(
        rows,
        train_end_year=wf_train_end_year,
        val_start_year=wf_val_start_year,
        val_end_year=wf_val_end_year,
        test_year=wf_test_year,
    )

    if not split.train or not split.val or not split.test:
        raise _SkipWalkForwardYear(
            f"(train={len(split.train)} val={len(split.val)} test={len(split.test)})"
        )

    if target == FootballPointDiffTarget.POINT_DIFF:
        return _eval_point_diff_year(
            session=session,
            split=split,
            alpha=alpha,
            as_of_hours=as_of_hours,
            min_edge_points=min_edge_points,
            sweep_thresholds=sweep_thresholds,
            sweep_min_bets=sweep_min_bets,
            odds_window_minutes=odds_window_minutes,
            min_market_books=min_market_books,
            round_to_hour=round_to_hour,
            book_keys=book_keys,
        )

    return _eval_residual_year(
        session=session,
        echo=echo,
        split=split,
        alpha=alpha,
        as_of_hours=as_of_hours,
        min_edge_points=min_edge_points,
        sweep_thresholds=sweep_thresholds,
        sweep_min_bets=sweep_min_bets,
        odds_window_minutes=odds_window_minutes,
        min_market_books=min_market_books,
        round_to_hour=round_to_hour,
        book_keys=book_keys,
        include_market_features=include_market_features,
    )


def _eval_point_diff_year(
    *,
    session: Session,
    split: SeasonSplit,
    alpha: float,
    as_of_hours: int,
    min_edge_points: float,
    sweep_thresholds: list[float] | None,
    sweep_min_bets: int,
    odds_window_minutes: int,
    min_market_books: int,
    round_to_hour: bool,
    book_keys: list[str] | None,
) -> _YearOutcome:
    pd_result, pd_model = train_point_diff_ridge(
        train_rows=split.train,
        val_rows=split.val,
        test_rows=split.test,
        alpha=alpha,
    )

    chosen_thr = min_edge_points
    if sweep_thresholds is not None:

        def _eval_thr(thr: float) -> SweepCandidate:
            m = compare_point_diff_model_vs_spread_market(
                session,
                rows=split.val,
                model=pd_model,
                feature_names=pd_result.feature_names,
                as_of_hours=as_of_hours,
                round_to_hour=round_to_hour,
                window_minutes=odds_window_minutes,
                min_edge_points=thr,
                min_market_books=min_market_books,
                book_keys=book_keys,
            )
            return SweepCandidate(bets=m.bets, profit_units=m.profit_units)

        best = choose_best_threshold(
            thresholds=sweep_thresholds,
            min_bets=sweep_min_bets,
            eval_threshold=_eval_thr,
        )
        if best is not None:
            chosen_thr = best.threshold

    pd_test_market = compare_point_diff_model_vs_spread_market(
        session,
        rows=split.test,
        model=pd_model,
        feature_names=pd_result.feature_names,
        as_of_hours=as_of_hours,
        round_to_hour=round_to_hour,
        window_minutes=odds_window_minutes,
        min_edge_points=chosen_thr,
        min_market_books=min_market_books,
        book_keys=book_keys,
    )

    return _YearOutcome(thr=chosen_thr, market=pd_test_market)


def _eval_residual_year(
    *,
    session: Session,
    echo: EchoFn,
    split: SeasonSplit,
    alpha: float,
    as_of_hours: int,
    min_edge_points: float,
    sweep_thresholds: list[float] | None,
    sweep_min_bets: int,
    odds_window_minutes: int,
    min_market_books: int,
    round_to_hour: bool,
    book_keys: list[str] | None,
    include_market_features: bool,
) -> _YearOutcome:
    try:
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
    except ValueError as e:
        if str(e) == "No training rows have market spreads available":
            raise _SkipWalkForwardYear(
                "(no training rows have market spreads available; try reducing --walk-forward-val-window-years or raising --season-start-year)"
            ) from e
        raise

    chosen_thr = min_edge_points
    if sweep_thresholds is not None:

        def _eval_thr(thr: float) -> SweepCandidate:
            m = compare_residual_model_vs_spread_market(
                session,
                rows=split.val,
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
            return SweepCandidate(bets=m.bets, profit_units=m.profit_units)

        best = choose_best_threshold(
            thresholds=sweep_thresholds,
            min_bets=sweep_min_bets,
            eval_threshold=_eval_thr,
        )
        if best is not None:
            chosen_thr = best.threshold

    res_test_market = compare_residual_model_vs_spread_market(
        session,
        rows=split.test,
        model=res_model,
        feature_names=res_result.feature_names,
        as_of_hours=as_of_hours,
        round_to_hour=round_to_hour,
        window_minutes=odds_window_minutes,
        min_edge_points=chosen_thr,
        min_market_books=min_market_books,
        book_keys=book_keys,
        include_market_features=include_market_features,
    )

    return _YearOutcome(thr=chosen_thr, market=res_test_market)


def _echo_year_outcome(
    *,
    echo: EchoFn,
    wf_test_year: int,
    thr: float,
    market: SpreadMarketComparisonResult | ResidualMarketComparisonResult,
) -> None:
    roi_ = roi(bets=market.bets, profit_units=market.profit_units)
    win_rate_ = win_rate(wins=market.wins, losses=market.losses)
    bet_rate_ = bet_rate(bets=market.bets, games_with_market=market.games_with_market)

    echo(
        " ".join(
            [
                f"wf(test_year={wf_test_year})",
                f"thr={thr:g}",
                f"games_with_spread={market.games_with_market}",
                f"bets={market.bets}",
                f"bet_rate={bet_rate_:.3f}",
                f"W-L-P={market.wins}-{market.losses}-{market.pushes}",
                f"win_rate={win_rate_:.3f}",
                f"breakeven={market.breakeven_win_rate:.3f}",
                f"ROI={roi_:.3f}",
                f"profit_units={market.profit_units:.3f}",
            ]
        )
    )


def _accumulate_totals(
    *,
    totals: WalkForwardTotals,
    market: SpreadMarketComparisonResult | ResidualMarketComparisonResult,
) -> None:
    totals.bets += market.bets
    totals.profit_units += market.profit_units
    totals.wins += market.wins
    totals.losses += market.losses
    totals.pushes += market.pushes
    totals.sum_win_profit_units += market.sum_win_profit_units
    totals.games_with_market += market.games_with_market


def _echo_totals(*, echo: EchoFn, totals: WalkForwardTotals) -> None:
    overall_roi = roi(bets=totals.bets, profit_units=totals.profit_units)
    overall_win_rate = win_rate(wins=totals.wins, losses=totals.losses)
    overall_breakeven = breakeven_win_rate(
        bets=totals.bets, sum_win_profit_units=totals.sum_win_profit_units
    )
    overall_bet_rate = bet_rate(bets=totals.bets, games_with_market=totals.games_with_market)

    echo(
        " ".join(
            [
                "wf(total):",
                f"games_with_spread={totals.games_with_market}",
                f"bets={totals.bets}",
                f"bet_rate={overall_bet_rate:.3f}",
                f"W-L-P={totals.wins}-{totals.losses}-{totals.pushes}",
                f"win_rate={overall_win_rate:.3f}",
                f"breakeven={overall_breakeven:.3f}",
                f"profit_units={totals.profit_units:.3f}",
                f"ROI={overall_roi:.3f}",
            ]
        )
    )


def _validate_walk_forward_args(
    *,
    compare_to_market: bool,
    sweep_split: SweepSplit,
    season_start_year: int,
    walk_forward_start_test_year: int | None,
    walk_forward_end_test_year: int | None,
    train_end_year: int | None,
    val_year: int | None,
) -> None:
    if not compare_to_market:
        raise ValueError("--walk-forward requires --compare-to-market")
    if sweep_split != SweepSplit.VAL:
        raise ValueError("--walk-forward requires --sweep-split val (to avoid leakage)")
    if train_end_year is not None or val_year is not None:
        raise ValueError(
            "--walk-forward uses rolling defaults; do not pass --train-end-year/--val-year"
        )
    if walk_forward_start_test_year is None or walk_forward_end_test_year is None:
        raise ValueError(
            "--walk-forward requires --walk-forward-start-test-year and --walk-forward-end-test-year"
        )
    if walk_forward_start_test_year > walk_forward_end_test_year:
        raise ValueError("walk-forward start year must be <= end year")
    if walk_forward_start_test_year < season_start_year:
        raise ValueError("walk-forward start test year must be >= --season-start-year")
