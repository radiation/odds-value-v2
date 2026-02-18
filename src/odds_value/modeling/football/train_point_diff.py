from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median, median_low

import numpy as np
from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
from sqlalchemy import func, select
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
    sum_win_profit_units: float
    breakeven_win_rate: float


@dataclass(frozen=True)
class ResidualTrainResult:
    feature_names: list[str]
    train_size: int
    val_size: int
    test_size: int
    train_skipped_no_market: int
    val_skipped_no_market: int
    test_skipped_no_market: int
    train_metrics: RegressionMetrics
    val_metrics: RegressionMetrics
    test_metrics: RegressionMetrics


@dataclass(frozen=True)
class ResidualMarketComparisonResult:
    games_with_market: int
    rmse_residual: float
    rmse_pointdiff_from_market_plus_model: float
    rmse_market_vs_actual: float
    bets: int
    wins: int
    losses: int
    pushes: int
    profit_units: float
    sum_win_profit_units: float
    breakeven_win_rate: float


@dataclass(frozen=True)
class _MarketLabeledRow:
    row: FootballGameDatasetRow
    home_spread_line: float
    market_point_diff: float
    captured_at: datetime
    n_books: int


def _features_for_labeled_row(
    lr: _MarketLabeledRow, *, include_market_features: bool
) -> dict[str, float]:
    base = lr.row.features
    if not include_market_features:
        return base

    # Copy to avoid mutating the underlying dataset row.
    merged: dict[str, float] = dict(base)
    merged["market_point_diff"] = float(lr.market_point_diff)
    merged["home_spread_line"] = float(lr.home_spread_line)
    merged["market_n_books"] = float(lr.n_books)
    return merged


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


def _label_rows_with_market_spread(
    session: Session,
    *,
    rows: list[FootballGameDatasetRow],
    as_of_hours: int,
    round_to_hour: bool,
    window_minutes: int,
    book_keys: set[str] | None,
) -> tuple[list[_MarketLabeledRow], int]:
    labeled: list[_MarketLabeledRow] = []
    skipped = 0

    window = timedelta(minutes=window_minutes)

    for r in rows:
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
            book_keys=book_keys,
        )
        if consensus is None:
            skipped += 1
            continue

        home_spread_line, captured_at, n_books = consensus
        market_point_diff = -float(home_spread_line)

        labeled.append(
            _MarketLabeledRow(
                row=r,
                home_spread_line=float(home_spread_line),
                market_point_diff=float(market_point_diff),
                captured_at=captured_at,
                n_books=int(n_books),
            )
        )

    return labeled, skipped


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


def _win_profit_units_for_american_price(price: int) -> float:
    """Return profit (in units) for a 1.0 unit stake when the bet wins.

    Examples:
    - -110 => 0.9091
    - +120 => 1.2
    """

    if price == 0:
        raise ValueError("American odds price cannot be 0")

    if price > 0:
        return float(price) / 100.0
    return 100.0 / float(-price)


