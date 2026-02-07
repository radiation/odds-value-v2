from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .adapter import ProviderAdapter
from .errors import ProviderCapabilityError


@dataclass(frozen=True)
class AdapterKey:
    provider: str
    league_key: str


AdapterFactory = Callable[[], ProviderAdapter]


class AdapterRegistry:
    def __init__(self) -> None:
        self._factories: dict[AdapterKey, AdapterFactory] = {}

    def register(self, key: AdapterKey, factory: AdapterFactory) -> None:
        if key in self._factories:
            raise ValueError(f"Duplicate adapter registration: {key}")
        self._factories[key] = factory

    def get(self, *, provider: str, league_key: str) -> ProviderAdapter:
        # Try exact match first.
        key = AdapterKey(provider=provider, league_key=league_key)
        factory = self._factories.get(key)

        # Fallback: allow league-agnostic adapter for a sport.
        if factory is None and league_key is not None:
            key2 = AdapterKey(provider=provider, league_key=league_key)
            factory = self._factories.get(key2)

        if factory is None:
            raise ProviderCapabilityError(
                f"No adapter registered for provider={provider} league_key={league_key}"
            )

        return factory()
