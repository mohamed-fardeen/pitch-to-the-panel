import React, { useRef, useEffect } from "react";
import { NodeExecution } from "./useDebugStream";

const NODE_COLORS: Record<string, string> = {
  pitch_refiner: "#7C3AED",
  controller:    "#2563EB",
  persona:       "#059669",
  pitcher:       "#D97706",
  tool:          "#0891B2",
  reflection:    "#7C3AED",
  memory_update: "#9CA3AF",
  final:         "#DC2626",
  error:         "#DC2626",
};

interface Props {
  executions: NodeExecution[];
  currentNode: string | null;
}

export function FlowTimeline({ executions, currentNode }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to end when new nodes arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [executions.length]);

  if (executions.length === 0) {
    return (
      <div style={{ padding: "12px 0", color: "#9CA3AF", fontSize: "13px" }}>
        Waiting for execution to start...
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      style={{
        display: "flex",
        gap: "4px",
        alignItems: "center",
        overflowX: "auto",
        paddingBottom: "8px",
        scrollbarWidth: "thin",
      }}
    >
      {executions.map((ex, i) => {
        const isLast = i === executions.length - 1;
        const color = NODE_COLORS[ex.node] ?? "#6B7280";

        return (
          <React.Fragment key={ex.id}>
            <div
              title={`Step ${ex.step}: ${ex.node}${ex.action ? ` → ${ex.action}` : ""}${ex.agentName ? ` (${ex.agentName})` : ""}`}
              style={{
                padding: "4px 10px",
                borderRadius: "20px",
                background: isLast ? color : `${color}22`,
                color: isLast ? "#fff" : color,
                border: `1px solid ${color}`,
                fontSize: "11px",
                fontWeight: 600,
                whiteSpace: "nowrap",
                flexShrink: 0,
                cursor: "default",
                transition: "all 0.2s ease",
                outline: ex.isError ? "2px solid #DC2626" : "none",
              }}
            >
              {ex.node}
              {ex.isError && " ✕"}
            </div>

            {/* Connector arrow between pills */}
            {i < executions.length - 1 && (
              <span style={{ color: "#D1D5DB", fontSize: "12px", flexShrink: 0 }}>
                →
              </span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
