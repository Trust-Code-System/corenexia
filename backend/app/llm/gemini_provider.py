"""Gemini (Google GenAI) provider.

Implements the normalized `LLMProvider` against the `google-genai` SDK, proving the abstraction is
multi-vendor. Translation to/from Gemini's format is done with plain dicts (which the SDK coerces),
so the message/tool/response mapping is unit-testable without the SDK or a live call.

The SDK is imported lazily inside `complete()` so the dependency is only needed when
`LLM_PROVIDER=gemini`. Live verification requires `GOOGLE_API_KEY` and spends money (user-gated).
"""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.llm.base import (
    LLMProvider,
    LLMResult,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    Usage,
)

# JSON-Schema keys Gemini's function-declaration schema does not accept; stripped before sending.
_UNSUPPORTED_SCHEMA_KEYS = ("additionalProperties", "$schema")


def _sanitize_schema(schema: dict) -> dict:
    """Recursively drop schema keywords the Gemini function-declaration format rejects."""
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _UNSUPPORTED_SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {k: _sanitize_schema(v) for k, v in value.items()}
        elif isinstance(value, dict):
            out[key] = _sanitize_schema(value)
        else:
            out[key] = value
    return out


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or settings.google_api_key
        self._model = model or settings.gemini_model

    # --- translation (pure, testable) -----------------------------------

    @staticmethod
    def _id_to_name(messages: list[Message]) -> dict[str, str]:
        """Map each tool_use id to its function name (Gemini keys responses by name, not id)."""
        mapping: dict[str, str] = {}
        for msg in messages:
            for block in msg.blocks:
                if isinstance(block, ToolUseBlock):
                    mapping[block.id] = block.name
        return mapping

    @classmethod
    def _to_contents(cls, messages: list[Message]) -> list[dict]:
        names = cls._id_to_name(messages)
        contents: list[dict] = []
        for msg in messages:
            role = "model" if msg.role == "assistant" else "user"
            parts: list[dict] = []
            for block in msg.blocks:
                if isinstance(block, TextBlock):
                    if block.text:
                        parts.append({"text": block.text})
                elif isinstance(block, ToolUseBlock):
                    parts.append({"function_call": {"name": block.name, "args": block.input}})
                elif isinstance(block, ToolResultBlock):
                    parts.append({
                        "function_response": {
                            "name": names.get(block.tool_use_id, block.tool_use_id),
                            "response": cls._response_payload(block.content),
                        }
                    })
            if parts:
                contents.append({"role": role, "parts": parts})
        return contents

    @staticmethod
    def _response_payload(content: str) -> dict:
        """Gemini function responses must be objects; wrap raw/JSON tool output accordingly."""
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return {"output": content}
        return parsed if isinstance(parsed, dict) else {"output": parsed}

    @staticmethod
    def _to_tools(tools: list[ToolSpec]) -> list[dict]:
        return [{
            "function_declarations": [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": _sanitize_schema(t.input_schema),
                }
                for t in tools
            ]
        }]

    def _parse_response(self, response) -> LLMResult:
        """Parse a (duck-typed) Gemini response into the normalized result."""
        blocks: list = []
        tool_calls: list[ToolUseBlock] = []
        text_parts: list[str] = []

        candidates = getattr(response, "candidates", None) or []
        if candidates:
            content = getattr(candidates[0], "content", None)
            for part in (getattr(content, "parts", None) or []):
                fc = getattr(part, "function_call", None)
                text = getattr(part, "text", None)
                if fc is not None:
                    args = dict(getattr(fc, "args", {}) or {})
                    call = ToolUseBlock(id=fc.name, name=fc.name, input=args)
                    blocks.append(call)
                    tool_calls.append(call)
                elif text:
                    blocks.append(TextBlock(text=text))
                    text_parts.append(text)

        meta = getattr(response, "usage_metadata", None)
        usage = Usage(
            input_tokens=getattr(meta, "prompt_token_count", 0) or 0,
            output_tokens=getattr(meta, "candidates_token_count", 0) or 0,
        )
        finish = ""
        if candidates:
            finish = str(getattr(candidates[0], "finish_reason", "") or "")
        assistant = Message(role="assistant", blocks=blocks, raw=None)
        return LLMResult(
            assistant_message=assistant,
            tool_calls=tool_calls,
            text="".join(text_parts),
            stop_reason=finish,
            usage=usage,
            model=getattr(response, "model_version", "") or self._model,
        )

    # --- live call ------------------------------------------------------

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResult:
        from google import genai  # lazy import — only needed when this provider runs

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self._model,
            contents=self._to_contents(messages),
            config={
                "system_instruction": system,
                "tools": self._to_tools(tools),
                "max_output_tokens": max_tokens,
            },
        )
        return self._parse_response(response)
