import { useState, useRef, useCallback } from "react";

export interface NodeExecution {
  id: string;
  node: string;
  step: number;
  action: string | null;
  target: string | null;
  memorySnapshot: {
    risks: number;
    strengths: number;
    claims: number;
    contradictions: number;
  } | null;
  timestamp: number;
  durationMs: number | null;
  isError: boolean;
  errorMessage: string | null;
  agentName: string | null;
}

export interface DebugStreamState {
  executions: NodeExecution[];
  currentNode: string | null;
  isComplete: boolean;
  isConnected: boolean;
  totalTurns: number;
  memorySnapshot: NodeExecution["memorySnapshot"];
  fullMemory: any;
  agentMemory: Record<string, any>;
  pushEvent: (eventType: string, data: any) => void;
  setConnected: (val: boolean) => void;
  reset: () => void;
}

export function useDebugStream(): DebugStreamState {
  const [executions, setExecutions] = useState<NodeExecution[]>([]);
  const [currentNode, setCurrentNode] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [totalTurns, setTotalTurns] = useState(0);
  const [memorySnapshot, setMemorySnapshot] = useState<NodeExecution["memorySnapshot"]>(null);
  
  const [fullMemory, setFullMemory] = useState<any>({ 
    risks: [], 
    strengths: [], 
    claims: [], 
    contradictions: [], 
    opinions: [] 
  });

  const [agentMemory, setAgentMemory] = useState<Record<string, any>>({});

  const lastTimestampRef = useRef<number | null>(null);

  const pushEvent = useCallback((eventType: string, data: any) => {
    // 1. Handle Memory Update ASAP
    if (eventType === "memory_update") {
      console.log("[DEBUG] Memory update received:", data);
      if (data.memory) setFullMemory(data.memory);
      if (data.agent_memory) setAgentMemory(data.agent_memory);
      return;
    }

    if (eventType === "debug_node") {
      const now = data.timestamp ?? Date.now() / 1000;
      const durationMs = lastTimestampRef.current
        ? Math.round((now - lastTimestampRef.current) * 1000)
        : null;
      lastTimestampRef.current = now;

      const execution: NodeExecution = {
        id: `${data.step}-${data.node}-${now}`,
        node: data.node,
        step: data.step,
        action: data.action ?? null,
        target: data.target ?? null,
        memorySnapshot: data.memory_snapshot ?? null,
        timestamp: now,
        durationMs,
        isError: false,
        errorMessage: null,
        agentName: data.agent_name || null,
      };

      setExecutions(prev => [...prev, execution]);
      setCurrentNode(data.node);

      if (data.memory_snapshot) {
        setMemorySnapshot(data.memory_snapshot);
      }
    }

    if (eventType === "error") {
      const errorExecution: NodeExecution = {
        id: `error-${Date.now()}`,
        node: "error",
        step: -1,
        action: null,
        target: null,
        memorySnapshot: null,
        timestamp: Date.now() / 1000,
        durationMs: null,
        isError: true,
        errorMessage: data.message ?? "Unknown error",
        agentName: null,
      };
      setExecutions(prev => [...prev, errorExecution]);
      setCurrentNode("error");
    }

    if (eventType === "conversation_complete") {
      setIsComplete(true);
      setCurrentNode(null);
      setTotalTurns(data.total_turns ?? 0);
    }

    if (eventType === "agent_turn" && data.agent_id) {
      setExecutions(prev => {
        const copy = [...prev];
        for (let i = copy.length - 1; i >= 0; i--) {
          if (copy[i].node === "persona" && !copy[i].agentName) {
            copy[i] = { ...copy[i], agentName: data.name || data.agent_name || data.agent_id };
            break;
          }
        }
        return copy;
      });
    }
  }, []);

  const reset = useCallback(() => {
    setExecutions([]);
    setCurrentNode(null);
    setIsComplete(false);
    setIsConnected(false);
    setTotalTurns(0);
    setMemorySnapshot(null);
    setFullMemory({ risks: [], strengths: [], claims: [], contradictions: [], opinions: [] });
    setAgentMemory({});
    lastTimestampRef.current = null;
  }, []);

  const setConnected = useCallback((val: boolean) => {
    setIsConnected(val);
  }, []);

  return {
    executions,
    currentNode,
    isComplete,
    isConnected,
    totalTurns,
    memorySnapshot,
    fullMemory,
    agentMemory,
    pushEvent,
    setConnected,
    reset,
  };
}
