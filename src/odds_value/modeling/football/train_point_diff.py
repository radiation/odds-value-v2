from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

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
