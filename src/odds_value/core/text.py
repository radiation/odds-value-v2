from __future__ import annotations

import re

_whitespace_re = re.compile(r"\s+")
_non_alnum_re = re.compile(r"[^a-z0-9\s]")


def normalize_team_alias(value: str) -> str:
    """Normalize a team alias for stable matching across sources."""

    v = value.strip().lower()
    v = _non_alnum_re.sub(" ", v)
    v = _whitespace_re.sub(" ", v)
    return v.strip()
