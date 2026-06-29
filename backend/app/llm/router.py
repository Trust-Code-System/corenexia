"""Multi-LLM routing (Initiative D).

`RoutingProvider` wraps several `LLMProvider`s and picks one per call, with automatic failover to
the next candidate on error. Two strategies:

  * ``fallback`` — try providers in the configured order (primary first), fall back on failure.
  * ``cost``     — order by a blended $/Mtok estimate (cheapest first), then fall back on failure.

It implements the `LLMProvider` interface, so the orchestrator graph uses it transparently. The
chosen provider's own `LLMResult.model`/`usage` flow through to metering and telemetry unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.llm.base import LLMProvider, LLMResult, Message, ToolSpec

logger = logging.getLogger("corenexia.router")

STRATEGY_FALLBACK = "fallback"
STRATEGY_COST = "cost"


@dataclass
class ProviderRoute:
    provider: LLMProvider
    label: str
    cost: float = 0.0  # blended $/Mtok estimate, for the "cost" strategy


class RoutingProvider(LLMProvider):
    name = "router"

    def __init__(self, routes: list[ProviderRoute], strategy: str = STRATEGY_FALLBACK):
        if not routes:
            raise ValueError("RoutingProvider needs at least one route.")
        self._routes = routes
        self._strategy = strategy if strategy in (STRATEGY_FALLBACK, STRATEGY_COST) else \
            STRATEGY_FALLBACK
        # Record which provider served the last call (handy for tests/telemetry).
        self.last_used: str | None = None

    def _ordered(self) -> list[ProviderRoute]:
        if self._strategy == STRATEGY_COST:
            return sorted(self._routes, key=lambda r: r.cost)
        return list(self._routes)

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResult:
        ordered = self._ordered()
        last_error: Exception | None = None
        for route in ordered:
            try:
                result = route.provider.complete(
                    system=system, messages=messages, tools=tools, max_tokens=max_tokens
                )
                self.last_used = route.label
                return result
            except Exception as exc:  # noqa: BLE001 — try the next provider
                last_error = exc
                logger.warning("provider '%s' failed (%s); failing over", route.label, exc)
        raise RuntimeError(
            f"All {len(ordered)} routed providers failed; last error: {last_error}"
        ) from last_error
