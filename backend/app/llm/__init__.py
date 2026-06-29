"""LLM provider abstraction. Default is Anthropic (Claude); Gemini is implemented; an optional
multi-LLM router (Initiative D) can wrap several providers with cost-aware failover."""

from app.config import settings
from app.llm.base import LLMProvider


def _build_single(name: str) -> LLMProvider:
    name = name.lower()
    if name == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if name == "gemini":
        from app.llm.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise ValueError(f"Unknown LLM provider '{name}'. Use 'anthropic' or 'gemini'.")


def _model_for(name: str) -> str:
    return settings.anthropic_model if name == "anthropic" else settings.gemini_model


def build_provider() -> LLMProvider:
    """Construct the configured provider, or a multi-LLM router when routing is enabled."""
    if settings.llm_routing_enabled:
        from app.llm.router import ProviderRoute, RoutingProvider
        from app.telemetry.metering import blended_price

        routes = [
            ProviderRoute(provider=_build_single(n), label=n, cost=blended_price(_model_for(n)))
            for n in settings.llm_routing_provider_list
        ]
        return RoutingProvider(routes, strategy=settings.llm_routing_strategy)

    return _build_single(settings.llm_provider)
