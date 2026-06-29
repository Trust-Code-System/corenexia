"""LLM provider abstraction. Default is Anthropic (Claude); Gemini is stubbed."""

from app.config import settings
from app.llm.base import LLMProvider


def build_provider() -> LLMProvider:
    """Construct the configured provider. Selected by `settings.llm_provider`."""
    provider = settings.llm_provider.lower()
    if provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if provider == "gemini":
        from app.llm.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise ValueError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use 'anthropic' or 'gemini'."
    )
