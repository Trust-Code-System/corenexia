"""Gemini provider translation tests (Initiative D). No SDK call, no network, no live LLM.

Exercises the message/tool/response mapping with plain data + duck-typed fakes. A real
generate_content call needs GOOGLE_API_KEY and is user-gated (not exercised here).
"""

from __future__ import annotations

from types import SimpleNamespace

from app.llm.base import (
    Message,
    TextBlock,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
)
from app.llm.gemini_provider import GeminiProvider, _sanitize_schema


def test_sanitize_schema_strips_unsupported_keys():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"code": {"type": "string", "additionalProperties": False}},
    }
    out = _sanitize_schema(schema)
    assert "additionalProperties" not in out
    assert "additionalProperties" not in out["properties"]["code"]
    assert out["properties"]["code"]["type"] == "string"


def test_to_tools_shape():
    tool = ToolSpec(name="run", description="d", input_schema={"type": "object", "properties": {}})
    tools = GeminiProvider._to_tools([tool])
    decl = tools[0]["function_declarations"][0]
    assert decl["name"] == "run"
    assert decl["parameters"]["type"] == "object"


def test_to_contents_roles_and_function_call_response_pairing():
    messages = [
        Message("user", [TextBlock("hello")]),
        Message("assistant", [ToolUseBlock(id="tool_1", name="run", input={"x": 1})]),
        Message("user", [ToolResultBlock(tool_use_id="tool_1", content='{"ok": true}')]),
    ]
    contents = GeminiProvider._to_contents(messages)
    assert contents[0] == {"role": "user", "parts": [{"text": "hello"}]}
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["function_call"] == {"name": "run", "args": {"x": 1}}
    # the tool result is keyed back to the function *name*, not the id, and parsed to an object
    fr = contents[2]["parts"][0]["function_response"]
    assert fr["name"] == "run"
    assert fr["response"] == {"ok": True}


def test_response_payload_wraps_non_object():
    assert GeminiProvider._response_payload("plain text") == {"output": "plain text"}
    assert GeminiProvider._response_payload("[1, 2]") == {"output": [1, 2]}
    assert GeminiProvider._response_payload('{"a": 1}') == {"a": 1}


def _fake_response(*, parts, prompt_tokens=10, out_tokens=5, model="gemini-2.5-pro"):
    content = SimpleNamespace(parts=parts)
    candidate = SimpleNamespace(content=content, finish_reason="STOP")
    meta = SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=out_tokens)
    return SimpleNamespace(candidates=[candidate], usage_metadata=meta, model_version=model)


def test_parse_response_text_and_usage():
    provider = GeminiProvider(api_key="x")
    resp = _fake_response(parts=[SimpleNamespace(text="the answer", function_call=None)])
    result = provider._parse_response(resp)
    assert result.text == "the answer"
    assert not result.tool_calls
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5
    assert result.model == "gemini-2.5-pro"


def test_parse_response_function_call():
    provider = GeminiProvider(api_key="x")
    fc = SimpleNamespace(name="run", args={"code": "print(1)"})
    resp = _fake_response(parts=[SimpleNamespace(text=None, function_call=fc)])
    result = provider._parse_response(resp)
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.name == "run"
    assert call.input == {"code": "print(1)"}
