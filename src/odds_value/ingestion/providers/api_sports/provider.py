from __future__ import annotations

from sqlalchemy.orm import Session

from odds_value.db.enums import ProviderEnum, SportEnum
from odds_value.db.models.core.provider_sport import ProviderSport
from odds_value.ingestion.providers.api_sports.adapters.football import ApiSportsFootballAdapter
from odds_value.ingestion.providers.api_sports.client import ApiSportsClient
from odds_value.ingestion.providers.base.client import BaseHttpClient
from odds_value.ingestion.providers.base.registry import AdapterKey, AdapterRegistry


def _get_base_url(session: Session) -> str:
    row = (
        session.query(ProviderSport)
        .filter(
            ProviderSport.provider == ProviderEnum.API_SPORTS,
            ProviderSport.sport == SportEnum.FOOTBALL,
        )
        .one()
    )
    return row.base_url


def register_api_sports_adapters(
    registry: AdapterRegistry,
    *,
    session: Session,
    api_key: str,
) -> None:
    base_url = _get_base_url(session)

    def make_client() -> ApiSportsClient:
        http = BaseHttpClient(base_url=base_url)
        return ApiSportsClient(http=http, api_key=api_key)

    # Register NFL adapter
    registry.register(
        AdapterKey(provider=ProviderEnum.API_SPORTS.value, league_key="NFL"),
        factory=lambda: ApiSportsFootballAdapter(client=make_client(), league_key="NFL"),
    )

    # Register NCAAF adapter
    registry.register(
        AdapterKey(provider=ProviderEnum.API_SPORTS.value, league_key="NCAAF"),
        factory=lambda: ApiSportsFootballAdapter(client=make_client(), league_key="NCAAF"),
    )
