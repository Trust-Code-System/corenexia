"""SSE streaming endpoint test (Initiative D). No Docker (fake sandbox), no live LLM."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_gateway import make_app


def test_orchestrate_stream_emits_phases_and_result(tmp_path):
    app = make_app(tmp_path, auth_enabled=False)  # ScriptedProvider + FakeSandbox
    with TestClient(app) as client:
        with client.stream("POST", "/v1/orchestrate/stream", json={"query": "law?"}) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = "".join(resp.iter_text())

    # The stream carries the run lifecycle and a final result event with the answer.
    assert "event: start" in body
    assert "event: done" in body
    assert "event: result" in body
    assert "Delaware" in body  # ScriptedProvider's final answer
