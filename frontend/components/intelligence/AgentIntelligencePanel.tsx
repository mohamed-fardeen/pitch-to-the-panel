"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BrainCircuit, Network, History, LayoutGrid } from "lucide-react";
import { AgentMindsView } from "./AgentMindsView";
import { MemoryTimeline } from "./MemoryTimeline";
import { KnowledgeGraph } from "./KnowledgeGraph";

interface AgentIntelligencePanelProps {
  memory: any;
  agentMemory: any;
  memoryHistory: any[];
  activeAgentId: string | null;
  personas: Array<{id: string, name: string, role: string}>;
}

export const AgentIntelligencePanel: React.FC<AgentIntelligencePanelProps> = ({
  memory,
  agentMemory,
  memoryHistory,
  activeAgentId,
  personas
}) => {
  const [tab, setTab] = useState<"minds" | "timeline" | "graph">("minds");

  const tabs = [
    { id: "minds", label: "Agent Minds", icon: LayoutGrid },
    { id: "timeline", label: "Evolution", icon: History },
    { id: "graph", label: "Logic Graph", icon: Network },
  ];

  return (
    <div className="flex flex-col h-full bg-white rounded-[3rem] shadow-2xl border border-slate-100 overflow-hidden">
      {/* Tab Header */}
      <div className="flex items-center justify-between p-8 border-b border-slate-50 bg-slate-50/50">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-slate-900 rounded-2xl">
            <BrainCircuit className="w-5 h-5 text-indigo-400" />
          </div>
          <h2 className="text-xl font-black text-slate-800 tracking-tighter uppercase">Intelligence Hub</h2>
        </div>

        <div className="flex bg-white p-1.5 rounded-2xl shadow-sm border border-slate-100">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id as any)}
              className={`
                flex items-center gap-2 px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all
                ${tab === t.id ? "bg-slate-900 text-white shadow-lg" : "text-slate-400 hover:text-slate-600"}
              `}
            >
              <t.icon className="w-4 h-4" />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <AnimatePresence mode="wait">
          {tab === "minds" && (
            <motion.div
              key="minds"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <AgentMindsView 
                agentMemory={agentMemory} 
                activeAgentId={activeAgentId} 
                personas={personas} 
              />
            </motion.div>
          )}

          {tab === "timeline" && (
            <motion.div
              key="timeline"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <MemoryTimeline history={memoryHistory} />
            </motion.div>
          )}

          {tab === "graph" && (
            <motion.div
              key="graph"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.05 }}
              className="p-8 h-full"
            >
               <KnowledgeGraph 
                 memory={memory} 
                 agentMemory={agentMemory} 
                 personas={personas} 
               />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Footer Status */}
      <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-center gap-2">
         <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
         <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Neural Stream Active</span>
      </div>
    </div>
  );
};
