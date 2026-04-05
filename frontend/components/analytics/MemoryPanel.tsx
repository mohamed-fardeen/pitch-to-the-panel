import React from "react";

interface MemorySnapshot {
  risks: number;
  strengths: number;
  claims: number;
  contradictions: number;
}

interface Props {
  memory: MemorySnapshot | null;
  totalTurns: number;
  isComplete: boolean;
}

const MEMORY_CONFIG = [
  { key: "risks" as const,          label: "Risks",          color: "#DC2626", bg: "#FEF2F2" },
  { key: "strengths" as const,      label: "Strengths",      color: "#059669", bg: "#F0FDF4" },
  { key: "claims" as const,         label: "Claims",         color: "#2563EB", bg: "#EFF6FF" },
  { key: "contradictions" as const, label: "Contradictions", color: "#D97706", bg: "#FFFBEB" },
];

export function MemoryPanel({ memory, totalTurns, isComplete }: Props) {
  return (
    <div
      style={{
        background: "#F9FAFB",
        border: "1px solid #E5E7EB",
        borderRadius: "12px",
        padding: "16px",
      }}
    >
      <p style={{ margin: "0 0 12px", fontSize: "12px", fontWeight: 600, color: "#6B7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Memory State
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "12px" }}>
        {MEMORY_CONFIG.map(({ key, label, color, bg }) => (
          <div
            key={key}
            style={{
              background: bg,
              border: `1px solid ${color}33`,
              borderRadius: "8px",
              padding: "8px 12px",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: "20px", fontWeight: 700, color }}>
              {memory?.[key] ?? 0}
            </div>
            <div style={{ fontSize: "11px", color: "#6B7280", marginTop: "2px" }}>
              {label}
            </div>
          </div>
        ))}
      </div>

      <div style={{ borderTop: "1px solid #E5E7EB", paddingTop: "10px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "#6B7280" }}>
          <span>Total turns</span>
          <span style={{ fontWeight: 600, color: "#111827" }}>{totalTurns}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "#6B7280", marginTop: "4px" }}>
          <span>Status</span>
          <span style={{ fontWeight: 600, color: isComplete ? "#059669" : "#2563EB" }}>
            {isComplete ? "Complete" : "Running"}
          </span>
        </div>
      </div>
    </div>
  );
}
