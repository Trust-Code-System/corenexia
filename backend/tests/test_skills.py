"""Reusable skills tests (Initiative D). No Docker, no API key, no network."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills import skills_router
from app.llm.base import LLMProvider, LLMResult, Message, TextBlock, ToolUseBlock
from app.orchestrator.graph import build_orchestrator, run_orchestration
from app.orchestrator.skills import InvalidSkillName, SkillStore
from app.orchestrator.tools import LOAD_SKILL, SAVE_SKILL
from tests.test_graph import FakeSandbox


def _tool_result(call: ToolUseBlock) -> LLMResult:
    return LLMResult(Message("assistant", [call]), tool_calls=[call], stop_reason="tool_use")


# --- store units ---------------------------------------------------------


def test_store_save_get_list_search_delete(tmp_path):
    store = SkillStore(str(tmp_path / "skills.db"))
    store.save("parse-nda", "Parse an NDA into JSON", "print('nda')", tags=["legal"])
    store.save("cagr", "Compute CAGR", "print('cagr')", tags=["finance"])

    assert store.get("parse-nda").code == "print('nda')"
    assert {s.name for s in store.list()} == {"parse-nda", "cagr"}
    assert [s.name for s in store.search("legal")] == ["parse-nda"]
    assert "parse-nda" in store.catalog()

    # upsert keeps created_at, updates code
    first = store.get("parse-nda").created_at
    store.save("parse-nda", "Parse an NDA into JSON v2", "print('nda2')")
    assert store.get("parse-nda").code == "print('nda2')"
    assert store.get("parse-nda").created_at == first

    assert store.delete("cagr") is True
    assert store.get("cagr") is None


def test_store_rejects_bad_name(tmp_path):
    store = SkillStore(str(tmp_path / "s.db"))
    with pytest.raises(InvalidSkillName):
        store.save("bad name!", "x", "y")


# --- agent flow through the graph ---------------------------------------


class SaveThenLoadProvider(LLMProvider):
    """Turn 1: save a skill. Turn 2: load it. Turn 3: answer with the loaded code."""

    name = "save-load"

    def __init__(self):
        self.calls = 0
        self.loaded_code: str | None = None

    def complete(self, *, system, messages, tools, max_tokens) -> LLMResult:
        self.calls += 1
        if self.calls == 1:
            assert any(t.name == SAVE_SKILL.name for t in tools)  # tools exposed when skills wired
            assert "Reusable skills" in system
            call = ToolUseBlock(id="s1", name=SAVE_SKILL.name,
                                input={"name": "greet", "description": "say hi",
                                       "code": "print('hi')", "tags": ["demo"]})
            return _tool_result(call)
        if self.calls == 2:
            assert "greet" in system  # catalog now shows the saved skill
            call = ToolUseBlock(id="l1", name=LOAD_SKILL.name, input={"name": "greet"})
            return _tool_result(call)
        # capture what came back from load_skill
        last = messages[-1]
        self.loaded_code = last.blocks[0].content
        final = "Loaded and done."
        return LLMResult(Message("assistant", [TextBlock(final)]), text=final,
                         stop_reason="end_turn")


def test_agent_can_save_and_load_a_skill(tmp_path):
    store = SkillStore(str(tmp_path / "skills.db"))
    provider = SaveThenLoadProvider()
    app = build_orchestrator(provider, FakeSandbox(stdout="x"), skills=store)

    final = run_orchestration(app, "Save and reuse a greeting", max_iterations=5)

    assert final["status"] == "done"
    assert store.get("greet") is not None          # persisted by the agent
    assert store.get("greet").use_count == 1        # load_skill recorded a use
    assert "print('hi')" in provider.loaded_code    # load_skill returned the saved code


def test_skills_absent_keeps_single_tool_behavior():
    # Without a SkillStore, only execute_python_code is exposed (back-compat).
    seen_tools = {}

    class Probe(LLMProvider):
        name = "probe"

        def complete(self, *, system, messages, tools, max_tokens):
            seen_tools["names"] = {t.name for t in tools}
            seen_tools["system"] = system
            return LLMResult(Message("assistant", [TextBlock("ok")]), text="ok",
                             stop_reason="end_turn")

    app = build_orchestrator(Probe(), FakeSandbox(stdout="x"))  # no skills
    run_orchestration(app, "hi")
    assert seen_tools["names"] == {"execute_python_code"}
    assert "Reusable skills" not in seen_tools["system"]


# --- REST API ------------------------------------------------------------


def _api(tmp_path) -> TestClient:
    app = FastAPI()
    app.state.auth_enabled = False
    app.state.skills = SkillStore(str(tmp_path / "skills.db"))
    app.include_router(skills_router)
    return TestClient(app)


def test_skills_rest_crud(tmp_path):
    client = _api(tmp_path)
    # create
    r = client.post("/v1/skills", json={"name": "cagr", "description": "Compute CAGR",
                                        "code": "print(1)", "tags": ["finance"]})
    assert r.status_code == 201
    # list (summaries, no code)
    listing = client.get("/v1/skills").json()
    assert listing[0]["name"] == "cagr"
    assert "code" not in listing[0]
    # get one (full, with code)
    one = client.get("/v1/skills/cagr").json()
    assert one["code"] == "print(1)"
    # filter
    assert client.get("/v1/skills", params={"q": "finance"}).json()
    assert client.get("/v1/skills", params={"q": "nope"}).json() == []
    # bad name rejected
    assert client.post("/v1/skills", json={"name": "x y", "description": "d",
                                           "code": "c"}).status_code == 400
    # delete
    assert client.delete("/v1/skills/cagr").status_code == 204
    assert client.get("/v1/skills/cagr").status_code == 404
