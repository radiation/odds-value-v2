from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from odds_value.db.enums import ProviderEnum
from odds_value.ingestion.providers.api_sports.client import ApiSportsClient
from odds_value.ingestion.providers.base.adapter import ProviderAdapter
from odds_value.ingestion.providers.base.errors import ProviderCapabilityError
from odds_value.ingestion.providers.base.types import EntityBundle, IngestQuery


@dataclass(frozen=True)
class ApiSportsFootballAdapter(ProviderAdapter):
    """
    API-Sports "american-football" adapter (NFL/NCAAF/etc).
    """

    client: ApiSportsClient
    league_key: str
    provider_key: str = ProviderEnum.API_SPORTS.value

    def fetch_entities(self, query: IngestQuery) -> EntityBundle:
        if query.league_key != self.league_key:
            raise ProviderCapabilityError(
                f"Adapter is for league_key={self.league_key}, got {query.league_key}"
            )

        game_id = getattr(query, "provider_game_id", None)
        if game_id is None:
            raise ProviderCapabilityError(
                "ApiSportsFootballAdapter requires query.provider_game_id for now "
                "(we'll add date-range ingestion next)."
            )

        items = self.client.get_response_items("/games", params={"id": str(game_id)})

        return EntityBundle(
            leagues=[],
            seasons=[],
            teams=[],
            games=[self._raw_game_to_payload(i) for i in items],
        )

    def _raw_game_to_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        return {"provider": self.provider_key, "league_key": self.league_key, "raw": item}
