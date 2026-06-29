"""Central configuration. Single source of truth for provider selection and sandbox limits."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loaded from environment / `.env`. See `.env.example` for documentation."""

    # LLM provider
    llm_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.5-pro"
    llm_max_tokens: int = 8000
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2

    # Multi-LLM routing (Initiative D). When enabled, the orchestrator runs behind a router that
    # picks among these providers and fails over on error. Strategy: "fallback" (in order) or
    # "cost" (cheapest first). Each provider still needs its own key configured.
    llm_routing_enabled: bool = False
    llm_routing_providers: str = "anthropic,gemini"  # comma-separated, in priority order
    llm_routing_strategy: str = "fallback"  # "fallback" | "cost"

    @property
    def llm_routing_provider_list(self) -> list[str]:
        return [p.strip().lower() for p in self.llm_routing_providers.split(",") if p.strip()]

    # Sandbox (Docker)
    sandbox_image: str = "corenexia-sandbox"
    sandbox_memory: str = "512m"
    sandbox_cpus: float = 1.0
    sandbox_pids_limit: int = 128
    sandbox_timeout_seconds: int = 30
    sandbox_max_concurrency: int = 4  # max simultaneous sandbox containers
    # Isolation backend: "docker" (hardened container, default; works on Windows/macOS/Linux),
    # "gvisor" (Docker + runsc syscall-interception runtime; Linux deploy/CI), or "e2b" (microVM).
    sandbox_runtime: str = "docker"
    # seccomp profile for the Docker/gVisor runner: "default" (Docker's built-in filter),
    # "unconfined" (disabled — not recommended), or an absolute path to a custom profile JSON.
    sandbox_seccomp_profile: str = "default"

    # Egress allowlist proxy (Initiative A follow-up). OFF by default → sandbox stays no-network.
    # When enabled, the container is attached to `sandbox_egress_network` and its HTTP(S)_PROXY is
    # pointed at `sandbox_egress_proxy_url`; the proxy permits only allowlisted hosts. The network
    # MUST be locked down so the only route out is the proxy (a deployment concern; see SECURITY).
    sandbox_egress_enabled: bool = False
    sandbox_egress_allowlist: str = ""  # comma-separated hosts; supports "*.example.com"
    sandbox_egress_proxy_url: str = ""  # e.g. http://host.docker.internal:8888
    sandbox_egress_network: str = "bridge"  # docker network attached when egress is enabled

    @property
    def sandbox_egress_allowlist_list(self) -> list[str]:
        return [h.strip() for h in self.sandbox_egress_allowlist.split(",") if h.strip()]

    # Orchestrator
    max_iterations: int = 6
    runs_db: str = "corenexia_runs.db"  # persistent run/audit store
    # Reusable skills (Initiative D): the agent's persistent, self-built toolbox.
    skills_enabled: bool = True
    skills_db: str = "corenexia_skills.db"

    # MCP aggregation (Initiative D): connect upstream MCP servers and re-expose their tools.
    # JSON array of objects, e.g.
    #   [{"name":"github","url":"https://host/mcp","auth_header":"Bearer X"}]
    mcp_upstreams: str = ""

    @property
    def mcp_upstreams_list(self) -> list[dict]:
        import json

        if not self.mcp_upstreams.strip():
            return []
        try:
            data = json.loads(self.mcp_upstreams)
        except (ValueError, TypeError):
            return []
        return [d for d in data if isinstance(d, dict) and d.get("name") and d.get("url")]

    # Gateway (Milestone 4)
    auth_enabled: bool = False  # when true, /v1/* requires a valid API key
    admin_token: str | None = None  # guards /admin/keys
    rate_limit_per_minute: int = 60  # per-key; 0 disables
    api_keys_db: str = "corenexia_keys.db"

    # MCP OAuth 2.1 (Initiative A follow-up). When auth is enabled, clients may exchange an API
    # key for a short-lived, scoped JWT at /oauth/token and present it as a Bearer token; static
    # API keys keep working for backward compatibility. RFC 8414/9728 metadata is published.
    oauth_issuer: str = "http://localhost:8000"  # token `iss`; also the metadata base URL
    oauth_audience: str = "corenexia-mcp"  # required token `aud`
    # HS256 signing secret. MUST be set to a long random value in production; if empty we fall
    # back to the admin token, or (last resort) a per-process random key (tokens die on restart).
    oauth_signing_key: str | None = None
    oauth_token_ttl_seconds: int = 3600  # short-lived access tokens (1h default)

    # Hardening (Milestone 5)
    # Comma-separated browser origins allowed by CORS (the God View frontend).
    allowed_origins: str = "http://localhost:3000"

    # Observability (Initiative B) — OpenTelemetry GenAI tracing.
    # When true, the app installs an SDK TracerProvider and emits spans. Configure the OTLP
    # destination with the standard OTEL_EXPORTER_OTLP_ENDPOINT / *_HEADERS env vars (works with
    # Langfuse, Phoenix, Jaeger, etc. — see OBSERVABILITY.md). Off by default.
    otel_enabled: bool = False
    otel_service_name: str = "corenexia"
    otel_console_export: bool = False  # debug: print spans to stdout instead of OTLP

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
