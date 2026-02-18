from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from odds_value.modeling.football.commands_types import EchoFn


@dataclass(frozen=True)
class ThresholdChoice:
    threshold: float
    roi: float
    profit_units: float


def roi(*, bets: int, profit_units: float) -> float:
    return profit_units / bets if bets else 0.0


def win_rate(*, wins: int, losses: int) -> float:
    return wins / (wins + losses) if (wins + losses) else 0.0


def bet_rate(*, bets: int, games_with_market: int) -> float:
    return bets / games_with_market if games_with_market else 0.0


def breakeven_win_rate(*, bets: int, sum_win_profit_units: float) -> float:
    # If you stake 1 unit each bet and win-profit is U, then breakeven p is:
    # p * U - (1 - p) * 1 = 0 => p = 1 / (1 + U)
    # Aggregated over varying prices, use total win-profit units.
    return float(bets) / (float(bets) + float(sum_win_profit_units)) if bets else 0.0


@dataclass(frozen=True)
class SweepCandidate:
    bets: int
    profit_units: float


MarketEvalFn = Callable[[float], SweepCandidate]


def choose_best_threshold(
    *,
    thresholds: list[float],
    min_bets: int,
    eval_threshold: MarketEvalFn,
) -> ThresholdChoice | None:
    best: ThresholdChoice | None = None

    for thr in thresholds:
        cand = eval_threshold(thr)
        if cand.bets < min_bets:
            continue

        cand_roi = roi(bets=cand.bets, profit_units=cand.profit_units)
        if best is None:
            best = ThresholdChoice(threshold=thr, roi=cand_roi, profit_units=cand.profit_units)
            continue

        if (cand_roi > best.roi) or (
            cand_roi == best.roi and cand.profit_units > best.profit_units
        ):
            best = ThresholdChoice(threshold=thr, roi=cand_roi, profit_units=cand.profit_units)

    return best


def echo_sweep_header(
    *, echo: EchoFn, split_name: str, thresholds: list[float], min_bets: int
) -> None:
    echo(
        f"sweep(split={split_name}): thresholds={','.join(str(t) for t in thresholds)} (min_bets={min_bets})"
    )
