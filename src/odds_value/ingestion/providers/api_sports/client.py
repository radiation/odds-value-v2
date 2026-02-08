from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from odds_value.ingestion.providers.base.client import BaseHttpClient
from odds_value.ingestion.providers.base.errors import ProviderResponseError


@dataclass
class ApiSportsClient:
    http: BaseHttpClient
    api_key: str

    def _headers(self) -> dict[str, str]:
        return {"x-apisports-key": self.api_key}

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = self.http.get_json(path, params=params, headers=self._headers())

        errors = data.get("errors") or []
        if errors:
            raise ProviderResponseError(f"api-sports returned errors: {errors}")

        return data

    def get_response_items(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        payload = self.get(path, params=params)
        items = payload.get("response")
        if not isinstance(items, list):
            raise TypeError(f"Expected 'response' list, got: {type(items)}")
        return [i for i in items if isinstance(i, dict)]
