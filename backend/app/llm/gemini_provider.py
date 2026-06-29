"""Gemini provider — seam for a later milestone.

Implementing this means translating normalized Messages/ToolSpecs to the Google GenAI
function-calling format and back. Kept as an explicit stub so the provider abstraction is proven
to be pluggable without pulling in the dependency now.
"""

from __future__ import annotations

from app.llm.base import LLMProvider, LLMResult, Message, ToolSpec


class GeminiProvider(LLMProvider):
    name = "gemini"

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResult:
        raise NotImplementedError(
            "GeminiProvider is not implemented in Milestone 1. "
            "Set LLM_PROVIDER=anthropic, or implement this provider against the Google GenAI SDK."
        )
