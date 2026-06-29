"use client";

import { useEffect, useState } from "react";

import { EventLog } from "@/components/EventLog";
import { OrchestratorCanvas } from "@/components/OrchestratorCanvas";
import { QueryComposer } from "@/components/QueryComposer";
import { StatusBadge } from "@/components/StatusBadge";
import { getHealth, getRun, startRun } from "@/lib/api";
import type { OrchestrateResult } from "@/lib/types";
import { useTelemetry } from "@/lib/useTelemetry";

export default function GodView() {
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OrchestrateResult | null>(null);
  const [health, setHealth] = useState<{ ok: boolean; label: string }>({
    ok: false,
    label: "checking…",
  });

  const { events, phase, conn } = useTelemetry(runId);

  useEffect(() => {
    getHealth()
      .then((h) =>
        setHealth({
          ok: Boolean(h.sandbox_ready),
          label: h.sandbox_ready ? "sandbox ready" : "sandbox not ready",
        }),
      )
      .catch(() => setHealth({ ok: false, label: "backend unreachable" }));
  }, []);

  // When a run reaches a terminal phase, fetch the final result.
  useEffect(() => {
    if (!runId) return;
    if (phase === "done" || phase === "error") {
      getRun(runId)
        .then((r) => {
          setResult(r.result);
          if (r.error) setError(r.error);
        })
        .catch((e) => setError(String(e)))
        .finally(() => setBusy(false));
    }
  }, [phase, runId]);

  async function handleSubmit(query: string, context?: string) {
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const { run_id } = await startRun(query, context);
      setRunId(run_id);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-800/60 px-5">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold tracking-wide text-slate-100">CORENEXIA</span>
          <span className="text-xs text-slate-500">Infinite Dynamic Orchestrator · God View</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${
              health.ok
                ? "border-emerald-700 text-emerald-300"
                : "border-rose-800 text-rose-300"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${health.ok ? "bg-emerald-400" : "bg-rose-500"}`}
            />
            {health.label}
          </span>
          <span className="text-slate-600">ws: {conn}</span>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Left sidebar — composer */}
        <aside className="flex w-80 shrink-0 flex-col gap-4 overflow-y-auto border-r border-slate-800 bg-slate-800/40 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200">New task</h2>
            <StatusBadge phase={busy || runId ? phase : "idle"} />
          </div>
          <QueryComposer onSubmit={handleSubmit} busy={busy} />
          {error && (
            <div className="rounded-lg border border-rose-800 bg-rose-950/40 p-3 text-xs text-rose-200">
              {error}
            </div>
          )}
          <p className="mt-auto text-[11px] leading-relaxed text-slate-500">
            Legal &amp; general-finance domain only. The orchestrator writes Python on demand and
            runs it in an isolated, ephemeral sandbox.
          </p>
        </aside>

        {/* Center — canvas */}
        <main className="relative min-w-0 flex-1">
          <OrchestratorCanvas events={events} phase={phase} />
        </main>

        {/* Right — telemetry + result */}
        <aside className="flex w-96 shrink-0 flex-col gap-4 overflow-y-auto border-l border-slate-800 bg-slate-800/40 p-5">
          <h2 className="text-sm font-semibold text-slate-200">Live telemetry</h2>
          <EventLog events={events} />

          {result?.answer && (
            <div className="mt-2">
              <h3 className="mb-2 text-sm font-semibold text-slate-200">Answer</h3>
              <div className="whitespace-pre-wrap rounded-lg border border-slate-700 bg-slate-950/50 p-3 text-sm text-slate-100">
                {result.answer}
              </div>
              <p className="mt-2 text-[11px] text-slate-500">
                {result.iterations} iteration(s) · {result.steps.length} sandbox step(s) ·{" "}
                {result.status}
              </p>
              {result.usage && result.usage.total_tokens > 0 && (
                <p className="mt-1 text-[11px] text-slate-500">
                  {result.usage.total_tokens.toLocaleString()} tokens (
                  {result.usage.input_tokens.toLocaleString()} in ·{" "}
                  {result.usage.output_tokens.toLocaleString()} out) ·{" "}
                  {result.usage.llm_calls} LLM call(s) ·{" "}
                  <span className="text-emerald-400">
                    ${result.usage.cost_usd.toFixed(4)}
                  </span>
                </p>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
