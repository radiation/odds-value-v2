from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from odds_value.db.enums import GameStatusEnum
from odds_value.db.models.core.game import Game
from odds_value.db.models.core.league import League
from odds_value.db.models.core.season import Season
from odds_value.db.models.features.football_team_game_state import FootballTeamGameState
from odds_value.db.models.features.football_team_game_stats import FootballTeamGameStats
from odds_value.db.models.features.team_game_stats import TeamGameStats
from odds_value.db.repos.core.league_repo import LeagueRepository
from odds_value.db.repos.core.season_repo import SeasonRepository
from odds_value.ingestion.football.nfl_calendar import (
    in_nfl_regular_season_window,
    nfl_regular_season_week,
)


@dataclass(frozen=True)
class BuildFootballTeamGameStateResult:
    league_key: str
    season_year: int
    games_seen: int
    team_games_seen: int
    states_created: int
    states_updated: int
    games_skipped: int


@dataclass(frozen=True)
class _TeamGameObserved:
    start_time: datetime
    points_for: int
    points_against: int
    yards_for: int | None
    yards_against: int | None
    turnovers_for: int | None
    takeaways: int | None


def _mean(values: list[int | float | None]) -> float:
    kept: list[float] = [float(v) for v in values if v is not None]
    if not kept:
        return 0.0
    return sum(kept) / len(kept)


