// Mirrors the backend telemetry + run shapes (app/telemetry/events.py, app/api/routes.py).

export type Phase =
  | "thinking"
  | "writing_code"
  | "executing_sandbox"
  | "done"
  | "error";

export interface TelemetryEvent {
  run_id: string;
  phase: Phase;
  message: string;
  data: Record<string, unknown>;
  ts: number;
}

export interface RunStartResponse {
  run_id: string;
  status: string;
  telemetry_ws: string;
}

export interface Template {
  id: string;
  title: string;
  description: string;
  query: string;
  domain: string;
  pack: string;
  tags: string[];
  example_context: string | null;
}

export interface Step {
  tool: string;
  code: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  timed_out: boolean;
  duration_ms: number;
}

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  cost_usd: number;
  llm_calls: number;
}

export interface OrchestrateResult {
  run_id: string;
  status: string;
  answer: string | null;
  iterations: number;
  steps: Step[];
  usage?: Usage;
}

export interface RunStatusResponse {
  run_id: string;
  status: string;
  result: OrchestrateResult | null;
  error: string | null;
}