def _median_price_for_game_at_captured_at(
    session: Session,
    *,
    game_id: int,
    market_type: MarketTypeEnum,
    side_type: SideTypeEnum,
    captured_at: datetime,
    line: float | None,
    book_keys: set[str] | None = None,
) -> float | None:
    stmt = (
        select(OddsSnapshot.price)
        .join(Book, Book.id == OddsSnapshot.book_id)
        .where(
            OddsSnapshot.game_id == game_id,
            OddsSnapshot.market_type == market_type,
            OddsSnapshot.side_type == side_type,
            OddsSnapshot.captured_at == captured_at,
            OddsSnapshot.line.is_not(None),
            OddsSnapshot.price != 0,
        )
    )

    if line is not None:
        # Avoid exact equality on floats/NUMERIC; tolerate tiny representation differences.
        stmt = stmt.where(func.abs(OddsSnapshot.line - float(line)) < 0.001)

    if book_keys:
        stmt = stmt.where(Book.key.in_(sorted(book_keys)))

    prices = list(session.execute(stmt).scalars().all())
    if not prices:
        return None

    win_profits: list[float] = []
    for p in prices:
        try:
            win_profits.append(_win_profit_units_for_american_price(int(p)))
        except ValueError:
            continue

    if not win_profits:
        return None

    return float(median(win_profits))


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
    """Return (consensus_line, captured_at, n_books) closest to target_dt.

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

        consensus_line = float(median_low(lines))

        if best is None:
            best = (consensus_line, captured_at, n_books)
            best_dt_delta_s = dt_delta_s
            best_n_books = n_books
            continue

        assert best_dt_delta_s is not None
        if (dt_delta_s < best_dt_delta_s) or (
            dt_delta_s == best_dt_delta_s and n_books > best_n_books
        ):
            best = (consensus_line, captured_at, n_books)
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
    min_market_books: int = 1,
    vig_price: int = -110,
    book_keys: list[str] | None = None,
) -> SpreadMarketComparisonResult:
    """Compare point-diff predictions against a consensus spread.

    Uses the HOME-side spread line to derive a market implied point_diff: `-home_spread_line`.

        Betting simulation:
    - Bet HOME if model - market >= min_edge_points
    - Bet AWAY if model - market <= -min_edge_points
    - Else no bet

        Pricing:
        - Uses the median `OddsSnapshot.price` (American odds) across eligible books at the
            chosen `captured_at` for the bet side.
        - If price is unavailable for that side at that `captured_at`, falls back to `vig_price`.
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
            sum_win_profit_units=0.0,
            breakeven_win_rate=0.0,
        )

    x, _y_true = _to_xy(rows, feature_names=feature_names)
    y_pred = model.predict(x)

    if len(y_pred) != len(rows):
        raise ValueError("Model prediction output length mismatch")

    market_preds: list[float] = []
    model_preds: list[float] = []
    actuals: list[float] = []

    bets = 0
    wins = 0
    losses = 0
    pushes = 0
    profit_units = 0.0
    sum_win_profit_units = 0.0

    window = timedelta(minutes=window_minutes)
    book_key_set = {k.strip() for k in book_keys or [] if k.strip()} or None

    if min_market_books < 1:
        raise ValueError("min_market_books must be >= 1")

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
        if int(_n_books) < int(min_market_books):
            continue
        market_point_diff = -float(home_spread_line)

        actual = float(r.point_diff)
        model_preds.append(float(pred))
        market_preds.append(market_point_diff)
        actuals.append(actual)

        edge = float(pred) - market_point_diff
        bet_side: SideTypeEnum | None
        if edge >= min_edge_points:
            bet_side = SideTypeEnum.HOME
        elif edge <= -min_edge_points:
            bet_side = SideTypeEnum.AWAY
        else:
            bet_side = None

        if bet_side is not None:
            win_profit_median = _median_price_for_game_at_captured_at(
                session,
                game_id=r.game_id,
                market_type=MarketTypeEnum.SPREAD,
                side_type=bet_side,
                captured_at=_captured_at,
                line=(
                    float(home_spread_line)
                    if bet_side == SideTypeEnum.HOME
                    else -float(home_spread_line)
                ),
                book_keys=book_key_set,
            )
            win_profit = (
                float(win_profit_median)
                if win_profit_median is not None
                else _win_profit_units_for_american_price(int(vig_price))
            )

            bets += 1
            sum_win_profit_units += win_profit
            cover_margin = actual + float(home_spread_line)

            if bet_side == SideTypeEnum.HOME:
                if cover_margin > 0:
                    wins += 1
                    profit_units += win_profit
                elif cover_margin < 0:
                    losses += 1
                    profit_units -= 1.0
                else:
                    pushes += 1
            else:
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
            sum_win_profit_units=sum_win_profit_units,
            breakeven_win_rate=(
                float(bets) / (float(bets) + float(sum_win_profit_units)) if bets else 0.0
            ),
        )

    y_actual = np.array(actuals, dtype=float)
    y_model = np.array(model_preds, dtype=float)
    y_market = np.array(market_preds, dtype=float)

    rmse_model = float(np.sqrt(float(mean_squared_error(y_actual, y_model))))
    rmse_market = float(np.sqrt(float(mean_squared_error(y_actual, y_market))))

    breakeven_win_rate = float(bets) / (float(bets) + float(sum_win_profit_units)) if bets else 0.0

    return SpreadMarketComparisonResult(
        games_with_market=len(actuals),
        rmse_model_vs_actual=rmse_model,
        rmse_market_vs_actual=rmse_market,
        bets=bets,
        wins=wins,
        losses=losses,
        pushes=pushes,
        profit_units=profit_units,
        sum_win_profit_units=sum_win_profit_units,
        breakeven_win_rate=breakeven_win_rate,
    )


