from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from enum import StrEnum

from sqlalchemy.orm import Session

SessionScope = Callable[[], AbstractContextManager[Session]]
EchoFn = Callable[[str], None]


class FootballPointDiffTarget(StrEnum):
    POINT_DIFF = "point-diff"
    RESIDUAL_VS_SPREAD = "residual-vs-spread"


class SweepSplit(StrEnum):
    VAL = "val"
    TEST = "test"
