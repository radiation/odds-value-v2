from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from odds_value.ingestion.providers.base.client import BaseHttpClient
from odds_value.ingestion.providers.base.errors import ProviderRateLimited, ProviderResponseError


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ApiSportsRateLimiter:
    """Proactive throttling based on API-Sports rate limit headers.

    The provider returns per-minute limit/remaining headers; we use them to pace
    requests and avoid hitting HTTP 429 during ingestion.
    """

    minute_limit_low_watermark: int = 2
    min_interval_s: float = 0.0
    last_request_monotonic: float | None = None

    _sleep: Any = field(default=time.sleep, repr=False)
    _monotonic: Any = field(default=time.monotonic, repr=False)

    def before_request(self) -> None:
        if self.min_interval_s <= 0.0:
            return
        now = float(self._monotonic())
        if self.last_request_monotonic is None:
            return
        elapsed = now - self.last_request_monotonic
        remaining = self.min_interval_s - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def after_response(self, headers: Mapping[str, str]) -> None:
        # Update pacing based on plan limit.
        limit = _parse_int(headers.get("X-RateLimit-Limit"))
        remaining = _parse_int(headers.get("X-RateLimit-Remaining"))

        if limit and limit > 0:
            self.min_interval_s = max(self.min_interval_s, 60.0 / float(limit))

        # If we're close to exhausting the minute bucket (or another process is
        # sharing the same key), add a cooldown.
        if remaining is not None and remaining <= self.minute_limit_low_watermark:
            # With no explicit reset header, the safest practical cooldown is a
            # full minute when we are at/near zero.
            cooldown = 60.0 if remaining <= 1 else 10.0
            self._sleep(cooldown)

        self.last_request_monotonic = float(self._monotonic())


@dataclass
class ApiSportsClient:
    http: BaseHttpClient
    api_key: str
    rate_limiter: ApiSportsRateLimiter = field(default_factory=ApiSportsRateLimiter)

    def _headers(self) -> dict[str, str]:
        return {"x-apisports-key": self.api_key}

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        # Proactively pace requests based on most recently observed limit.
        self.rate_limiter.before_request()

        # Basic retry on minute-bucket throttling.
        attempts = 0
        while True:
            attempts += 1
            try:
                data, headers = self.http.get_json_with_headers(
                    path, params=params, headers=self._headers()
                )
                self.rate_limiter.after_response(headers)
                break
            except ProviderRateLimited:
                # No reset header is guaranteed; sleep a full bucket and retry.
                if attempts >= 5:
                    raise
                time.sleep(60.0)

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
