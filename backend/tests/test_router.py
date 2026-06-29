"""Multi-LLM routing tests (Initiative D). No network, no live LLM."""

from __future__ import annotations

import pytest

from app.llm.base import LLMProvider, LLMResult, Message, TextBlock
from app.llm.router import (
    STRATEGY_COST,
    STRATEGY_FALLBACK,
    ProviderRoute,
    RoutingProvider,
)


class _Fake(LLMProvider):
    def __init__(self, label: str, *, fail: bool = False):
        self.name = label
        self._fail = fail
        self.calls = 0

    def complete(self, *, system, messages, tools, max_tokens) -> LLMResult:
        self.calls += 1
        if self._fail:
            raise RuntimeError(f"{self.name} is down")
        return LLMResult(
            assistant_message=Message("assistant", [TextBlock(self.name)]),
            text=self.name, stop_reason="end_turn", model=self.name,
        )


def _route(label, *, fail=False, cost=0.0):
    return ProviderRoute(provider=_Fake(label, fail=fail), label=label, cost=cost)


def _run(router: RoutingProvider) -> LLMResult:
    return router.complete(system="s", messages=[], tools=[], max_tokens=10)


def test_fallback_uses_primary_when_healthy():
    router = RoutingProvider([_route("a"), _route("b")], strategy=STRATEGY_FALLBACK)
    assert _run(router).text == "a"
    assert router.last_used == "a"


def test_fallback_fails_over_to_next_on_error():
    a, b = _route("a", fail=True), _route("b")
    router = RoutingProvider([a, b], strategy=STRATEGY_FALLBACK)
    result = _run(router)
    assert result.text == "b"
    assert router.last_used == "b"
    assert a.provider.calls == 1 and b.provider.calls == 1


def test_cost_strategy_prefers_cheapest():
    expensive = _route("expensive", cost=25.0)
    cheap = _route("cheap", cost=1.0)
    # listed expensive-first, but cost strategy must pick the cheap one
    router = RoutingProvider([expensive, cheap], strategy=STRATEGY_COST)
    assert _run(router).text == "cheap"


def test_cost_strategy_still_fails_over():
    cheap_broken = _route("cheap", fail=True, cost=1.0)
    pricey_ok = _route("pricey", cost=25.0)
    router = RoutingProvider([cheap_broken, pricey_ok], strategy=STRATEGY_COST)
    assert _run(router).text == "pricey"  # cheapest tried first, failed, fell over


def test_all_providers_failing_raises():
    router = RoutingProvider([_route("a", fail=True), _route("b", fail=True)])
    with pytest.raises(RuntimeError, match="All 2 routed providers failed"):
        _run(router)


def test_empty_routes_rejected():
    with pytest.raises(ValueError):
        RoutingProvider([])
