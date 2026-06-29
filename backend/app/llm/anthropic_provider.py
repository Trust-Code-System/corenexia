"""Anthropic (Claude) provider — the default orchestrator brain.

Built per the `claude-api` skill: model `claude-opus-4-8` with adaptive thinking, and a manual
tool-use round-trip. Thinking blocks are preserved in the assistant turn's `raw` payload and
replayed unchanged on the next request, as required when continuing on the same model.
"""

from __future__ import annotations

import anthropic

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


def _usage_from_response(response) -> Usage:
    """Read token counts off an Anthropic response (fields may be absent on older SDKs)."""
    raw = getattr(response, "usage", None)
    if raw is None:
        return Usage()
    return Usage(
        input_tokens=getattr(raw, "input_tokens", 0) or 0,
        output_tokens=getattr(raw, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
    )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        # If api_key is None the SDK resolves it from ANTHROPIC_API_KEY / the environment.
        # The SDK auto-retries 429/5xx/connection errors with backoff; we set the budget here.
        self._client = anthropic.Anthropic(
            api_key=api_key or settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        self._model = model or settings.anthropic_model

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResult:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            tools=[self._tool_to_api(t) for t in tools],
            messages=[self._message_to_api(m) for m in messages],
        )

        # `refusal` arrives as HTTP 200 — check before reading content.
        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            explanation = getattr(detail, "explanation", "request was declined for safety reasons")
            assistant = Message(role="assistant", blocks=[TextBlock(text=explanation)],
                                raw=response.content)
            return LLMResult(
                assistant_message=assistant,
                text=explanation,
                stop_reason="refusal",
                usage=_usage_from_response(response),
                model=getattr(response, "model", self._model),
            )

        normalized_blocks: list = []
        tool_calls: list[ToolUseBlock] = []
        text_parts: list[str] = []
        for block in response.content:
            if block.type == "text":
                normalized_blocks.append(TextBlock(text=block.text))
                text_parts.append(block.text)
            elif block.type == "tool_use":
                # block.input is already-parsed JSON from the SDK.
                call = ToolUseBlock(id=block.id, name=block.name, input=dict(block.input))
                normalized_blocks.append(call)
                tool_calls.append(call)
            # thinking / other blocks are not normalized but are preserved in `raw` below.

        assistant = Message(
            role="assistant",
            blocks=normalized_blocks,
            raw=response.content,  # replayed verbatim so thinking blocks survive the round-trip
        )
        return LLMResult(
            assistant_message=assistant,
            tool_calls=tool_calls,
            text="".join(text_parts),
            stop_reason=response.stop_reason or "",
            usage=_usage_from_response(response),
            model=getattr(response, "model", self._model),
        )

    # --- translation helpers ------------------------------------------------

    @staticmethod
    def _tool_to_api(tool: ToolSpec) -> dict:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }

    @staticmethod
    def _message_to_api(message: Message) -> dict:
        # Replay assistant turns verbatim to preserve thinking/tool_use blocks.
        if message.role == "assistant" and message.raw is not None:
            return {"role": "assistant", "content": message.raw}

        content: list[dict] = []
        for block in message.blocks:
            if isinstance(block, TextBlock):
                content.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
            elif isinstance(block, ToolResultBlock):
                content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": block.content,
                        "is_error": block.is_error,
                    }
                )
        return {"role": message.role, "content": content}
