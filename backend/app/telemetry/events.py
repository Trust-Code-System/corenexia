"""In-process event bus for orchestrator telemetry.

The graph emits an OrchestratorEvent at each phase transition. Today the only subscriber is the
logger; in Milestone 1's Step-4 seam a WebSocket endpoint will `subscribe()` a queue and stream
these events to the React Flow canvas. The bus is deliberately tiny and dependency-free.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger("corenexia.telemetry")


class Phase(StrEnum):
    """High-level orchestrator states surfaced to the UI."""

    THINKING = "thinking"
    WRITING_CODE = "writing_code"
    EXECUTING_SANDBOX = "executing_sandbox"
    DONE = "done"
    ERROR = "error"


@dataclass
class OrchestratorEvent:
    run_id: str
    phase: Phase
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["phase"] = self.phase.value
        return d


# A sink receives one event. The graph is synchronous, so sinks are plain callables.
EventSink = Callable[[OrchestratorEvent], None]


class EventBus:
    """Fan-out hub. Sync sinks (e.g. logging) plus asyncio.Queue subscribers (e.g. WebSockets).

    Thread-safe: the orchestration graph runs in a worker thread (asyncio.to_thread), so
    `publish` may be called off the event loop. Each subscriber records the loop it was created
    on, and events are delivered with `loop.call_soon_threadsafe` so the waiting WebSocket
    coroutine is woken correctly.
    """

    def __init__(self) -> None:
        self._sinks: list[EventSink] = [_log_sink]
        self._subscribers: list[tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = []

    def add_sink(self, sink: EventSink) -> None:
        self._sinks.append(sink)

    def subscribe(self) -> asyncio.Queue:
        """Register an async subscriber. Must be called from within the event loop."""
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        self._subscribers.append((queue, loop))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers = [(q, lp) for (q, lp) in self._subscribers if q is not queue]

    def publish(self, event: OrchestratorEvent) -> None:
        for sink in self._sinks:
            try:
                sink(event)
            except Exception:  # a bad sink must never break the orchestrator
                logger.exception("telemetry sink failed")
        for queue, loop in list(self._subscribers):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                # Event loop is closed/closing — drop the subscriber on next unsubscribe.
                pass


def _log_sink(event: OrchestratorEvent) -> None:
    logger.info("[%s] %s — %s", event.run_id, event.phase.value, event.message)
