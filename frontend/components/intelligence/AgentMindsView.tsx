"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Brain, 
  Target, 
  AlertTriangle, 
  PlusCircle, 
  TrendingUp, 
  MessageSquare,
  ShieldAlert,
  Zap
} from "lucide-react";

interface AgentMemory {
  stance: string;
  focus?: string;
  concerns: string[];
  positives: string[];
  confidence: number;
  disagreements: string[];
  notes: string[];
}

interface AgentMindsViewProps {
  agentMemory: Record<string, AgentMemory>;
  activeAgentId: string | null;
  personas: Array<{id: string, name: string, role: string}>;
}

export const AgentMindsView: React.FC<AgentMindsViewProps> = ({ 
  agentMemory, 
  activeAgentId, 
  personas 
}) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 p-6">
      <AnimatePresence>
        {personas.map((persona) => {
          const rawMemory = agentMemory[persona.id] || {};
          const memory = {
            stance: rawMemory.stance || "Neutral",
            concerns: Array.isArray(rawMemory.concerns) ? rawMemory.concerns : [],
            positives: Array.isArray(rawMemory.positives) ? rawMemory.positives : [],
            confidence: typeof rawMemory.confidence === 'number' ? rawMemory.confidence : 50,
            disagreements: Array.isArray(rawMemory.disagreements) ? rawMemory.disagreements : [],
            notes: Array.isArray(rawMemory.notes) ? rawMemory.notes : []
          };
          
          const isActive = activeAgentId === persona.id;

          return (
            <motion.div
              key={persona.id}
              layout
              initial={{ opacity: 0, y: 20 }}
              animate={{ 
                opacity: 1, 
                y: 0,
                scale: isActive ? 1.02 : 1,
                borderColor: isActive ? "rgb(99, 102, 241)" : "rgb(241, 245, 249)"
              }}
              className={`
                relative bg-white rounded-[2rem] border-2 p-6 shadow-sm transition-all duration-500
                ${isActive ? "shadow-indigo-200 shadow-2xl ring-4 ring-indigo-50" : "hover:shadow-md"}
              `}
            >
              {/* Active Indicator */}
              {isActive && (
                <div className="absolute -top-3 -right-3 flex items-center gap-2 bg-indigo-600 text-white text-[10px] font-black uppercase px-4 py-1.5 rounded-full shadow-lg animate-bounce">
                  <Zap className="w-3 h-3 fill-current" />
                  Thinking...
                </div>
              )}

              {/* Header */}
              <div className="flex flex-col mb-6">
                <div className="flex items-center gap-3 mb-1">
                  <div className={`p-2 rounded-xl bg-slate-100 ${isActive ? 'bg-indigo-100' : ''}`}>
                    <Brain className={`w-5 h-5 ${isActive ? 'text-indigo-600' : 'text-slate-500'}`} />
                  </div>
                  <div>
                    <h3 className="text-lg font-black text-slate-800 leading-none">{persona.name}</h3>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{persona.role}</span>
                  </div>
                </div>
              </div>

              {/* Status Bar */}
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                  <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-1">Stance</span>
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${getStanceColor(memory.stance)}`} />
                    <span className="text-sm font-black text-slate-700">{memory.stance}</span>
                  </div>
                </div>
                <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                  <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block mb-1">Confidence</span>
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-emerald-500" />
                    <span className="text-sm font-black text-slate-700">{memory.confidence}%</span>
                  </div>
                </div>
              </div>

              {/* Content Sections */}
              <div className="space-y-6">
                {/* Positives */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <PlusCircle className="w-3 h-3 text-emerald-500" />
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Identified Strengths</span>
                  </div>
                  <div className="space-y-1.5">
                    {memory.positives.length > 0 ? memory.positives.map((p, i) => (
                      <div key={i} className="text-[11px] font-medium text-slate-600 bg-emerald-50/50 px-3 py-1.5 rounded-lg border border-emerald-100">
                        {p}
                      </div>
                    )) : <div className="text-[11px] text-slate-300 italic px-3">Awaiting signal...</div>}
                  </div>
                </div>

                {/* Concerns */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="w-3 h-3 text-rose-500" />
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Risks & Concerns</span>
                  </div>
                  <div className="space-y-1.5">
                    {memory.concerns.length > 0 ? memory.concerns.map((c, i) => (
                      <div key={i} className="text-[11px] font-medium text-slate-600 bg-rose-50/50 px-3 py-1.5 rounded-lg border border-rose-100">
                        {c}
                      </div>
                    )) : <div className="text-[11px] text-slate-300 italic px-3">No major risks noted.</div>}
                  </div>
                </div>

                {/* Disagreements */}
                {memory.disagreements?.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-3 h-3 text-amber-500" />
                      <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Open Disagreements</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {memory.disagreements.map((d, i) => (
                        <div key={i} className="text-[9px] font-black text-amber-700 bg-amber-50 px-2 py-1 rounded-md border border-amber-200 uppercase">
                          {d}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
};

function getStanceColor(stance: any) {
  const s = String(stance || "").toLowerCase();
  if (s.includes("skeptical") || s.includes("critical")) return "bg-rose-500";
  if (s.includes("optimistic") || s.includes("supportive")) return "bg-emerald-500";
  return "bg-slate-400";
}
