from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import httpx

from .errors import ProviderRateLimited, ProviderRequestError


Json = dict[str, Any]


@dataclass
class BaseHttpClient:
    """
    Provider-agnostic HTTP client wrapper.

    - Uses a single underlying httpx.Client for connection pooling.
    - Provides consistent error handling.
    - Provider-specific clients can subclass and add convenience methods / auth.
    """

    base_url: str
    timeout_s: float = 30.0
    connect_timeout_s: float = 10.0
    headers: Mapping[str, str] = field(default_factory=dict)

    transport: httpx.BaseTransport | None = None

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url.rstrip("/") + "/",
            timeout=httpx.Timeout(self.timeout_s, connect=self.connect_timeout_s),
            headers=dict(self.headers),
            transport=self.transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BaseHttpClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Json:
        """
        Perform an HTTP request and return parsed JSON (dict).
        Raises ProviderRequestError (including ProviderRateLimited) on transport issues / non-2xx.
        """
        try:
            resp = self._client.request(
                method=method,
                url=path.lstrip("/"),
                params=params,
                json=json,
                headers=headers,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise ProviderRequestError(str(e)) from e

        if resp.status_code == 429:
            raise ProviderRateLimited("Provider rate limited the request (HTTP 429).")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ProviderRequestError(
                f"HTTP {resp.status_code} for {method} {resp.request.url}"
            ) from e

        try:
            data = resp.json()
        except ValueError as e:
            raise ProviderRequestError("Response was not valid JSON.") from e

        if not isinstance(data, dict):
            raise ProviderRequestError(f"Expected JSON object, got {type(data)}")

        return data

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Json:
        return self.request_json("GET", path, params=params, headers=headers)
