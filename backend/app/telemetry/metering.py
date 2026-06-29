"""Token + cost metering for orchestration runs.

Every model turn reports token usage (see `LLMResult.usage`). The graph accumulates it across a
run; this module turns token counts into a dollar figure via a per-model price table and provides
a small `UsageTotals` accumulator used by the graph, the runs registry, and per-key metering.

Prices are USD per **million** tokens and are easy to override via `CORENEXIA_MODEL_PRICES`
(JSON: ``{"model-id": {"input": 3.0, "output": 15.0}}``) so deployers can keep them current
without a code change. Unknown models price at $0 and log once, so metering never crashes a run.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass

from app.llm.base import Usage

logger = logging.getLogger("corenexia.metering")

# USD per 1,000,000 tokens. Keep approximate list prices; override via env for accuracy.
# Sources: Anthropic + Google public pricing (as of 2026-06). input/output only.
_DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-opus-4-7": {"input": 5.0, "output": 25.0},
    "claude-opus-4-6": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
}

_PER_MILLION = 1_000_000.0
_warned_models: set[str] = set()


def _load_prices() -> dict[str, dict[str, float]]:
    prices = dict(_DEFAULT_PRICES)
    raw = os.getenv("CORENEXIA_MODEL_PRICES")
    if raw:
        try:
            prices.update(json.loads(raw))
        except (ValueError, TypeError):
            logger.warning("CORENEXIA_MODEL_PRICES is not valid JSON; using built-in prices")
    return prices


def blended_price(model: str) -> float:
    """A single $/Mtok figure for ranking models by cost (weights output 3:1 over input).

    Used by the multi-LLM router to prefer cheaper models. Unknown models rank as 0 (cheapest),
    which is fine — they're treated as free and tried first only if explicitly configured.
    """
    rate = _load_prices().get(model)
    if rate is None:
        return 0.0
    return (rate.get("input", 0.0) + 3 * rate.get("output", 0.0)) / 4


def cost_for(model: str, usage: Usage) -> float:
    """Dollar cost of one turn's tokens for `model`. Unknown models cost $0 (warns once)."""
    prices = _load_prices()
    rate = prices.get(model)
    if rate is None:
        if model and model not in _warned_models:
            _warned_models.add(model)
            logger.warning("No price for model %r; metering it at $0", model)
        return 0.0
    return (
        usage.input_tokens * rate.get("input", 0.0)
        + usage.output_tokens * rate.get("output", 0.0)
    ) / _PER_MILLION


@dataclass
class UsageTotals:
    """Running totals for a single orchestration run, JSON-serialisable for persistence/UI."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, model: str, usage: Usage) -> UsageTotals:
        """Fold one model turn into the totals (in place) and return self."""
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_tokens += usage.cache_read_tokens
        self.cache_write_tokens += usage.cache_write_tokens
        self.cost_usd = round(self.cost_usd + cost_for(model, usage), 6)
        self.llm_calls += 1
        return self

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_tokens"] = self.total_tokens
        return d

    @classmethod
    def from_dict(cls, data: dict | None) -> UsageTotals:
        if not data:
            return cls()
        return cls(
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            cache_read_tokens=int(data.get("cache_read_tokens", 0)),
            cache_write_tokens=int(data.get("cache_write_tokens", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
            llm_calls=int(data.get("llm_calls", 0)),
        )
