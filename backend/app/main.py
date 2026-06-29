"""FastAPI entrypoint for the Corenexia orchestrator gateway.

On startup it builds the LLM provider and sandbox, runs a Docker preflight (logging a clear
build hint if the sandbox image is missing rather than crashing), and compiles the LangGraph
orchestrator. Components live on `app.state` for the routes to use.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import admin_router
from app.api.oauth import oauth_router
from app.api.routes import router
from app.api.skills import skills_router
from app.api.templates import templates_router
from app.api.ws import ws_router
from app.config import settings
from app.gateway.auth import MCPAuthMiddleware
from app.gateway.keys import KeyStore
from app.gateway.ratelimit import RateLimiter
from app.llm import build_provider
from app.mcp_server import engine as mcp_engine
from app.mcp_server import mcp as mcp_server
from app.observability import RequestIDMiddleware, setup_logging
from app.orchestrator.graph import build_orchestrator
from app.orchestrator.runs import RunRegistry
from app.orchestrator.skills import SkillStore
from app.sandbox import build_sandbox
from app.telemetry.events import EventBus
from app.telemetry.otel import setup_tracing

setup_logging()
logger = logging.getLogger("corenexia")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.bus = EventBus()
    app.state.runs = RunRegistry(settings.runs_db)

    # Observability (Initiative B): install OTel tracing if enabled (no-op otherwise).
    app.state.tracing_enabled = setup_tracing(settings)

    # Gateway (Milestone 4)
    app.state.auth_enabled = settings.auth_enabled
    app.state.admin_token = settings.admin_token
    app.state.keys = KeyStore(settings.api_keys_db)
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    logger.info(
        "Gateway: auth_enabled=%s, admin_api=%s, rate_limit/min=%s",
        settings.auth_enabled,
        "on" if settings.admin_token else "off",
        settings.rate_limit_per_minute,
    )

    app.state.provider = build_provider()
    app.state.sandbox = build_sandbox()

    ready, message = app.state.sandbox.preflight()
    app.state.sandbox_ready = ready
    app.state.sandbox_message = message
    if ready:
        logger.info("Sandbox preflight OK: %s", message)
    else:
        logger.error("Sandbox preflight FAILED: %s", message)
        logger.error("The server will start but /v1/orchestrate returns 503 until this is fixed.")

    app.state.skills = SkillStore(settings.skills_db) if settings.skills_enabled else None
    app.state.orchestrator = build_orchestrator(
        provider=app.state.provider,
        sandbox=app.state.sandbox,
        bus=app.state.bus,
        skills=app.state.skills,
    )

    # Share the compiled orchestrator with the MCP tool surface, and run the MCP session
    # manager for the lifetime of the app.
    mcp_engine.orchestrator = app.state.orchestrator
    async with mcp_server.session_manager.run():
        logger.info(
            "Corenexia ready (LLM provider: %s). MCP tool surface mounted at /mcp.",
            app.state.provider.name,
        )
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Corenexia — Infinite Dynamic Orchestrator",
        version="0.1.0",
        lifespan=lifespan,
    )
    # Request tracing (outermost) + CORS for the God View frontend + MCP endpoint auth.
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(MCPAuthMiddleware)

    app.include_router(router)
    app.include_router(templates_router)
    app.include_router(skills_router)
    app.include_router(oauth_router)
    app.include_router(admin_router)
    app.include_router(ws_router)

    # Mount the MCP streamable-HTTP server. streamable_http_path="/" => endpoint lands at /mcp.
    app.mount("/mcp", mcp_server.streamable_http_app())
    return app


app = create_app()
