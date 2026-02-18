from __future__ import annotations

from pathlib import Path

from odds_value.modeling.football.commands_types import EchoFn, SessionScope
from odds_value.modeling.football.dataset import (
    build_football_game_dataset,
    write_football_game_dataset_csv,
)


def export_football_game_dataset(
    *,
    session_scope: SessionScope,
    echo: EchoFn,
    league_key: str,
    season_start_year: int | None,
    season_end_year: int | None,
    include_elo_features: bool,
    out: str,
) -> None:
    with session_scope() as session:
        rows = build_football_game_dataset(
            session,
            league_key=league_key,
            season_start_year=season_start_year,
            season_end_year=season_end_year,
            require_final=True,
            include_elo_features=include_elo_features,
        )

    out_path = Path(out)
    write_football_game_dataset_csv(rows, path=out_path)

    echo(f"Exported {len(rows)} rows to {out_path}")
