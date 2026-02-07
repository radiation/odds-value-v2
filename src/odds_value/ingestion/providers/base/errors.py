from __future__ import annotations

from dataclasses import dataclass


class ProviderError(RuntimeError):
    """Base exception for provider-related failures."""


class ProviderRequestError(ProviderError):
    """HTTP/network/transport layer failures (timeouts, connection errors, non-2xx, etc.)."""


class ProviderRateLimited(ProviderRequestError):
    """Provider throttled the request (e.g., HTTP 429)."""


class ProviderResponseError(ProviderError):
    """Provider returned a well-formed response indicating an application-level error."""


class ProviderCapabilityError(ProviderError):
    """Adapter does not support a requested operation."""


@dataclass(frozen=True)
class ProviderMappingError(ProviderError):
    """Mapping/extraction failed due to unexpected schema or values."""
    message: str
    context: dict[str, object] | None = None

    def __str__(self) -> str:  # pragma: no cover
        if not self.context:
            return self.message
        return f"{self.message} | context={self.context}"
