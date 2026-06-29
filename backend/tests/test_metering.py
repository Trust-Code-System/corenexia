"""Token + cost metering tests (Initiative B).

Covers the cost table, per-run usage accumulation in the graph, and per-key spend-cap
enforcement (402). No Docker, no API key, no network — scripted provider + fake sandbox.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import admin_router
from app.api.routes import router
from app.gateway.keys import KeyStore
from app.gateway.ratelimit import RateLimiter
from app.llm.base import LLMProvider, LLMResult, Message, TextBlock, ToolUseBlock, Usage
from app.orchestrator.graph import build_orchestrator, run_orchestration
from app.orchestrator.tools import EXECUTE_PYTHON_CODE
from app.telemetry.events import EventBus
from app.telemetry.metering import UsageTotals, cost_for
from tests.test_gateway import ADMIN_TOKEN
from tests.test_graph import FakeSandbox


class UsageReportingProvider(LLMProvider):
    """Calls the tool once then answers; reports token usage on every turn."""

    name = "usage-reporting"

    def __init__(self, model: str = "claude-opus-4-8"):
        self._model = model
        self.call_count = 0

    def complete(self, *, system, messages, tools, max_tokens) -> LLMResult:
        self.call_count += 1
        usage = Usage(input_tokens=1000, output_tokens=500)
        if self.call_count == 1:
            call = ToolUseBlock(id="t1", name=EXECUTE_PYTHON_CODE.name, input={"code": "print(1)"})
            return LLMResult(
                assistant_message=Message(role="assistant", blocks=[call]),
                tool_calls=[call], text="", stop_reason="tool_use",
                usage=usage, model=self._model,
            )
        final = "Done."
        return LLMResult(
            assistant_message=Message(role="assistant", blocks=[TextBlock(text=final)]),
            tool_calls=[], text=final, stop_reason="end_turn",
            usage=usage, model=self._model,
        )


# --- cost table units ----------------------------------------------------


def test_cost_for_known_model():
    # opus 4.8: $5/Mtok in, $25/Mtok out -> 1000*5/1e6 + 500*25/1e6 = 0.005 + 0.0125
    cost = cost_for("claude-opus-4-8", Usage(input_tokens=1000, output_tokens=500))
    assert round(cost, 6) == 0.0175


def test_cost_for_unknown_model_is_zero():
    assert cost_for("no-such-model", Usage(input_tokens=10_000, output_tokens=10_000)) == 0.0


def test_usage_totals_roundtrip_and_accumulate():
    totals = UsageTotals()
    totals.add("claude-opus-4-8", Usage(input_tokens=1000, output_tokens=500))
    totals.add("claude-opus-4-8", Usage(input_tokens=1000, output_tokens=500))
    assert totals.input_tokens == 2000
    assert totals.output_tokens == 1000
    assert totals.llm_calls == 2
    assert round(totals.cost_usd, 6) == 0.035
    # survives a dict round-trip (persistence shape)
    again = UsageTotals.from_dict(totals.to_dict())
    assert again.cost_usd == totals.cost_usd
    assert again.total_tokens == 3000


# --- graph accumulation --------------------------------------------------


def test_graph_accumulates_usage():
    sandbox = FakeSandbox(stdout="1")
    app = build_orchestrator(UsageReportingProvider(), sandbox)
    final = run_orchestration(app, "Anything")
    usage = final["usage"]
    # Two LLM turns (tool call + final answer), each 1000 in / 500 out.
    assert usage["llm_calls"] == 2
    assert usage["input_tokens"] == 2000
    assert usage["output_tokens"] == 1000
    assert round(usage["cost_usd"], 6) == 0.035


# --- spend-cap enforcement (402) -----------------------------------------


def _capped_app(tmp_path) -> FastAPI:
    provider = UsageReportingProvider()
    sandbox = FakeSandbox(stdout="1")
    app = FastAPI()
    app.state.bus = EventBus()
    app.state.runs = None
    app.state.auth_enabled = True
    app.state.admin_token = ADMIN_TOKEN
    app.state.keys = KeyStore(str(tmp_path / "keys.db"))
    app.state.rate_limiter = RateLimiter(0)  # disabled
    app.state.provider = provider
    app.state.sandbox = sandbox
    app.state.sandbox_ready = True
    app.state.sandbox_message = "fake"
    app.state.orchestrator = build_orchestrator(provider, sandbox, app.state.bus)
    app.include_router(router)
    app.include_router(admin_router)
    return app


def test_spend_cap_blocks_with_402(tmp_path):
    app = _capped_app(tmp_path)
    with TestClient(app) as client:
        admin = {"X-Admin-Token": ADMIN_TOKEN}
        created = client.post("/admin/keys", json={"name": "capped"}, headers=admin)
        key_id = created.json()["id"]
        api_key = created.json()["api_key"]
        auth = {"Authorization": f"Bearer {api_key}"}

        # Set a tiny cap, then push recorded cost past it.
        assert client.put(
            f"/admin/keys/{key_id}/spend-cap", json={"spend_cap_usd": 0.01}, headers=admin
        ).status_code == 200
        app.state.keys.add_usage(key_id, input_tokens=0, output_tokens=0, cost_usd=0.02)

        # New orchestration is blocked.
        blocked = client.post("/v1/orchestrate", json={"query": "x"}, headers=auth)
        assert blocked.status_code == 402

        # Clearing the cap re-opens the key and a run reports usage.
        assert client.put(
            f"/admin/keys/{key_id}/spend-cap", json={"spend_cap_usd": None}, headers=admin
        ).status_code == 200
        ok = client.post("/v1/orchestrate", json={"query": "x"}, headers=auth)
        assert ok.status_code == 200
        assert ok.json()["usage"]["cost_usd"] > 0

        # The run's cost was metered onto the key.
        listed = client.get("/admin/keys", headers=admin).json()
        rec = next(k for k in listed if k["id"] == key_id)
        assert rec["cost_usd"] > 0.02
