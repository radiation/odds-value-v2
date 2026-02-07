from __future__ import annotations

from typing import Protocol

from .types import EntityBundle, IngestQuery


class ProviderAdapter(Protocol):
    """
    Orchestration depends on this, not on any HTTP client.

    Each provider may only support some sports/leagues.
    """

    provider_key: str

    def fetch_entities(self, query: IngestQuery) -> EntityBundle:
        """
        Fetch + normalize provider data into canonical entity payloads.
        For games-first providers (API-Sports), this likely:
            fetch games -> derive leagues/seasons/teams -> return bundle
        """
        ...
