from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from math import log, pow
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
    include_elo_features: bool = False,
    elo_initial: float = 1500.0,
    elo_k: float = 20.0,
    elo_home_field_advantage: float = 55.0,
    elo_regress_to_mean: float = 0.33,
) -> list[FootballGameDatasetRow]:
    """Build a game-level modeling dataset from `football_team_game_state`.

    Produces one row per game by joining the home and away pregame state rows.

    Targets (supervised labels):
    - `point_diff` = home_score - away_score
    - `total_points` = home_score + away_score
    - `home_win` = 1 if home_score > away_score else 0

    Split guidance: do time-based splits by `season_year` (or `start_time`) to avoid leakage.

    Optional features:
    - Elo ratings (if include_elo_features=True): pregame team strength computed from prior games only.
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

    # Optional team-strength signal derived from past results only (no leakage).
    elo_by_team_id: dict[int, float] = {}
    last_season_year: int | None = None

    def _elo_expected(home_elo: float, away_elo: float) -> float:
        exp = (away_elo - (home_elo + elo_home_field_advantage)) / 400.0
        return 1.0 / (1.0 + pow(10.0, exp))

    def _elo_mov_multiplier(point_diff: float) -> float:
        # Common Elo margin-of-victory multiplier (bounded, diminishing returns).
        margin = abs(point_diff)
        return log(margin + 1.0) * (2.2 / ((margin * 0.001) + 2.2))

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

        season_year_i = int(season_year)
        if include_elo_features:
            if last_season_year is None:
                last_season_year = season_year_i
            elif season_year_i != last_season_year:
                # Regress toward the mean at season boundaries (reduces stale carryover).
                for team_id, rating in list(elo_by_team_id.items()):
                    elo_by_team_id[team_id] = elo_initial + (rating - elo_initial) * (
                        1.0 - elo_regress_to_mean
                    )
                last_season_year = season_year_i

            home_elo_pre = float(elo_by_team_id.get(int(game.home_team_id), elo_initial))
            away_elo_pre = float(elo_by_team_id.get(int(game.away_team_id), elo_initial))
            features["elo_home_pre"] = home_elo_pre
            features["elo_away_pre"] = away_elo_pre
            features["elo_diff_pre"] = home_elo_pre - away_elo_pre

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
                season_year=season_year_i,
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

        if include_elo_features:
            home_id = int(game.home_team_id)
            away_id = int(game.away_team_id)
            home_elo = float(elo_by_team_id.get(home_id, elo_initial))
            away_elo = float(elo_by_team_id.get(away_id, elo_initial))

            expected_home = _elo_expected(home_elo, away_elo)
            if point_diff > 0:
                actual_home = 1.0
            elif point_diff < 0:
                actual_home = 0.0
            else:
                actual_home = 0.5

            delta = elo_k * _elo_mov_multiplier(float(point_diff)) * (actual_home - expected_home)
            elo_by_team_id[home_id] = home_elo + delta
            elo_by_team_id[away_id] = away_elo - delta

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
