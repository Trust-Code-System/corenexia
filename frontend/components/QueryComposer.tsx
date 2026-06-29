"use client";

import { useEffect, useState } from "react";

import { listTemplates } from "@/lib/api";
import type { Template } from "@/lib/types";

const SAMPLE =
  "Extract the parties, term, governing law, and termination notice period from the sample " +
  "services agreement and return them as JSON.";

export function QueryComposer({
  onSubmit,
  busy,
}: {
  onSubmit: (query: string, context?: string) => void;
  busy: boolean;
}) {
  const [query, setQuery] = useState(SAMPLE);
  const [context, setContext] = useState("");
  const [templates, setTemplates] = useState<Template[]>([]);

  useEffect(() => {
    listTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]));
  }, []);

  function applyTemplate(id: string) {
    const tpl = templates.find((t) => t.id === id);
    if (!tpl) return;
    setQuery(tpl.query);
    setContext(tpl.example_context ?? "");
  }

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (query.trim()) onSubmit(query.trim(), context.trim() || undefined);
      }}
    >
      {templates.length > 0 && (
        <>
          <label className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Starter template
          </label>
          <select
            defaultValue=""
            onChange={(e) => applyTemplate(e.target.value)}
            disabled={busy}
            aria-label="Starter template"
            title="Starter template"
            className="rounded-lg border border-slate-700 bg-slate-950/60 p-2 text-sm text-slate-100 outline-none focus:border-accent focus:ring-1 focus:ring-accent"
          >
            <option value="" disabled>
              Choose a legal / finance / general starter…
            </option>
            {["legal", "finance", "general"].map((domain) => {
              const group = templates.filter((t) => t.domain === domain);
              if (group.length === 0) return null;
              return (
                <optgroup key={domain} label={domain.toUpperCase()}>
                  {group.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.title}
                    </option>
                  ))}
                </optgroup>
              );
            })}
          </select>
        </>
      )}

      <label className="text-xs font-medium uppercase tracking-wide text-slate-400">
        Task
      </label>
      <textarea
        className="min-h-[96px] resize-y rounded-lg border border-slate-700 bg-slate-950/60 p-3 text-sm text-slate-100 outline-none focus:border-accent focus:ring-1 focus:ring-accent"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Describe a legal or finance task…"
      />

      <label className="text-xs font-medium uppercase tracking-wide text-slate-400">
        Context (optional)
      </label>
      <textarea
        className="min-h-[64px] resize-y rounded-lg border border-slate-700 bg-slate-950/60 p-3 text-sm text-slate-100 outline-none focus:border-accent focus:ring-1 focus:ring-accent"
        value={context}
        onChange={(e) => setContext(e.target.value)}
        placeholder="Paste a contract excerpt or dataset…"
      />

      <button
        type="submit"
        disabled={busy || !query.trim()}
        className="mt-1 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-accent-muted disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? "Orchestrating…" : "Run orchestrator"}
      </button>
    </form>
  );
}
