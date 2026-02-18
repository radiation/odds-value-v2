from __future__ import annotations

from dataclasses import dataclass

from odds_value.modeling.football.dataset import FootballGameDatasetRow


@dataclass(frozen=True)
class SeasonSplit:
    train: list[FootballGameDatasetRow]
    val: list[FootballGameDatasetRow]
    test: list[FootballGameDatasetRow]


def split_by_season_year(
    rows: list[FootballGameDatasetRow],
    *,
    train_end_year: int,
    val_year: int,
    test_year: int,
) -> SeasonSplit:
    """Time-based split by `season_year`.

    This avoids leakage and matches how you'd actually deploy: train on past seasons,
    tune on the next season, and evaluate on the most recent season.
    """

    if not (train_end_year < val_year < test_year):
        raise ValueError(
            "Require train_end_year < val_year < test_year; "
            f"got train_end_year={train_end_year}, val_year={val_year}, test_year={test_year}"
        )

    train = [r for r in rows if r.season_year <= train_end_year]
    val = [r for r in rows if r.season_year == val_year]
    test = [r for r in rows if r.season_year == test_year]

    return SeasonSplit(train=train, val=val, test=test)


def split_by_season_year_window(
    rows: list[FootballGameDatasetRow],
    *,
    train_end_year: int,
    val_start_year: int,
    val_end_year: int,
    test_year: int,
) -> SeasonSplit:
    """Time-based split by `season_year` with a multi-year validation window."""

    if not (train_end_year < val_start_year <= val_end_year < test_year):
        raise ValueError(
            "Require train_end_year < val_start_year <= val_end_year < test_year; "
            f"got train_end_year={train_end_year}, val_start_year={val_start_year}, "
            f"val_end_year={val_end_year}, test_year={test_year}"
        )

    train = [r for r in rows if r.season_year <= train_end_year]
    val = [r for r in rows if val_start_year <= r.season_year <= val_end_year]
    test = [r for r in rows if r.season_year == test_year]

    return SeasonSplit(train=train, val=val, test=test)
