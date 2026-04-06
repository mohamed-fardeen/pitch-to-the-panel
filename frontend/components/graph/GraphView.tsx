"use client";

import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  ConnectionLineType,
  MarkerType,
  ReactFlowProvider,
} from "reactflow";
import "reactflow/dist/style.css";

import { AgentNode } from "./AgentNode";
import { AnimatedEdge } from "./AnimatedEdge";
import { DebugStreamState } from "../analytics/useDebugStream";
import { MemoryPanelV2 } from "./MemoryPanelV2";
import { StepTimeline } from "./StepTimeline";
import { Activity, ShieldCheck, Database, Target, BrainCircuit } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const nodeTypes = { agent: AgentNode };
const edgeTypes = { animated: AnimatedEdge };

// Radial Layout Constants
const CENTER_X = 600;
const CENTER_Y = 400;
const RADIUS = 350;

const AGENT_ORDER = [
  "persona",
  "memory",
  "tool",
  "pitcher",
  "reflection",
  "final",
];

const NODE_COLORS: Record<string, string> = {
  controller: "rgb(79 70 229)", // indigo-600
  persona: "rgb(6 182 212)",   // cyan-500
  memory: "rgb(16 185 129)",   // emerald-500
  reflection: "rgb(245 158 11)", // amber-500
  tool: "rgb(234 179 8)",      // yellow-500
  pitcher: "rgb(244 63 94)",   // rose-500
  final: "rgb(139 92 246)",    // purple-500
};

interface GraphViewProps {
  debugStream: DebugStreamState;
}

