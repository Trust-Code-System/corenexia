"use client";

import "@xyflow/react/dist/style.css";

import { useEffect, useRef } from "react";
import {
  Background,
  Controls,
  type Edge,
  MarkerType,
  type Node,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";

import type { Phase, TelemetryEvent } from "@/lib/types";

const CARD = {
  color: "#e2e8f0",
  border: "1px solid #334155",
  borderRadius: 12,
  fontSize: 12,
  width: 170,
  padding: 8,
};

function baseNodes(): Node[] {
  return [
    {
      id: "client",
      type: "input",
      position: { x: 0, y: 140 },
      sourcePosition: Position.Right,
      data: { label: "Client request" },
      style: { ...CARD, background: "#1e293b" },
    },
    {
      id: "orchestrator",
      position: { x: 270, y: 120 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: { label: "Orchestrator · idle" },
      style: {
        ...CARD,
        background: "#0b3b53",
        border: "1px solid #38bdf8",
        boxShadow: "0 0 18px rgba(56,189,248,0.25)",
      },
    },
    {
      id: "result",
      type: "output",
      position: { x: 560, y: 140 },
      targetPosition: Position.Left,
      data: { label: "Structured result" },
      style: { ...CARD, background: "#1e293b" },
    },
  ];
}

function baseEdges(): Edge[] {
  return [
    { id: "e-client", source: "client", target: "orchestrator" },
    { id: "e-result", source: "orchestrator", target: "result" },
  ];
}

function sandboxNode(id: string, index: number): Node {
  return {
    id,
    type: "output",
    position: { x: 300, y: 280 + index * 88 },
    targetPosition: Position.Top,
    data: { label: "⚙ Sandbox (MicroVM)" },
    style: { ...CARD, background: "#2e1065", border: "1px solid #a78bfa" },
  };
}

function pulseEdge(nodeId: string): Edge {
  return {
    id: `edge-${nodeId}`,
    source: "orchestrator",
    target: nodeId,
    animated: true,
    className: "edge-pulse",
    markerEnd: { type: MarkerType.ArrowClosed, color: "#38bdf8" },
  };
}

export function OrchestratorCanvas({
  events,
  phase,
}: {
  events: TelemetryEvent[];
  phase: Phase | null;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState(baseNodes());
  const [edges, setEdges, onEdgesChange] = useEdgesState(baseEdges());
  const processed = useRef(0);
  const sandboxCount = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Reset the canvas when a new run starts (the telemetry hook clears events).
  useEffect(() => {
    if (events.length === 0) {
      processed.current = 0;
      sandboxCount.current = 0;
      setNodes(baseNodes());
      setEdges(baseEdges());
    }
  }, [events.length, setNodes, setEdges]);

  // Reflect the live phase on the orchestrator node.
  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) =>
        n.id === "orchestrator"
          ? { ...n, data: { ...n.data, label: `Orchestrator · ${phase ?? "idle"}` } }
          : n,
      ),
    );
  }, [phase, setNodes]);

  // Incrementally process new telemetry: spin up sandbox nodes, then retire them.
  useEffect(() => {
    for (let i = processed.current; i < events.length; i++) {
      const evt = events[i];
      if (evt.phase !== "executing_sandbox") continue;

      const status = evt.data?.status;
      const tid = String(evt.data?.tool_use_id ?? `sbx-${i}`);
      const nodeId = `sandbox-${tid}`;

      if (status === "start") {
        const index = sandboxCount.current++;
        setNodes((nds) =>
          nds.some((n) => n.id === nodeId) ? nds : [...nds, sandboxNode(nodeId, index)],
        );
        setEdges((eds) =>
          eds.some((e) => e.id === `edge-${nodeId}`) ? eds : [...eds, pulseEdge(nodeId)],
        );
      } else if (status === "complete") {
        const isError = Boolean(evt.data?.is_error);
        setEdges((eds) =>
          eds.map((e) =>
            e.id === `edge-${nodeId}`
              ? {
                  ...e,
                  animated: false,
                  className: "",
                  style: { stroke: isError ? "#f43f5e" : "#34d399", strokeWidth: 2 },
                }
              : e,
          ),
        );
        // Let the completed node linger briefly, then vanish.
        const t = setTimeout(() => {
          setNodes((nds) => nds.filter((n) => n.id !== nodeId));
          setEdges((eds) => eds.filter((e) => e.id !== `edge-${nodeId}`));
        }, 1400);
        timers.current.push(t);
      }
    }
    processed.current = events.length;
  }, [events, setNodes, setEdges]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
  }, []);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      fitView
      proOptions={{ hideAttribution: true }}
      className="bg-slate-900"
    >
      <Background color="#1e293b" gap={20} />
      <Controls className="!bg-slate-800 !border-slate-700" />
    </ReactFlow>
  );
}
