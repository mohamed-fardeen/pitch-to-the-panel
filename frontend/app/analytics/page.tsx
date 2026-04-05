"use client";

import React, { useRef, useEffect } from "react";
import { useDebugStream } from "../../components/analytics/useDebugStream";
import { NodeCard } from "../../components/analytics/NodeCard";
import { FlowTimeline } from "../../components/analytics/FlowTimeline";
import { MemoryPanel } from "../../components/analytics/MemoryPanel";

export default function Analytics() {
  const params = new URLSearchParams(typeof window !== "undefined" ? window.location.search : "");
  const sessionId = params.get("session_id");

  const {
    executions,
    currentNode,
    isComplete,
    isConnected,
    totalTurns,
    memorySnapshot,
  } = useDebugStream(sessionId);

  const listEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll execution list to bottom
  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [executions.length]);

  return (
    <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "24px", fontFamily: "system-ui, sans-serif" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "24px" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "20px", fontWeight: 700, color: "#111827" }}>
            Agent Execution Graph
          </h1>
          {sessionId && (
            <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#9CA3AF" }}>
              session: {sessionId}
            </p>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div
            style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: isConnected ? "#10B981" : "#9CA3AF",
            }}
          />
          <span style={{ fontSize: "12px", color: "#6B7280" }}>
            {isConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      {/* No session warning */}
      {!sessionId && (
        <div style={{ padding: "16px", background: "#FEF3C7", border: "1px solid #F59E0B", borderRadius: "8px", marginBottom: "24px", fontSize: "13px", color: "#92400E" }}>
          No session_id in URL. Open this page as{" "}
          <code>/analytics?session_id=YOUR_SESSION_ID</code> after starting a pitch.
        </div>
      )}

      {/* Current node banner */}
      {currentNode && (
        <div
          style={{
            padding: "12px 16px",
            background: "#EFF6FF",
            border: "1px solid #BFDBFE",
            borderRadius: "10px",
            marginBottom: "20px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#2563EB", animation: "pulse 1.5s infinite" }} />
          <span style={{ fontSize: "13px", color: "#1E40AF" }}>
            <strong>Active:</strong> {currentNode}
            {executions.length > 0 && executions[executions.length - 1].action && (
              <span style={{ marginLeft: "8px", color: "#6B7280" }}>
                → {executions[executions.length - 1].action}
                {executions[executions.length - 1].target && ` (${executions[executions.length - 1].target})`}
              </span>
            )}
          </span>
        </div>
      )}

      {/* Flow Timeline */}
      <div style={{ marginBottom: "24px" }}>
        <p style={{ margin: "0 0 8px", fontSize: "12px", fontWeight: 600, color: "#6B7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Flow Timeline
        </p>
        <FlowTimeline executions={executions} currentNode={currentNode} />
      </div>

      {/* Main 2-column layout */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 240px", gap: "20px", alignItems: "start" }}>

        {/* Execution history */}
        <div>
          <p style={{ margin: "0 0 8px", fontSize: "12px", fontWeight: 600, color: "#6B7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Execution History ({executions.length} steps)
          </p>

          <div style={{ maxHeight: "560px", overflowY: "auto", paddingRight: "4px" }}>
            {executions.length === 0 ? (
              <div style={{ padding: "32px", textAlign: "center", color: "#9CA3AF", fontSize: "13px", border: "1px dashed #E5E7EB", borderRadius: "10px" }}>
                Waiting for first node execution...
              </div>
            ) : (
              executions.map((ex, i) => (
                <NodeCard
                  key={ex.id}
                  execution={ex}
                  isActive={i === executions.length - 1 && !isComplete}
                  index={i}
                />
              ))
            )}
            <div ref={listEndRef} />
          </div>
        </div>

        {/* Sidebar */}
        <div style={{ position: "sticky", top: "24px" }}>
          <MemoryPanel
            memory={memorySnapshot}
            totalTurns={totalTurns}
            isComplete={isComplete}
          />

          {/* Stats */}
          {executions.length > 0 && (
            <div style={{ marginTop: "12px", background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: "12px", padding: "16px" }}>
              <p style={{ margin: "0 0 10px", fontSize: "12px", fontWeight: 600, color: "#6B7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Node Breakdown
              </p>
              {Object.entries(
                executions.reduce((acc, ex) => {
                  acc[ex.node] = (acc[ex.node] ?? 0) + 1;
                  return acc;
                }, {} as Record<string, number>)
              )
                .sort((a, b) => b[1] - a[1])
                .map(([node, count]) => (
                  <div key={node} style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "#374151", marginBottom: "4px" }}>
                    <span>{node}</span>
                    <span style={{ fontWeight: 600 }}>×{count}</span>
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}
