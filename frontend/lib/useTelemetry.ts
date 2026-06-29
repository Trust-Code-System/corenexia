"use client";

import { useEffect, useRef, useState } from "react";

import { telemetryWsUrl } from "./api";
import type { Phase, TelemetryEvent } from "./types";

export type ConnState = "idle" | "connecting" | "open" | "closed" | "error";

/**
 * Subscribe to the backend telemetry WebSocket for a single run. Re-subscribes whenever `runId`
 * changes; the backend closes the socket when the run reaches a terminal phase.
 */
export function useTelemetry(runId: string | null) {
  const [events, setEvents] = useState<TelemetryEvent[]>([]);
  const [phase, setPhase] = useState<Phase | null>(null);
  const [conn, setConn] = useState<ConnState>("idle");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    setEvents([]);
    setPhase(null);
    setConn("connecting");

    const ws = new WebSocket(telemetryWsUrl(runId));
    wsRef.current = ws;

    ws.onopen = () => setConn("open");
    ws.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as TelemetryEvent;
        setEvents((prev) => [...prev, evt]);
        setPhase(evt.phase);
      } catch {
        // ignore malformed frames
      }
    };
    ws.onerror = () => setConn("error");
    ws.onclose = () => setConn((c) => (c === "error" ? c : "closed"));

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId]);

  return { events, phase, conn };
}