def train_residual_vs_spread_ridge(
    session: Session,
    *,
    train_rows: list[FootballGameDatasetRow],
    val_rows: list[FootballGameDatasetRow],
    test_rows: list[FootballGameDatasetRow],
    alpha: float = 1.0,
    as_of_hours: int = 6,
    round_to_hour: bool = True,
    window_minutes: int = 180,
    book_keys: list[str] | None = None,
    include_market_features: bool = False,
) -> tuple[ResidualTrainResult, Pipeline]:
    """Train Ridge on residuals: (actual point_diff - market_implied_point_diff).

    Market implied point_diff is derived from the HOME spread line: `-home_spread_line`.
    Only games with an available market snapshot in the window are used.
    """

    book_key_set = {k.strip() for k in book_keys or [] if k.strip()} or None

    labeled_train, skipped_train = _label_rows_with_market_spread(
        session,
        rows=train_rows,
        as_of_hours=as_of_hours,
        round_to_hour=round_to_hour,
        window_minutes=window_minutes,
        book_keys=book_key_set,
    )
    labeled_val, skipped_val = _label_rows_with_market_spread(
        session,
        rows=val_rows,
        as_of_hours=as_of_hours,
        round_to_hour=round_to_hour,
        window_minutes=window_minutes,
        book_keys=book_key_set,
    )
    labeled_test, skipped_test = _label_rows_with_market_spread(
        session,
        rows=test_rows,
        as_of_hours=as_of_hours,
        round_to_hour=round_to_hour,
        window_minutes=window_minutes,
        book_keys=book_key_set,
    )

    if not labeled_train:
        raise ValueError("No training rows have market spreads available")

    feature_names = sorted(
        {
            k
            for lr in labeled_train
            for k in _features_for_labeled_row(lr, include_market_features=include_market_features)
        }
    )
    if not feature_names:
        raise ValueError("No feature columns found in training rows")

    def _to_xy_residual(
        labeled_rows: list[_MarketLabeledRow],
    ) -> tuple[np.ndarray, np.ndarray]:
        feature_dicts = [
            _features_for_labeled_row(lr, include_market_features=include_market_features)
            for lr in labeled_rows
        ]
        x = np.array(
            [[fd.get(f, 0.0) for f in feature_names] for fd in feature_dicts],
            dtype=float,
        )
        y = np.array(
            [float(lr.row.point_diff) - float(lr.market_point_diff) for lr in labeled_rows],
            dtype=float,
        )
        return x, y

    x_train, y_train = _to_xy_residual(labeled_train)
    x_val, y_val = _to_xy_residual(labeled_val) if labeled_val else (np.empty((0, 0)), np.array([]))
    x_test, y_test = (
        _to_xy_residual(labeled_test) if labeled_test else (np.empty((0, 0)), np.array([]))
    )

    model: Pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("ridge", Ridge(alpha=alpha)),
        ]
    )

    model.fit(x_train, y_train)

    train_pred = model.predict(x_train)
    val_pred = model.predict(x_val) if len(labeled_val) else np.array([], dtype=float)
    test_pred = model.predict(x_test) if len(labeled_test) else np.array([], dtype=float)

    train_metrics = _metrics(y_train, train_pred)
    val_metrics = (
        _metrics(y_val, val_pred) if len(labeled_val) else RegressionMetrics(0.0, 0.0, 0.0)
    )
    test_metrics = (
        _metrics(y_test, test_pred) if len(labeled_test) else RegressionMetrics(0.0, 0.0, 0.0)
    )

    result = ResidualTrainResult(
        feature_names=feature_names,
        train_size=len(labeled_train),
        val_size=len(labeled_val),
        test_size=len(labeled_test),
        train_skipped_no_market=skipped_train,
        val_skipped_no_market=skipped_val,
        test_skipped_no_market=skipped_test,
        train_metrics=train_metrics,
        val_metrics=val_metrics,
        test_metrics=test_metrics,
    )

    return result, model


