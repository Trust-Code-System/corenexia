import type { RunStartResponse, RunStatusResponse, Template } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Derive the ws:// (or wss://) origin from the http(s) API base. */
export function wsBase(): string {
  return API_BASE.replace(/^http/, "ws");
}

export function telemetryWsUrl(runId?: string): string {
  const url = new URL("/ws/telemetry", wsBase());
  if (runId) url.searchParams.set("run_id", runId);
  return url.toString();
}

export async function startRun(
  query: string,
  context?: string,
  maxIterations?: number,
): Promise<RunStartResponse> {
  const res = await fetch(`${API_BASE}/v1/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      context: context || null,
      max_iterations: maxIterations ?? null,
    }),
  });
  if (!res.ok) {
    const detail = await safeDetail(res);
    throw new Error(`Failed to start run (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function getRun(runId: string): Promise<RunStatusResponse> {
  const res = await fetch(`${API_BASE}/v1/runs/${runId}`);
  if (!res.ok) {
    const detail = await safeDetail(res);
    throw new Error(`Failed to fetch run (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function listTemplates(): Promise<Template[]> {
  const res = await fetch(`${API_BASE}/v1/templates`);
  if (!res.ok) throw new Error(`Failed to list templates (${res.status})`);
  return res.json();
}

export async function getHealth(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json();
}

async function safeDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
  } catch {
    return res.statusText;
  }
}
