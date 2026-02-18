from __future__ import annotations

from odds_value.modeling.football.commands_types import (
    EchoFn,
    FootballPointDiffTarget,
    SessionScope,
    SweepSplit,
)
from odds_value.modeling.football.train_point_diff_single_year import train_single_year_workflow
from odds_value.modeling.football.train_point_diff_walk_forward import train_walk_forward_workflow


def train_football_point_diff(
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
    walk_forward: bool,
    walk_forward_start_test_year: int | None,
    walk_forward_end_test_year: int | None,
    walk_forward_val_window_years: int,
    odds_window_minutes: int,
    min_market_books: int,
    round_to_hour: bool,
    book_keys: list[str] | None,
    include_market_features: bool,
    include_elo_features: bool,
) -> None:
    resolved_target = (
        target if isinstance(target, FootballPointDiffTarget) else FootballPointDiffTarget(target)
    )
    resolved_sweep_split = (
        sweep_split if isinstance(sweep_split, SweepSplit) else SweepSplit(sweep_split)
    )

    if walk_forward:
        train_walk_forward_workflow(
            session_scope=session_scope,
            echo=echo,
            league_key=league_key,
            season_start_year=season_start_year,
            alpha=alpha,
            target=resolved_target,
            compare_to_market=compare_to_market,
            as_of_hours=as_of_hours,
            min_edge_points=min_edge_points,
            sweep_thresholds=sweep_thresholds,
            sweep_min_bets=sweep_min_bets,
            sweep_split=resolved_sweep_split,
            walk_forward_start_test_year=walk_forward_start_test_year,
            walk_forward_end_test_year=walk_forward_end_test_year,
            walk_forward_val_window_years=walk_forward_val_window_years,
            odds_window_minutes=odds_window_minutes,
            min_market_books=min_market_books,
            round_to_hour=round_to_hour,
            book_keys=book_keys,
            include_market_features=include_market_features,
            include_elo_features=include_elo_features,
            train_end_year=train_end_year,
            val_year=val_year,
        )
        return

    train_single_year_workflow(
        session_scope=session_scope,
        echo=echo,
        league_key=league_key,
        season_start_year=season_start_year,
        train_end_year=train_end_year,
        val_year=val_year,
        test_year=test_year,
        alpha=alpha,
        target=resolved_target,
        compare_to_market=compare_to_market,
        as_of_hours=as_of_hours,
        min_edge_points=min_edge_points,
        sweep_thresholds=sweep_thresholds,
        sweep_min_bets=sweep_min_bets,
        sweep_split=resolved_sweep_split,
        odds_window_minutes=odds_window_minutes,
        min_market_books=min_market_books,
        round_to_hour=round_to_hour,
        book_keys=book_keys,
        include_market_features=include_market_features,
        include_elo_features=include_elo_features,
    )
