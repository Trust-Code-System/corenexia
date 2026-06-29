"use client";

import { useEffect, useRef } from "react";

import type { TelemetryEvent } from "@/lib/types";

const PHASE_COLOR: Record<string, string> = {
  thinking: "text-amber-300",
  writing_code: "text-sky-300",
  executing_sandbox: "text-violet-300",
  done: "text-emerald-300",
  error: "text-rose-300",
};

export function EventLog({ events }: { events: TelemetryEvent[] }) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (events.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No activity yet. Run the orchestrator to see live telemetry.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2 font-mono text-xs">
      {events.map((evt, i) => (
        <div key={i} className="rounded-md border border-slate-800 bg-slate-950/50 p-2">
          <div className="flex items-center justify-between">
            <span className={`font-semibold ${PHASE_COLOR[evt.phase] ?? "text-slate-300"}`}>
              {evt.phase}
            </span>
            <span className="text-slate-600">
              {new Date(evt.ts * 1000).toLocaleTimeString()}
            </span>
          </div>
          {evt.message && <div className="mt-1 text-slate-300">{evt.message}</div>}
          {typeof evt.data?.code_preview === "string" && (
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-black/40 p-2 text-[11px] text-sky-200">
              {evt.data.code_preview as string}
            </pre>
          )}
          {typeof evt.data?.stdout_preview === "string" && evt.data.stdout_preview && (
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-black/40 p-2 text-[11px] text-emerald-200">
              {evt.data.stdout_preview as string}
            </pre>
          )}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
