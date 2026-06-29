"""Provider-agnostic LLM interface.

The orchestrator speaks in normalized content blocks so the LangGraph loop never depends on a
specific vendor's message format. Each provider translates these to/from its native shape.
Assistant turns also carry an opaque `raw` payload (the provider's native content) so that
provider-specific blocks — e.g. Claude's thinking blocks — can be replayed verbatim on the next
turn without the graph having to understand them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool = False


Block = TextBlock | ToolUseBlock | ToolResultBlock


@dataclass
class Message:
    role: Literal["user", "assistant"]
    blocks: list[Block]
    # Provider-native content for an assistant turn, replayed verbatim on the next request.
    raw: Any = None


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class Usage:
    """Token accounting for one model turn. Providers populate what they report."""

    input_tokens: int = 0
    output_tokens: int = 0
    # Cache-related token counts (Anthropic prompt caching); informational.
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResult:
    """One model turn, normalized."""

    assistant_message: Message
    tool_calls: list[ToolUseBlock] = field(default_factory=list)
    text: str = ""
    stop_reason: str = ""
    # Per-turn token usage; defaults to zero for providers/fakes that don't report it.
    usage: Usage = field(default_factory=Usage)
    # The model id that produced this turn (for cost attribution).
    model: str = ""


class LLMProvider(ABC):
    """A pluggable LLM backend. Implementations translate normalized messages to native calls."""

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResult:
        """Run one model turn and return the normalized result."""
        raise NotImplementedError
