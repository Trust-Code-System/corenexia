"""REST endpoints for the orchestrator gateway."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.gateway.auth import ApiKeyDep
from app.gateway.keys import ApiKeyRecord
from app.orchestrator.graph import run_orchestration
from app.orchestrator.runs import start_background_run
from app.telemetry.events import Phase

_TERMINAL_PHASES = {Phase.DONE, Phase.ERROR}

router = APIRouter()


def _require_sandbox(app) -> None:
    if not getattr(app.state, "sandbox_ready", False):
        raise HTTPException(
            status_code=503,
            detail=f"Sandbox not ready: {getattr(app.state, 'sandbox_message', 'unknown')}",
        )


def _enforce_spend_cap(key: ApiKeyRecord | None) -> None:
    """Block a new orchestration when the key's accumulated cost has reached its spend cap."""
    if key is not None and key.over_cap:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Spend cap reached: ${key.cost_usd:.4f} of ${key.spend_cap_usd:.2f} used. "
                "Raise the cap or use another key."
            ),
        )


def _meter_key(app, key: ApiKeyRecord | None, usage: dict | None) -> None:
    """Record a finished run's tokens/cost against the key that paid for it."""
    if key is None or not usage:
        return
    app.state.keys.add_usage(
        key.id,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cost_usd=usage.get("cost_usd", 0.0),
    )


class OrchestrateRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The task for the orchestrator.")
    context: str | None = Field(None, description="Optional supporting text (e.g. a document).")
    max_iterations: int | None = Field(None, ge=1, le=20)


class StepView(BaseModel):
    tool: str
    code: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int


class UsageView(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0


class OrchestrateResponse(BaseModel):
    run_id: str
    status: str
    answer: str | None
    iterations: int
    steps: list[StepView]
    usage: UsageView = Field(default_factory=UsageView)


class RunStartResponse(BaseModel):
    run_id: str
    status: str
    # Where to watch this run live.
    telemetry_ws: str


class RunStatusResponse(BaseModel):
    run_id: str
    status: str
    result: OrchestrateResponse | None = None
    error: str | None = None


def _to_response(final: dict) -> OrchestrateResponse:
    return OrchestrateResponse(
        run_id=final["run_id"],
        status=final["status"],
        answer=final["answer"],
        iterations=final["iterations"],
        steps=[StepView(**step) for step in final["steps"]],
        usage=UsageView(**final.get("usage", {})),
    )


@router.get("/health")
async def health(request: Request) -> dict:
    ready: bool = getattr(request.app.state, "sandbox_ready", False)
    message: str = getattr(request.app.state, "sandbox_message", "unknown")
    return {
        "status": "ok",
        "sandbox_ready": ready,
        "sandbox": message,
        "llm_provider": request.app.state.provider.name,
    }


@router.post("/v1/orchestrate", response_model=OrchestrateResponse)
async def orchestrate(
    body: OrchestrateRequest,
    request: Request,
    key: ApiKeyRecord | None = ApiKeyDep,
) -> OrchestrateResponse:
    """Run synchronously and return the full result. Simplest path; blocks until done."""
    app = request.app
    _require_sandbox(app)
    _enforce_spend_cap(key)

    # The graph is synchronous (the sandbox shells out to Docker); run it off the event loop.
    try:
        final = await asyncio.to_thread(
            run_orchestration,
            app.state.orchestrator,
            body.query,
            body.context,
            max_iterations=body.max_iterations,
        )
    except Exception as exc:  # surface provider/sandbox failures as 502
        raise HTTPException(status_code=502, detail=f"Orchestration failed: {exc}") from exc

    _meter_key(app, key, final.get("usage"))
    return _to_response(final)


@router.post("/v1/runs", response_model=RunStartResponse, status_code=202)
async def start_run(
    body: OrchestrateRequest,
    request: Request,
    key: ApiKeyRecord | None = ApiKeyDep,
) -> RunStartResponse:
    """Start a run in the background and return its id immediately. Watch it on /ws/telemetry."""
    app = request.app
    _require_sandbox(app)
    _enforce_spend_cap(key)
    run_id = await start_background_run(
        app, body.query, body.context, max_iterations=body.max_iterations,
        key_id=key.id if key else None,
    )
    return RunStartResponse(
        run_id=run_id, status="running", telemetry_ws=f"/ws/telemetry?run_id={run_id}"
    )


@router.post("/v1/orchestrate/stream")
async def orchestrate_stream(
    body: OrchestrateRequest,
    request: Request,
    key: ApiKeyRecord | None = ApiKeyDep,
) -> StreamingResponse:
    """Stream a run's progress as Server-Sent Events: one frame per telemetry phase, then a final
    `result` event with the answer. An HTTP alternative to the telemetry WebSocket."""
    app = request.app
    _require_sandbox(app)
    _enforce_spend_cap(key)

    bus = app.state.bus
    queue = bus.subscribe()  # subscribe BEFORE starting so no early events are missed
    run_id = await start_background_run(
        app, body.query, body.context, max_iterations=body.max_iterations,
        key_id=key.id if key else None,
    )

    async def _events():
        try:
            yield f"event: start\ndata: {json.dumps({'run_id': run_id})}\n\n"
            while True:
                event = await queue.get()
                if event.run_id != run_id:
                    continue
                yield f"event: {event.phase.value}\ndata: {json.dumps(event.to_dict())}\n\n"
                if event.phase in _TERMINAL_PHASES:
                    break
            record = app.state.runs.get(run_id)
            result = record.result if record and record.result else {"run_id": run_id}
            yield f"event: result\ndata: {json.dumps(result)}\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.get(
    "/v1/runs/{run_id}",
    response_model=RunStatusResponse,
    dependencies=[ApiKeyDep],
)
async def get_run(run_id: str, request: Request) -> RunStatusResponse:
    """Fetch the status (and result, once finished) of a background run."""
    record = request.app.state.runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No run with id '{run_id}'.")
    result = OrchestrateResponse(**record.result) if record.result else None
    return RunStatusResponse(
        run_id=record.run_id, status=record.status, result=result, error=record.error
    )