def _days_between(earlier: datetime, later: datetime) -> int:
    if earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=UTC)
    if later.tzinfo is None:
        later = later.replace(tzinfo=UTC)
    delta = later - earlier
    return int(delta.total_seconds() // 86400)


def build_football_team_game_state_for_season(
    session: Session,
    *,
    league_key: str,
    season_year: int,
    rebuild: bool = False,
    include_non_regular_season: bool = False,
    commit_every: int = 500,
) -> BuildFootballTeamGameStateResult:
    """Build `football_team_game_state` rows for a season.

    Computes pre-game features "as of kickoff" (no leakage): for a given game,
    only games strictly before that game's `start_time` contribute to features.

    Notes:
    - Currently implemented for NFL only, because the `week` definition is
      NFL-specific (Tue→Mon ET buckets).
    - History only considers FINAL games with known scores.
    """

    if league_key != "NFL":
        raise ValueError("Only league_key='NFL' is supported for now")

    league_repo = LeagueRepository(session)
    season_repo = SeasonRepository(session)

    league = league_repo.one_where(League.league_key == league_key)
    season = season_repo.one_where(Season.league_id == league.id, Season.year == season_year)

    games_stmt = (
        select(Game)
        .where(Game.league_id == league.id, Game.season_id == season.id)
        .order_by(Game.start_time)
    )
    games = list(session.execute(games_stmt).scalars().all())

    if rebuild:
        session.execute(delete(FootballTeamGameState).where(FootballTeamGameState.season_id == season.id))
        session.commit()

    existing_stmt = select(FootballTeamGameState).where(FootballTeamGameState.season_id == season.id)
    existing = list(session.execute(existing_stmt).scalars().all())
    existing_by_team_game: dict[tuple[int, int], FootballTeamGameState] = {
        (r.team_id, r.game_id): r for r in existing
    }

    # Preload observed per-team stats in this season (optional; some games may be missing).
    tgs_stmt = (
        select(TeamGameStats)
        .join(Game, Game.id == TeamGameStats.game_id)
        .where(Game.league_id == league.id, Game.season_id == season.id)
    )
    tgs_rows = list(session.execute(tgs_stmt).scalars().all())
    tgs_by_game_team: dict[tuple[int, int], TeamGameStats] = {(r.game_id, r.team_id): r for r in tgs_rows}

    fb_stmt = select(FootballTeamGameStats).where(
        FootballTeamGameStats.team_game_stats_id.in_([r.id for r in tgs_rows])
    )
    fb_rows = list(session.execute(fb_stmt).scalars().all()) if tgs_rows else []
    fb_by_tgs_id: dict[int, FootballTeamGameStats] = {r.team_game_stats_id: r for r in fb_rows}

    history_by_team: dict[int, list[_TeamGameObserved]] = {}

    states_created = 0
    states_updated = 0
    games_skipped = 0
    team_games_seen = 0

    for idx, game in enumerate(games, start=1):
        if game.start_time is None or game.home_team_id is None or game.away_team_id is None:
            continue

        if not include_non_regular_season and not in_nfl_regular_season_window(game.start_time, season_year):
            games_skipped += 1
            continue

        # Compute pregame state for both teams before adding this game's results.
        for team_id in (game.home_team_id, game.away_team_id):
            team_games_seen += 1

            history = history_by_team.get(team_id, [])
            games_played = len(history)

            last_game_time = history[-1].start_time if history else None
            rest_days = _days_between(last_game_time, game.start_time) if last_game_time else None

            l3 = history[-3:]
            l5 = history[-5:]

            off_pts_l3 = _mean([h.points_for for h in l3])
            off_pts_l5 = _mean([h.points_for for h in l5])
            off_pts_season = _mean([h.points_for for h in history])

            off_diff_l3 = _mean([(h.points_for - h.points_against) for h in l3])
            off_diff_l5 = _mean([(h.points_for - h.points_against) for h in l5])
            off_diff_season = _mean([(h.points_for - h.points_against) for h in history])

            off_yards_l3 = _mean([h.yards_for for h in l3])
            off_yards_l5 = _mean([h.yards_for for h in l5])
            off_yards_season = _mean([h.yards_for for h in history])

            off_turnovers_l3 = _mean([h.turnovers_for for h in l3])
            off_turnovers_l5 = _mean([h.turnovers_for for h in l5])
            off_turnovers_season = _mean([h.turnovers_for for h in history])

            def_pa_l3 = _mean([h.points_against for h in l3])
            def_pa_l5 = _mean([h.points_against for h in l5])
            def_pa_season = _mean([h.points_against for h in history])

            def_diff_l3 = _mean([(h.points_against - h.points_for) for h in l3])
            def_diff_l5 = _mean([(h.points_against - h.points_for) for h in l5])
            def_diff_season = _mean([(h.points_against - h.points_for) for h in history])

            def_yards_allowed_l3 = _mean([h.yards_against for h in l3])
            def_yards_allowed_l5 = _mean([h.yards_against for h in l5])
            def_yards_allowed_season = _mean([h.yards_against for h in history])

            def_takeaways_l3 = _mean([h.takeaways for h in l3])
            def_takeaways_l5 = _mean([h.takeaways for h in l5])
            def_takeaways_season = _mean([h.takeaways for h in history])

            state_values = {
                "team_id": team_id,
                "game_id": game.id,
                "start_time": game.start_time,
                "season_id": season.id,
                "week": nfl_regular_season_week(game.start_time, season_year),
                "games_played": games_played,
                "rest_days": rest_days,
                "games_l3": min(3, games_played),
                "games_l5": min(5, games_played),
                "off_pts_l3": off_pts_l3,
                "off_pts_l5": off_pts_l5,
                "off_pts_season": off_pts_season,
                "off_diff_l3": off_diff_l3,
                "off_diff_l5": off_diff_l5,
                "off_diff_season": off_diff_season,
                "off_yards_l3": off_yards_l3,
                "off_yards_l5": off_yards_l5,
                "off_yards_season": off_yards_season,
                "off_turnovers_l3": off_turnovers_l3,
                "off_turnovers_l5": off_turnovers_l5,
                "off_turnovers_season": off_turnovers_season,
                "def_pa_l3": def_pa_l3,
                "def_pa_l5": def_pa_l5,
                "def_pa_season": def_pa_season,
                "def_diff_l3": def_diff_l3,
                "def_diff_l5": def_diff_l5,
                "def_diff_season": def_diff_season,
                "def_yards_allowed_l3": def_yards_allowed_l3,
                "def_yards_allowed_l5": def_yards_allowed_l5,
                "def_yards_allowed_season": def_yards_allowed_season,
                "def_takeaways_l3": def_takeaways_l3,
                "def_takeaways_l5": def_takeaways_l5,
                "def_takeaways_season": def_takeaways_season,
            }

            existing_row = existing_by_team_game.get((team_id, game.id))
            if existing_row is None:
                row = FootballTeamGameState(**state_values)
                session.add(row)
                existing_by_team_game[(team_id, game.id)] = row
                states_created += 1
            else:
                for key, value in state_values.items():
                    setattr(existing_row, key, value)
                states_updated += 1

        # After computing pregame state, add this game's final observed stats to history.
        if (
            game.status == GameStatusEnum.FINAL
            and game.home_score is not None
            and game.away_score is not None
            and game.home_team_id is not None
            and game.away_team_id is not None
        ):
            home_tgs = tgs_by_game_team.get((game.id, game.home_team_id))
            away_tgs = tgs_by_game_team.get((game.id, game.away_team_id))

            home_fb = fb_by_tgs_id.get(home_tgs.id) if home_tgs else None
            away_fb = fb_by_tgs_id.get(away_tgs.id) if away_tgs else None

            home_obs = _TeamGameObserved(
                start_time=game.start_time,
                points_for=game.home_score,
                points_against=game.away_score,
                yards_for=home_fb.yards_total if home_fb else None,
                yards_against=away_fb.yards_total if away_fb else None,
                turnovers_for=home_fb.turnovers if home_fb else None,
                takeaways=away_fb.turnovers if away_fb else None,
            )
            away_obs = _TeamGameObserved(
                start_time=game.start_time,
                points_for=game.away_score,
                points_against=game.home_score,
                yards_for=away_fb.yards_total if away_fb else None,
                yards_against=home_fb.yards_total if home_fb else None,
                turnovers_for=away_fb.turnovers if away_fb else None,
                takeaways=home_fb.turnovers if home_fb else None,
            )

            history_by_team.setdefault(game.home_team_id, []).append(home_obs)
            history_by_team.setdefault(game.away_team_id, []).append(away_obs)

        if commit_every > 0 and idx % commit_every == 0:
            session.commit()

    session.commit()

    return BuildFootballTeamGameStateResult(
        league_key=league_key,
        season_year=season_year,
        games_seen=len(games),
        team_games_seen=team_games_seen,
        states_created=states_created,
        states_updated=states_updated,
        games_skipped=games_skipped,
    )
