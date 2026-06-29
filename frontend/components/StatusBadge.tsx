import type { Phase } from "@/lib/types";

const LABELS: Record<string, { text: string; dot: string }> = {
  idle: { text: "Idle", dot: "bg-slate-500" },
  thinking: { text: "Thinking", dot: "bg-amber-400" },
  writing_code: { text: "Writing code", dot: "bg-sky-400" },
  executing_sandbox: { text: "Executing sandbox", dot: "bg-violet-400" },
  done: { text: "Done", dot: "bg-emerald-400" },
  error: { text: "Error", dot: "bg-rose-500" },
};

export function StatusBadge({ phase }: { phase: Phase | "idle" | null }) {
  const key = phase ?? "idle";
  const meta = LABELS[key] ?? LABELS.idle;
  const animate = key === "thinking" || key === "writing_code" || key === "executing_sandbox";
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-800 px-3 py-1 text-xs font-medium text-slate-200">
      <span className={`h-2 w-2 rounded-full ${meta.dot} ${animate ? "animate-pulse" : ""}`} />
      {meta.text}
    </span>
  );
}
