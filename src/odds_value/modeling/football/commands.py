"""Non-CLI entrypoints for modeling workflows.

This module is intentionally thin: it provides a stable import path for the CLI
(`odds_value.modeling.football.commands`) while keeping implementations split
across smaller modules.
"""

from __future__ import annotations

from odds_value.modeling.football import commands_export as _export
from odds_value.modeling.football import commands_train_point_diff as _train
from odds_value.modeling.football.commands_types import (
    EchoFn,
    FootballPointDiffTarget,
    SessionScope,
    SweepSplit,
)

export_football_game_dataset = _export.export_football_game_dataset
train_football_point_diff = _train.train_football_point_diff

__all__ = [
    "EchoFn",
    "FootballPointDiffTarget",
    "SessionScope",
    "SweepSplit",
    "export_football_game_dataset",
    "train_football_point_diff",
]
