import React from "react";
import { NodeExecution } from "./useDebugStream";

const NODE_DISPLAY_NAMES: Record<string, string> = {
  pitch_refiner: "Pitch Refiner",
  controller: "Controller",
  persona: "Persona",
  pitcher: "Pitcher",
  tool: "Tool",
  reflection: "Reflection",
  memory_update: "Memory Update",
  final: "Final",
  error: "Error",
};

const NODE_COLORS: Record<string, { active: string; visited: string; text: string }> = {
  pitch_refiner: { active: "#7C3AED", visited: "#EDE9FE", text: "#5B21B6" },
  controller: { active: "#2563EB", visited: "#DBEAFE", text: "#1D4ED8" },
  persona: { active: "#059669", visited: "#D1FAE5", text: "#065F46" },
  pitcher: { active: "#D97706", visited: "#FEF3C7", text: "#92400E" },
  tool: { active: "#0891B2", visited: "#CFFAFE", text: "#164E63" },
  reflection: { active: "#7C3AED", visited: "#EDE9FE", text: "#5B21B6" },
  memory_update: { active: "#6B7280", visited: "#F3F4F6", text: "#374151" },
  final: { active: "#DC2626", visited: "#FEE2E2", text: "#991B1B" },
  error: { active: "#DC2626", visited: "#FEE2E2", text: "#991B1B" },
};

const fallbackColor = { active: "#6B7280", visited: "#F3F4F6", text: "#374151" };

interface Props {
  execution: NodeExecution;
  isActive: boolean;
  index: number;
}

export function NodeCard({ execution, isActive, index }: Props) {
  const colors = NODE_COLORS[execution.node] ?? fallbackColor;
  const displayName = NODE_DISPLAY_NAMES[execution.node] ?? execution.node;

  const cardStyle: React.CSSProperties = {
    padding: "12px 16px",
    marginBottom: "8px",
    borderRadius: "10px",
    border: isActive
      ? `2px solid ${colors.active}`
      : execution.isError
      ? "2px solid #DC2626"
      : "1px solid #E5E7EB",
    background: isActive
      ? colors.visited
      : execution.isError
      ? "#FEF2F2"
      : "#FFFFFF",
    display: "flex",
    alignItems: "flex-start",
    gap: "12px",
    transition: "all 0.2s ease",
    position: "relative",
  };

  const dotStyle: React.CSSProperties = {
    width: "10px",
    height: "10px",
    borderRadius: "50%",
    background: isActive ? colors.active : execution.isError ? "#DC2626" : "#D1D5DB",
    flexShrink: 0,
    marginTop: "5px",
  };

  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}>
        <div style={dotStyle} />
        <span style={{ fontSize: "11px", color: "#9CA3AF", fontWeight: 500 }}>
          {execution.step >= 0 ? `#${execution.step}` : "!"}
        </span>
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
          <span
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: colors.text,
              background: colors.visited,
              padding: "2px 8px",
              borderRadius: "6px",
            }}
          >
            {displayName}
          </span>

          {execution.agentName && (
            <span style={{ fontSize: "12px", color: "#6B7280" }}>
              → {execution.agentName}
            </span>
          )}

          {isActive && (
            <span
              style={{
                fontSize: "11px",
                color: colors.active,
                fontWeight: 600,
                marginLeft: "auto",
              }}
            >
              ACTIVE
            </span>
          )}
        </div>

        {execution.isError ? (
          <p style={{ margin: 0, fontSize: "12px", color: "#DC2626" }}>
            {execution.errorMessage}
          </p>
        ) : (
          <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
            {execution.action && (
              <span style={{ fontSize: "12px", color: "#374151" }}>
                <span style={{ color: "#9CA3AF" }}>action: </span>
                {execution.action}
              </span>
            )}
            {execution.target && (
              <span style={{ fontSize: "12px", color: "#374151" }}>
                <span style={{ color: "#9CA3AF" }}>target: </span>
                {execution.target}
              </span>
            )}
          </div>
        )}
      </div>

      {execution.durationMs !== null && (
        <span
          style={{
            fontSize: "11px",
            color: execution.durationMs > 5000 ? "#DC2626" : "#6B7280",
            flexShrink: 0,
            alignSelf: "center",
          }}
        >
          {execution.durationMs > 1000
            ? `${(execution.durationMs / 1000).toFixed(1)}s`
            : `${execution.durationMs}ms`}
        </span>
      )}
    </div>
  );
}
