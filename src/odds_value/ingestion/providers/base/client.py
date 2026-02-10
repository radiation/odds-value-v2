from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

import httpx

from .errors import ProviderRateLimited, ProviderRequestError

Json = dict[str, Any]
JsonValue = object


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

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            return self._client.request(
                method=method,
                url=path.lstrip("/"),
                params=params,
                json=json,
                headers=headers,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise ProviderRequestError(str(e)) from e

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
        resp = self._request(method, path, params=params, json=json, headers=headers)

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

    def request_json_value(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonValue:
        """Perform an HTTP request and return parsed JSON (any JSON type).

        Some providers (e.g., The Odds API) return top-level JSON arrays.
        This method keeps transport + status handling consistent with `request_json`.
        """

        resp = self._request(method, path, params=params, json=json, headers=headers)

        if resp.status_code == 429:
            raise ProviderRateLimited("Provider rate limited the request (HTTP 429).")

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ProviderRequestError(
                f"HTTP {resp.status_code} for {method} {resp.request.url}"
            ) from e

        try:
            return resp.json()
        except ValueError as e:
            raise ProviderRequestError("Response was not valid JSON.") from e

    def get_json_value(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonValue:
        return self.request_json_value("GET", path, params=params, headers=headers)

    def request_json_with_headers(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[Json, httpx.Headers]:
        """Like `request_json`, but also returns response headers."""

        resp = self._request(method, path, params=params, json=json, headers=headers)

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

        return data, resp.headers

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Json:
        return self.request_json("GET", path, params=params, headers=headers)

    def get_json_with_headers(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[Json, httpx.Headers]:
        return self.request_json_with_headers("GET", path, params=params, headers=headers)