function GraphContent({ debugStream }: GraphViewProps) {
  const { executions, currentNode, fullMemory } = debugStream;
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const completedNodesRef = useRef<Set<string>>(new Set());

  const lastExec = useMemo(() => executions[executions.length - 1], [executions]);

  // Initializing Neural System Layout
  useEffect(() => {
    const initialNodes = [
      {
        id: "controller",
        type: "agent",
        position: { x: CENTER_X, y: CENTER_Y },
        data: { type: "controller", label: "Controller", isActive: false, step: 0, action: null, isCompleted: false },
      },
      ...AGENT_ORDER.map((type, idx) => {
        const angle = (idx / AGENT_ORDER.length) * 2 * Math.PI - Math.PI / 2;
        return {
          id: type,
          type: "agent",
          position: {
            x: CENTER_X + RADIUS * Math.cos(angle),
            y: CENTER_Y + RADIUS * Math.sin(angle),
          },
          data: { type, label: type, isActive: false, step: 0, action: null, isCompleted: false },
        };
      }),
    ];

    const initialEdges = AGENT_ORDER.map(type => ({
      id: `controller-${type}`,
      source: "controller",
      target: type,
      type: "animated",
      data: { isActive: false, color: NODE_COLORS[type], label: "" },
      markerEnd: { type: MarkerType.ArrowClosed, color: "rgb(203 213 225)" } as any,
    }));

    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [setNodes, setEdges]);

  // Reactive Logic: Node & Edge Synchronization
  useEffect(() => {
    if (!lastExec) return;
    
    // Mark node as completed in track list
    completedNodesRef.current.add(lastExec.node);

    setNodes(nds => nds.map(node => ({
      ...node,
      data: {
        ...node.data,
        isActive: node.id === lastExec.node,
        isCompleted: completedNodesRef.current.has(node.id),
        step: lastExec.step,
        action: lastExec.action,
        agentName: lastExec.agentName,
      }
    })));

    setEdges(eds => eds.map(edge => {
      const isTargetActive = edge.target === lastExec.node;
      const isSourceController = edge.source === "controller";
      
      return {
        ...edge,
        data: {
          ...edge.data,
          isActive: isTargetActive && isSourceController,
          label: lastExec.action || "",
        },
        markerEnd: { 
          ...(edge.markerEnd as any), 
          color: (isTargetActive && isSourceController) ? NODE_COLORS[edge.target] : "rgb(203 213 225)"
        }
      };
    }));

  }, [lastExec, setNodes, setEdges]);

  return (
    <div className="flex-1 flex flex-col relative bg-white bg-dot-pattern min-h-screen overflow-hidden">
      {/* Central Thinking Radial Glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1200px] h-[1200px] bg-[radial-gradient(circle_at_center,_rgba(99,102,241,0.05)_0%,_transparent_70%)] pointer-events-none z-0" />

      {/* Header Info Overlay */}
      <div className="absolute top-12 left-12 z-20 space-y-2 pointer-events-none">
        <h2 className="text-4xl font-black text-slate-800 tracking-tighter uppercase mb-0.5">Neural Graph</h2>
        <div className="flex items-center gap-2">
           <div className={`w-2 h-2 rounded-full ${debugStream.isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
           <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{debugStream.isConnected ? 'System Live' : 'Offline'}</span>
        </div>
      </div>

      {/* WOW FEATURE: Floating Action Display (Top-Center) */}
      <AnimatePresence>
        {lastExec && (
          <motion.div
            key={lastExec.step}
            initial={{ y: -50, opacity: 0, scale: 0.8 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 20, opacity: 0, scale: 0.9 }}
            className="absolute top-12 left-1/2 -translate-x-1/2 z-50 pointer-events-none"
          >
            <div className="bg-slate-900 shadow-2xl rounded-[3rem] px-10 py-5 flex items-center gap-8 border border-white/10 ring-8 ring-slate-900/5">
               <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-indigo-500/20 rounded-2xl">
                     <BrainCircuit className="w-5 h-5 text-indigo-400" />
                  </div>
                  <div className="flex flex-col">
                     <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest leading-none mb-1">Controller Intent</span>
                     <span className="text-sm font-black text-white antialiased tracking-tight">{lastExec.action || "Synthesizing Request"}</span>
                  </div>
               </div>
               
               <div className="w-[1px] h-10 bg-white/10" />

               <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-cyan-500/20 rounded-2xl">
                     <Target className="w-5 h-5 text-cyan-400" />
                  </div>
                  <div className="flex flex-col">
                     <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest leading-none mb-1">Target Persona</span>
                     <span className="text-sm font-black text-white antialiased tracking-tight line-clamp-1 max-w-[120px]">{lastExec.agentName || lastExec.node.toUpperCase()}</span>
                  </div>
               </div>

               <div className="w-[1px] h-10 bg-white/10" />

               <div className="flex flex-col items-center min-w-[60px]">
                  <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-0.5">Step</span>
                  <span className="text-xl font-black text-indigo-400 tracking-tighter">#{lastExec.step}</span>
               </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 flex relative overflow-hidden">
        <div className="flex-1 relative z-10">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            connectionLineType={ConnectionLineType.SmoothStep}
            fitView
            minZoom={0.2}
            maxZoom={2}
          >
            <Controls className="!bg-white/80 !backdrop-blur-md !border-slate-100 !shadow-xl !rounded-xl !m-8" />
          </ReactFlow>
        </div>

        <div className="w-[450px] relative z-30 overflow-hidden border-l border-slate-100 shadow-2xl bg-white/70 backdrop-blur-3xl">
           <MemoryPanelV2 memory={fullMemory} />
        </div>
      </div>

      {/* Bottom Sequence Bar */}
      <div className="relative z-40">
         <StepTimeline executions={executions} />
      </div>

      {/* Ambient Neural Spikes Background Effect */}
      {currentNode && (
         <div className="absolute inset-0 pointer-events-none z-0">
             <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[900px] bg-indigo-500/5 blur-[150px] animate-pulse-slow" />
         </div>
      )}
    </div>
  );
}

export function GraphView({ debugStream }: GraphViewProps) {
  return (
    <ReactFlowProvider>
       <GraphContent debugStream={debugStream} />
    </ReactFlowProvider>
  );
}
