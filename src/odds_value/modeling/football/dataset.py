from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from odds_value.db.enums import GameStatusEnum
from odds_value.db.models.core.game import Game
from odds_value.db.models.core.league import League
from odds_value.db.models.core.season import Season
from odds_value.db.models.features.football_team_game_state import FootballTeamGameState
from odds_value.db.repos.core.league_repo import LeagueRepository


@dataclass(frozen=True)
class FootballGameDatasetRow:
    game_id: int
    season_year: int
    week: int
    start_time: datetime

    home_team_id: int
    away_team_id: int

    home_score: int
    away_score: int

    point_diff: int
    total_points: int
    home_win: int

    # Feature columns live in `features` so we can expand safely over time.
    features: dict[str, float]


_NUMERIC_STATE_COLUMNS: tuple[str, ...] = (
    "games_played",
    "rest_days",
    "games_l3",
    "games_l5",
    "off_pts_l3",
    "off_pts_l5",
    "off_pts_season",
    "off_diff_l3",
    "off_diff_l5",
    "off_diff_season",
    "off_yards_l3",
    "off_yards_l5",
    "off_yards_season",
    "off_turnovers_l3",
    "off_turnovers_l5",
    "off_turnovers_season",
    "def_pa_l3",
    "def_pa_l5",
    "def_pa_season",
    "def_diff_l3",
    "def_diff_l5",
    "def_diff_season",
    "def_yards_allowed_l3",
    "def_yards_allowed_l5",
    "def_yards_allowed_season",
    "def_takeaways_l3",
    "def_takeaways_l5",
    "def_takeaways_season",
)


def _as_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    raise TypeError(f"Unsupported numeric value type: {type(value)}")


def build_football_game_dataset(
    session: Session,
    *,
    league_key: str = "NFL",
    season_start_year: int | None = None,
    season_end_year: int | None = None,
    require_final: bool = True,
) -> list[FootballGameDatasetRow]:
    """Build a game-level modeling dataset from `football_team_game_state`.

    Produces one row per game by joining the home and away pregame state rows.

    Targets (supervised labels):
    - `point_diff` = home_score - away_score
    - `total_points` = home_score + away_score
    - `home_win` = 1 if home_score > away_score else 0

    Split guidance: do time-based splits by `season_year` (or `start_time`) to avoid leakage.
    """

    league_repo = LeagueRepository(session)
    league = league_repo.one_where(League.league_key == league_key)

    home_state = aliased(FootballTeamGameState)
    away_state = aliased(FootballTeamGameState)

    stmt = (
        select(Game, Season.year, home_state, away_state)
        .join(Season, Season.id == Game.season_id)
        .join(
            home_state,
            (home_state.game_id == Game.id) & (home_state.team_id == Game.home_team_id),
        )
        .join(
            away_state,
            (away_state.game_id == Game.id) & (away_state.team_id == Game.away_team_id),
        )
        .where(Game.league_id == league.id)
        .order_by(Game.start_time)
    )

    if season_start_year is not None:
        stmt = stmt.where(Season.year >= season_start_year)
    if season_end_year is not None:
        stmt = stmt.where(Season.year <= season_end_year)

    if require_final:
        stmt = stmt.where(
            Game.status == GameStatusEnum.FINAL,
            Game.home_score.is_not(None),
            Game.away_score.is_not(None),
        )

    rows: list[FootballGameDatasetRow] = []

    for game, season_year, hs, aws in session.execute(stmt).all():
        if (
            game.id is None
            or game.start_time is None
            or game.home_team_id is None
            or game.away_team_id is None
            or game.home_score is None
            or game.away_score is None
        ):
            continue

        features: dict[str, float] = {}

        # Encode state columns as home/away + diff.
        for col in _NUMERIC_STATE_COLUMNS:
            h_val = _as_float(getattr(hs, col))
            a_val = _as_float(getattr(aws, col))
            features[f"home_{col}"] = h_val
            features[f"away_{col}"] = a_val
            features[f"diff_{col}"] = h_val - a_val

        # Week is stored on state rows; (home == away) by construction.
        week = int(hs.week)

        point_diff = int(game.home_score - game.away_score)
        total_points = int(game.home_score + game.away_score)
        home_win = 1 if point_diff > 0 else 0

        rows.append(
            FootballGameDatasetRow(
                game_id=int(game.id),
                season_year=int(season_year),
                week=week,
                start_time=game.start_time,
                home_team_id=int(game.home_team_id),
                away_team_id=int(game.away_team_id),
                home_score=int(game.home_score),
                away_score=int(game.away_score),
                point_diff=point_diff,
                total_points=total_points,
                home_win=home_win,
                features=features,
            )
        )

    return rows


def write_football_game_dataset_csv(rows: list[FootballGameDatasetRow], *, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    # Stable column order: metadata/targets first, then features sorted.
    feature_keys: list[str] = sorted({k for r in rows for k in r.features})

    fieldnames = [
        "game_id",
        "season_year",
        "week",
        "start_time",
        "home_team_id",
        "away_team_id",
        "home_score",
        "away_score",
        "point_diff",
        "total_points",
        "home_win",
        *feature_keys,
    ]

    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in rows:
            row_dict: dict[str, object] = {
                "game_id": r.game_id,
                "season_year": r.season_year,
                "week": r.week,
                "start_time": r.start_time.isoformat(),
                "home_team_id": r.home_team_id,
                "away_team_id": r.away_team_id,
                "home_score": r.home_score,
                "away_score": r.away_score,
                "point_diff": r.point_diff,
                "total_points": r.total_points,
                "home_win": r.home_win,
            }
            for k in feature_keys:
                row_dict[k] = r.features.get(k, 0.0)
            writer.writerow(row_dict)
