"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";

interface AgentThought {
  concerns?: string[];
  agent_opinions?: string[];
  disagreements?: string[];
  risks?: string[];
  strengths?: string[];
  claims?: string[];
  contradictions?: string[];
}

interface AgentThoughtsPanelProps {
  agentMemory: Record<string, AgentThought>;
  agentsConfig: Record<string, { name: string; role: string }>;
}

const AGENT_COLORS: Record<string, string> = {
  vc: "#4f46e5",
  enthusiastic: "#06b6d4",
  hostile: "#ef4444",
  expert: "#8b5cf6",
  competitor: "#f59e0b",
  beginner: "#10b981",
  suresh: "#ea580c",
  design_critic: "#ec4899",
};

const AGENT_ICONS: Record<string, string> = {
  vc: "trending_up",
  enthusiastic: "favorite",
  hostile: "warning",
  expert: "science",
  competitor: "target",
  beginner: "help",
  suresh: "store",
  design_critic: "palette",
};

export function AgentThoughtsPanel({ agentMemory, agentsConfig }: AgentThoughtsPanelProps) {
  const agents = Object.entries(agentMemory || {}).filter(([id]) => id in (agentsConfig || {}));
  
  const hasAnyThoughts = agents.some(([, mem]) => 
    (mem.concerns?.length || 0) + (mem.agent_opinions?.length || 0) + (mem.disagreements?.length || 0) + 
    (mem.risks?.length || 0) + (mem.strengths?.length || 0) + (mem.claims?.length || 0) + (mem.contradictions?.length || 0) > 0
  );

  return (
    <div className="flex flex-col h-full bg-slate-50/50 backdrop-blur-2xl border-l border-slate-200/60 shadow-inner">
      {/* Header */}
      <div className="p-8 border-b border-slate-200/60 bg-white/60 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-200">
            <span className="material-symbols-outlined text-xl text-white" style={{ fontVariationSettings: "'FILL' 1" }}>psychology</span>
          </div>
          <div>
            <h3 className="text-sm font-black text-slate-800 uppercase tracking-widest">Agent Thoughts</h3>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-tight">Private Reasoning • Live</p>
            </div>
          </div>
        </div>
        <span className="material-symbols-outlined text-slate-300">lock_open</span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
        {!hasAnyThoughts ? (
          <div className="h-full flex flex-col items-center justify-center py-20 opacity-30 text-center space-y-4">
            <div className="w-16 h-16 rounded-[2rem] border-2 border-dashed border-slate-300 flex items-center justify-center bg-slate-50/50">
              <span className="material-symbols-outlined text-3xl text-slate-300">lock</span>
            </div>
            <div className="space-y-1">
              <p className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em]">Silence of the Minds</p>
              <p className="text-[10px] text-slate-400 font-medium">Thoughts appear as agents process the pitch</p>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {agents.map(([agentId, mem]) => {
              const config = agentsConfig[agentId];
              if (!config) return null;

              const color = AGENT_COLORS[agentId] || "#64748b";
              const icon = AGENT_ICONS[agentId] || "person";

              // Collect and flatten latest thoughts
              const allThoughts: { text: string; type: string; icon: string; color: string; bg: string }[] = [];

              if (mem.concerns) mem.concerns.slice(-2).forEach(text => allThoughts.push({ text, type: 'concern', icon: 'warning', color: 'text-amber-600', bg: 'bg-amber-50' }));
              if (mem.agent_opinions) mem.agent_opinions.slice(-2).forEach(text => allThoughts.push({ text, type: 'opinion', icon: 'lightbulb', color: 'text-indigo-600', bg: 'bg-indigo-50' }));
              if (mem.disagreements) mem.disagreements.slice(-2).forEach(text => allThoughts.push({ text, type: 'disagreement', icon: 'gavel', color: 'text-rose-600', bg: 'bg-rose-50' }));
              if (mem.risks) mem.risks.slice(-2).forEach(text => allThoughts.push({ text, type: 'risk', icon: 'error', color: 'text-red-600', bg: 'bg-red-50' }));
              if (mem.strengths) mem.strengths.slice(-1).forEach(text => allThoughts.push({ text, type: 'strength', icon: 'add_task', color: 'text-emerald-600', bg: 'bg-emerald-50' }));

              const displayThoughts = allThoughts.slice(-5); // Rule 3: Only latest 3-5 items

              if (displayThoughts.length === 0) return null;

              return (
                <motion.div
                  key={agentId}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="bg-white/80 rounded-[2rem] border border-slate-100 shadow-sm overflow-hidden"
                >
                  {/* Agent Header */}
                  <div className="flex items-center gap-3 p-5 border-b border-slate-50 transition-colors" style={{ borderLeftWidth: 6, borderLeftColor: color }}>
                    <div className="w-8 h-8 rounded-xl flex items-center justify-center shadow-inner" style={{ backgroundColor: `${color}15` }}>
                      <span className="material-symbols-outlined text-sm" style={{ color, fontVariationSettings: "'FILL' 1" }}>{icon}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest leading-none mb-1">{config.role}</p>
                      <h4 className="text-sm font-black text-slate-800 tracking-tight block truncate">{config.name}</h4>
                    </div>
                  </div>

                  {/* Thought Items */}
                  <div className="p-4 space-y-3">
                    <AnimatePresence initial={false}>
                      {displayThoughts.map((thought, i) => (
                        <motion.div
                          key={`${agentId}-${thought.type}-${thought.text.substring(0, 20)}`}
                          initial={{ opacity: 0, scale: 0.95, y: 5 }}
                          animate={{ opacity: 1, scale: 1, y: 0 }}
                          transition={{ 
                            type: "spring",
                            stiffness: 400,
                            damping: 30
                          }}
                          className={`flex items-start gap-3 p-3.5 rounded-2xl ${thought.bg} border border-white relative group overflow-hidden`}
                        >
                          {/* Entry Glow Effect */}
                          <motion.div 
                            initial={{ opacity: 1 }}
                            animate={{ opacity: 0 }}
                            transition={{ duration: 1.5 }}
                            className="absolute inset-0 bg-white shadow-[inset_0_0_20px_rgba(255,255,255,0.8)] pointer-events-none"
                          />
                          
                          <div className={`mt-0.5 shrink-0 w-5 h-5 rounded-lg flex items-center justify-center bg-white shadow-sm`}>
                             <span className={`material-symbols-outlined text-[12px] ${thought.color}`} style={{ fontVariationSettings: "'FILL' 1" }}>{thought.icon}</span>
                          </div>
                          
                          <span className="text-[11px] font-medium text-slate-600 leading-normal flex-1">
                            {thought.text}
                          </span>
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer Branding */}
      <div className="p-6 border-t border-slate-100 bg-white/40">
         <div className="flex items-center justify-center gap-2 opacity-20">
            <span className="text-[8px] font-black uppercase tracking-[0.3em] text-slate-400">Memory Integrity Subsystem</span>
         </div>
      </div>
    </div>
  );
}
