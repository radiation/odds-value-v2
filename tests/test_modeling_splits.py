from __future__ import annotations

from datetime import UTC, datetime

from odds_value.modeling.football.dataset import FootballGameDatasetRow
from odds_value.modeling.football.splits import split_by_season_year


def _row(season_year: int, game_id: int) -> FootballGameDatasetRow:
    return FootballGameDatasetRow(
        game_id=game_id,
        season_year=season_year,
        week=1,
        start_time=datetime(season_year, 9, 1, tzinfo=UTC),
        home_team_id=1,
        away_team_id=2,
        home_score=10,
        away_score=7,
        point_diff=3,
        total_points=17,
        home_win=1,
        features={"diff_off_pts_l3": 0.0},
    )


def test_split_by_season_year_partitions_rows() -> None:
    rows = [_row(2023, 1), _row(2024, 2), _row(2025, 3)]

    split = split_by_season_year(rows, train_end_year=2023, val_year=2024, test_year=2025)

    assert [r.game_id for r in split.train] == [1]
    assert [r.game_id for r in split.val] == [2]
    assert [r.game_id for r in split.test] == [3]
