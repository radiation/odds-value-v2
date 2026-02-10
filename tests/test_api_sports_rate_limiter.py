from __future__ import annotations

from typing import Any

from odds_value.ingestion.providers.api_sports.client import ApiSportsClient, ApiSportsRateLimiter
from odds_value.ingestion.providers.base.client import BaseHttpClient


def test_api_sports_rate_limiter_paces_requests() -> None:
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    t = 0.0

    def fake_monotonic() -> float:
        return t

    limiter = ApiSportsRateLimiter(_sleep=fake_sleep, _monotonic=fake_monotonic)
    limiter.min_interval_s = 1.0
    limiter.last_request_monotonic = 0.0

    t = 0.25
    limiter.before_request()
    assert sleeps == [0.75]


def test_api_sports_rate_limiter_uses_headers_for_minute_cooldown() -> None:
    sleeps: list[float] = []

    limiter = ApiSportsRateLimiter(
        _sleep=lambda s: sleeps.append(s),
        _monotonic=lambda: 123.0,
        minute_limit_low_watermark=2,
    )

    limiter.after_response({"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "1"})
    assert limiter.min_interval_s > 0.0
    assert 60.0 in sleeps


def test_api_sports_client_reads_rate_limit_headers() -> None:
    class DummyHttp(BaseHttpClient):
        def __init__(self) -> None:
            pass

        def get_json_with_headers(
            self, path: str, *, params: Any | None = None, headers: Any | None = None
        ) -> tuple[dict[str, Any], dict[str, str]]:
            return {"response": [], "errors": []}, {
                "X-RateLimit-Limit": "300",
                "X-RateLimit-Remaining": "299",
            }

    client = ApiSportsClient(http=DummyHttp(), api_key="k")
    # Should not raise; should update limiter min_interval.
    client.get("/games")
    assert client.rate_limiter.min_interval_s > 0.0
