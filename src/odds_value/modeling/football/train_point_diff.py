from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median

import numpy as np
from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from odds_value.db.enums import MarketTypeEnum, SideTypeEnum
from odds_value.db.models.odds.book import Book
from odds_value.db.models.odds.odds_snapshot import OddsSnapshot
from odds_value.modeling.football.dataset import FootballGameDatasetRow


@dataclass(frozen=True)
class RegressionMetrics:
    mae: float
    rmse: float
    r2: float


@dataclass(frozen=True)
class PointDiffTrainResult:
    feature_names: list[str]
    train_size: int
    val_size: int
    test_size: int
    train_metrics: RegressionMetrics
    val_metrics: RegressionMetrics
    test_metrics: RegressionMetrics


@dataclass(frozen=True)
class SpreadMarketComparisonResult:
    games_with_market: int
    rmse_model_vs_actual: float
    rmse_market_vs_actual: float
    bets: int
    wins: int
    losses: int
    pushes: int
    profit_units: float


def _to_xy(
    rows: list[FootballGameDatasetRow], *, feature_names: list[str]
) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[r.features.get(f, 0.0) for f in feature_names] for r in rows], dtype=float)
    y = np.array([r.point_diff for r in rows], dtype=float)
    return x, y


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> RegressionMetrics:
    mse = float(mean_squared_error(y_true, y_pred))
    return RegressionMetrics(
        mae=float(mean_absolute_error(y_true, y_pred)),
        rmse=float(np.sqrt(mse)),
        r2=float(r2_score(y_true, y_pred)),
    )


def train_point_diff_ridge(
    *,
    train_rows: list[FootballGameDatasetRow],
    val_rows: list[FootballGameDatasetRow],
    test_rows: list[FootballGameDatasetRow],
    alpha: float = 1.0,
) -> tuple[PointDiffTrainResult, Pipeline]:
    """Train a simple Ridge regression baseline for `point_diff`.

    This is intentionally basic (fast + stable). It gives you a first-pass
    expected margin you can compare to a spread.
    """

    feature_names = sorted({k for r in train_rows for k in r.features})
    if not feature_names:
        raise ValueError("No feature columns found in training rows")

    x_train, y_train = _to_xy(train_rows, feature_names=feature_names)
    x_val, y_val = _to_xy(val_rows, feature_names=feature_names)
    x_test, y_test = _to_xy(test_rows, feature_names=feature_names)

    model: Pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("ridge", Ridge(alpha=alpha)),
        ]
    )

    model.fit(x_train, y_train)

    train_pred = model.predict(x_train)
    val_pred = model.predict(x_val) if len(val_rows) else np.array([], dtype=float)
    test_pred = model.predict(x_test) if len(test_rows) else np.array([], dtype=float)

    train_metrics = _metrics(y_train, train_pred)
    val_metrics = _metrics(y_val, val_pred) if len(val_rows) else RegressionMetrics(0.0, 0.0, 0.0)
    test_metrics = (
        _metrics(y_test, test_pred) if len(test_rows) else RegressionMetrics(0.0, 0.0, 0.0)
    )

    result = PointDiffTrainResult(
        feature_names=feature_names,
        train_size=len(train_rows),
        val_size=len(val_rows),
        test_size=len(test_rows),
        train_metrics=train_metrics,
        val_metrics=val_metrics,
        test_metrics=test_metrics,
    )

    return result, model


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _consensus_line_for_game_at(
    session: Session,
    *,
    game_id: int,
    market_type: MarketTypeEnum,
    side_type: SideTypeEnum,
    target_dt: datetime,
    window: timedelta,
    book_keys: set[str] | None = None,
) -> tuple[float, datetime, int] | None:
    """Return (median_line, captured_at, n_books) closest to target_dt.

    This is robust to The Odds API returning a snapshot timestamp slightly different
    from the requested `date`, by searching within a window.
    """

    start = target_dt - window
    end = target_dt + window

    stmt = (
        select(OddsSnapshot)
        .join(Book, Book.id == OddsSnapshot.book_id)
        .where(
            OddsSnapshot.game_id == game_id,
            OddsSnapshot.market_type == market_type,
            OddsSnapshot.side_type == side_type,
            OddsSnapshot.captured_at >= start,
            OddsSnapshot.captured_at <= end,
            OddsSnapshot.line.is_not(None),
        )
    )

    if book_keys:
        stmt = stmt.where(Book.key.in_(sorted(book_keys)))
    snaps = list(session.execute(stmt).scalars().all())
    if not snaps:
        return None

    lines_by_captured_at: dict[datetime, list[float]] = defaultdict(list)
    for s in snaps:
        if s.captured_at is None or s.line is None:
            continue
        try:
            line_f = float(s.line)
        except (TypeError, ValueError):
            continue
        lines_by_captured_at[s.captured_at].append(line_f)

    if not lines_by_captured_at:
        return None

    best: tuple[float, datetime, int] | None = None
    best_dt_delta_s: float | None = None
    best_n_books: int = 0

    for captured_at, lines in lines_by_captured_at.items():
        if not lines:
            continue
        dt_delta_s = abs((_as_utc(captured_at) - target_dt).total_seconds())
        n_books = len(lines)

        if best is None:
            best = (float(median(lines)), captured_at, n_books)
            best_dt_delta_s = dt_delta_s
            best_n_books = n_books
            continue

        assert best_dt_delta_s is not None
        if (dt_delta_s < best_dt_delta_s) or (
            dt_delta_s == best_dt_delta_s and n_books > best_n_books
        ):
            best = (float(median(lines)), captured_at, n_books)
            best_dt_delta_s = dt_delta_s
            best_n_books = n_books

    return best


