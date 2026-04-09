"use client";

import React, { useMemo, useEffect } from "react";
import ReactFlow, { 
  Background, 
  Controls, 
  useNodesState, 
  useEdgesState,
  Handle,
  Position,
  NodeProps,
  MarkerType
} from "reactflow";
import "reactflow/dist/style.css";
import { motion } from "framer-motion";
import { Brain, ShieldAlert, BadgeCheck, FileText } from "lucide-react";

// --- Custom Nodes ---

const BaseNode = ({ children, color, label, icon: Icon, type }: any) => (
  <div className={`p-[2px] rounded-3xl bg-gradient-to-br ${color} shadow-lg min-w-[150px]`}>
    <div className="bg-white rounded-[1.4rem] p-4 flex flex-col items-center text-center gap-2">
      <div className={`p-2 rounded-xl bg-slate-50 text-slate-600`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="flex flex-col">
        <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">{type}</span>
        <span className="text-xs font-black text-slate-800 tracking-tight leading-tight">{label}</span>
      </div>
      {children}
    </div>
  </div>
);

const PitchNode = ({ data }: NodeProps) => (
  <div className="relative">
    <BaseNode color="from-indigo-600 to-blue-700" label="Current Pitch" type="Source" icon={FileText} />
    <Handle type="source" position={Position.Bottom} className="!opacity-0" />
  </div>
);

const AgentMindNode = ({ data }: NodeProps) => (
  <div className="relative">
    <Handle type="target" position={Position.Top} className="!opacity-0" />
    <BaseNode color="from-cyan-400 to-blue-500" label={data.label} type="Agent" icon={Brain} />
    <Handle type="source" position={Position.Bottom} className="!opacity-0" />
  </div>
);

const RiskNode = ({ data }: NodeProps) => (
  <div className="relative">
    <Handle type="target" position={Position.Top} className="!opacity-0" />
    <BaseNode color="from-rose-400 to-pink-500" label={data.label} type="Risk" icon={ShieldAlert} />
  </div>
);

const ClaimNode = ({ data }: NodeProps) => (
  <div className="relative">
    <Handle type="target" position={Position.Top} className="!opacity-0" />
    <BaseNode color="from-emerald-400 to-teal-500" label={data.label} type="Claim" icon={BadgeCheck} />
  </div>
);

const nodeTypes = {
  pitch: PitchNode,
  agent: AgentMindNode,
  risk: RiskNode,
  claim: ClaimNode
};

// --- Main component ---

interface KnowledgeGraphProps {
  memory: any;
  agentMemory: any;
  personas: any[];
}

export const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ memory, agentMemory, personas }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    const newNodes: any[] = [];
    const newEdges: any[] = [];

    // 1. Root Node
    newNodes.push({
      id: "pitch",
      type: "pitch",
      data: { label: "Pitch" },
      position: { x: 500, y: 0 }
    });

    // 2. Agent Nodes
    personas.forEach((p, i) => {
      const xPos = 200 + i * 300;
      newNodes.push({
        id: p.id,
        type: "agent",
        data: { label: p.name },
        position: { x: xPos, y: 200 }
      });

      newEdges.push({
        id: `pitch-${p.id}`,
        source: "pitch",
        target: p.id,
        animated: true,
        style: { stroke: "#cbd5e1", strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#cbd5e1" }
      });

      // 3. Claims/Risks from this agent's memory
      const am = agentMemory[p.id] || {};
      const risks = am.concerns || [];
      const claims = am.positives || [];

      risks.slice(0, 2).forEach((risk: string, ri: number) => {
        const nodeId = `risk-${p.id}-${ri}`;
        newNodes.push({
          id: nodeId,
          type: "risk",
          data: { label: risk },
          position: { x: xPos - 50 + ri * 100, y: 400 + ri * 50 }
        });
        newEdges.push({
          id: `${p.id}-${nodeId}`,
          source: p.id,
          target: nodeId,
          style: { stroke: "#f43f5e", strokeWidth: 1, strokeDasharray: "5 5" },
        });
      });

      claims.slice(0, 2).forEach((claim: string, ci: number) => {
        const nodeId = `claim-${p.id}-${ci}`;
        newNodes.push({
          id: nodeId,
          type: "claim",
          data: { label: claim },
          position: { x: xPos + 150 + ci * 100, y: 400 + ci * 50 }
        });
        newEdges.push({
          id: `${p.id}-${nodeId}`,
          source: p.id,
          target: nodeId,
          style: { stroke: "#10b981", strokeWidth: 1, strokeDasharray: "5 5" },
        });
      });
    });

    setNodes(newNodes);
    setEdges(newEdges);
  }, [memory, agentMemory, personas]);

  return (
    <div className="h-[600px] w-full bg-slate-50 rounded-[3rem] overflow-hidden border border-slate-100 shadow-inner">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
      >
        <Background color="#cbd5e1" gap={20} />
        <Controls />
      </ReactFlow>
    </div>
  );
};