def compare_residual_model_vs_spread_market(
    session: Session,
    *,
    rows: list[FootballGameDatasetRow],
    model: Pipeline,
    feature_names: list[str],
    as_of_hours: int = 6,
    round_to_hour: bool = True,
    window_minutes: int = 180,
    min_edge_points: float = 1.0,
    min_market_books: int = 1,
    vig_price: int = -110,
    book_keys: list[str] | None = None,
    include_market_features: bool = False,
) -> ResidualMarketComparisonResult:
    """Evaluate a residual model and translate it into point_diff + ATS betting.

    residual_pred is interpreted as: predicted (actual_point_diff - market_point_diff).
    Therefore predicted point_diff = market_point_diff + residual_pred.

    Betting simulation matches the point_diff-vs-market approach, except the edge is residual_pred.
    """

    if not rows:
        return ResidualMarketComparisonResult(
            games_with_market=0,
            rmse_residual=0.0,
            rmse_pointdiff_from_market_plus_model=0.0,
            rmse_market_vs_actual=0.0,
            bets=0,
            wins=0,
            losses=0,
            pushes=0,
            profit_units=0.0,
            sum_win_profit_units=0.0,
            breakeven_win_rate=0.0,
        )

    book_key_set = {k.strip() for k in book_keys or [] if k.strip()} or None
    labeled, _skipped = _label_rows_with_market_spread(
        session,
        rows=rows,
        as_of_hours=as_of_hours,
        round_to_hour=round_to_hour,
        window_minutes=window_minutes,
        book_keys=book_key_set,
    )

    if min_market_books < 1:
        raise ValueError("min_market_books must be >= 1")

    if labeled and min_market_books > 1:
        labeled = [lr for lr in labeled if lr.n_books >= min_market_books]

    if not labeled:
        return ResidualMarketComparisonResult(
            games_with_market=0,
            rmse_residual=0.0,
            rmse_pointdiff_from_market_plus_model=0.0,
            rmse_market_vs_actual=0.0,
            bets=0,
            wins=0,
            losses=0,
            pushes=0,
            profit_units=0.0,
            sum_win_profit_units=0.0,
            breakeven_win_rate=0.0,
        )

    feature_dicts = [
        _features_for_labeled_row(lr, include_market_features=include_market_features)
        for lr in labeled
    ]
    x = np.array([[fd.get(f, 0.0) for f in feature_names] for fd in feature_dicts], dtype=float)
    residual_pred = model.predict(x)

    bets = 0
    wins = 0
    losses = 0
    pushes = 0
    profit_units = 0.0
    sum_win_profit_units = 0.0

    residual_true: list[float] = []
    residual_preds: list[float] = []
    point_true: list[float] = []
    point_pred: list[float] = []
    market_point: list[float] = []

    for lr, r_pred in zip(labeled, residual_pred, strict=True):
        actual = float(lr.row.point_diff)
        market_pd = float(lr.market_point_diff)
        r_true = actual - market_pd

        residual_true.append(r_true)
        residual_preds.append(float(r_pred))
        point_true.append(actual)
        point_pred.append(market_pd + float(r_pred))
        market_point.append(market_pd)

        edge = float(r_pred)
        if edge >= min_edge_points:
            bet_side = SideTypeEnum.HOME
            win_profit_median = _median_price_for_game_at_captured_at(
                session,
                game_id=lr.row.game_id,
                market_type=MarketTypeEnum.SPREAD,
                side_type=bet_side,
                captured_at=lr.captured_at,
                line=float(lr.home_spread_line),
                book_keys=book_key_set,
            )
            win_profit = (
                float(win_profit_median)
                if win_profit_median is not None
                else _win_profit_units_for_american_price(int(vig_price))
            )

            bets += 1
            sum_win_profit_units += win_profit
            cover_margin = actual + float(lr.home_spread_line)
            if cover_margin > 0:
                wins += 1
                profit_units += win_profit
            elif cover_margin < 0:
                losses += 1
                profit_units -= 1.0
            else:
                pushes += 1
        elif edge <= -min_edge_points:
            bet_side = SideTypeEnum.AWAY
            win_profit_median = _median_price_for_game_at_captured_at(
                session,
                game_id=lr.row.game_id,
                market_type=MarketTypeEnum.SPREAD,
                side_type=bet_side,
                captured_at=lr.captured_at,
                line=-float(lr.home_spread_line),
                book_keys=book_key_set,
            )
            win_profit = (
                float(win_profit_median)
                if win_profit_median is not None
                else _win_profit_units_for_american_price(int(vig_price))
            )

            bets += 1
            sum_win_profit_units += win_profit
            cover_margin = actual + float(lr.home_spread_line)
            if cover_margin < 0:
                wins += 1
                profit_units += win_profit
            elif cover_margin > 0:
                losses += 1
                profit_units -= 1.0
            else:
                pushes += 1

    y_res_true = np.array(residual_true, dtype=float)
    y_res_pred = np.array(residual_preds, dtype=float)
    y_pd_true = np.array(point_true, dtype=float)
    y_pd_pred = np.array(point_pred, dtype=float)
    y_market = np.array(market_point, dtype=float)

    rmse_residual = float(np.sqrt(float(mean_squared_error(y_res_true, y_res_pred))))
    rmse_pointdiff = float(np.sqrt(float(mean_squared_error(y_pd_true, y_pd_pred))))
    rmse_market = float(np.sqrt(float(mean_squared_error(y_pd_true, y_market))))

    breakeven_win_rate = float(bets) / (float(bets) + float(sum_win_profit_units)) if bets else 0.0

    return ResidualMarketComparisonResult(
        games_with_market=len(labeled),
        rmse_residual=rmse_residual,
        rmse_pointdiff_from_market_plus_model=rmse_pointdiff,
        rmse_market_vs_actual=rmse_market,
        bets=bets,
        wins=wins,
        losses=losses,
        pushes=pushes,
        profit_units=profit_units,
        sum_win_profit_units=sum_win_profit_units,
        breakeven_win_rate=breakeven_win_rate,
    )