def compare_point_diff_model_vs_spread_market(
    session: Session,
    *,
    rows: list[FootballGameDatasetRow],
    model: Pipeline,
    feature_names: list[str],
    as_of_hours: int = 6,
    round_to_hour: bool = True,
    window_minutes: int = 180,
    min_edge_points: float = 1.0,
    vig_price: int = -110,
    book_keys: list[str] | None = None,
) -> SpreadMarketComparisonResult:
    """Compare point-diff predictions against a consensus spread.

    Uses the HOME-side spread line to derive a market implied point_diff: `-home_spread_line`.

    Betting simulation:
    - Bet HOME if model - market >= min_edge_points
    - Bet AWAY if model - market <= -min_edge_points
    - Else no bet
    Assumes a fixed American odds price (default -110).
    """

    if not rows:
        return SpreadMarketComparisonResult(
            games_with_market=0,
            rmse_model_vs_actual=0.0,
            rmse_market_vs_actual=0.0,
            bets=0,
            wins=0,
            losses=0,
            pushes=0,
            profit_units=0.0,
        )

    x, _y_true = _to_xy(rows, feature_names=feature_names)
    y_pred = model.predict(x)

    if len(y_pred) != len(rows):
        raise ValueError("Model prediction output length mismatch")

    # -110 => risk 1.0 to win 0.9091 units
    if vig_price >= 0:
        raise ValueError("vig_price should be negative American odds (e.g. -110)")
    win_profit = 100.0 / float(-vig_price)

    market_preds: list[float] = []
    model_preds: list[float] = []
    actuals: list[float] = []

    bets = 0
    wins = 0
    losses = 0
    pushes = 0
    profit_units = 0.0

    window = timedelta(minutes=window_minutes)
    book_key_set = {k.strip() for k in book_keys or [] if k.strip()} or None

    for r, pred in zip(rows, y_pred, strict=True):
        target = _as_utc(r.start_time) - timedelta(hours=as_of_hours)
        if round_to_hour:
            target = target.replace(minute=0, second=0, microsecond=0)
        else:
            target = target.replace(second=0, microsecond=0)

        consensus = _consensus_line_for_game_at(
            session,
            game_id=r.game_id,
            market_type=MarketTypeEnum.SPREAD,
            side_type=SideTypeEnum.HOME,
            target_dt=target,
            window=window,
            book_keys=book_key_set,
        )
        if consensus is None:
            continue

        home_spread_line, _captured_at, _n_books = consensus
        market_point_diff = -float(home_spread_line)

        actual = float(r.point_diff)
        model_preds.append(float(pred))
        market_preds.append(market_point_diff)
        actuals.append(actual)

        edge = float(pred) - market_point_diff
        if edge >= min_edge_points:
            # Bet HOME against spread.
            bets += 1
            cover_margin = actual + float(home_spread_line)
            if cover_margin > 0:
                wins += 1
                profit_units += win_profit
            elif cover_margin < 0:
                losses += 1
                profit_units -= 1.0
            else:
                pushes += 1
        elif edge <= -min_edge_points:
            # Bet AWAY against spread.
            bets += 1
            cover_margin = actual + float(home_spread_line)
            if cover_margin < 0:
                wins += 1
                profit_units += win_profit
            elif cover_margin > 0:
                losses += 1
                profit_units -= 1.0
            else:
                pushes += 1

    if not actuals:
        return SpreadMarketComparisonResult(
            games_with_market=0,
            rmse_model_vs_actual=0.0,
            rmse_market_vs_actual=0.0,
            bets=bets,
            wins=wins,
            losses=losses,
            pushes=pushes,
            profit_units=profit_units,
        )

    y_actual = np.array(actuals, dtype=float)
    y_model = np.array(model_preds, dtype=float)
    y_market = np.array(market_preds, dtype=float)

    rmse_model = float(np.sqrt(float(mean_squared_error(y_actual, y_model))))
    rmse_market = float(np.sqrt(float(mean_squared_error(y_actual, y_market))))

    return SpreadMarketComparisonResult(
        games_with_market=len(actuals),
        rmse_model_vs_actual=rmse_model,
        rmse_market_vs_actual=rmse_market,
        bets=bets,
        wins=wins,
        losses=losses,
        pushes=pushes,
        profit_units=profit_units,
    )
