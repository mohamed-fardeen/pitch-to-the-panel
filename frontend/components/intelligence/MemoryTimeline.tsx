"use client";

import React from "react";
import { motion } from "framer-motion";
import { 
  History, 
  AlertCircle, 
  CheckCircle2, 
  MessageCircle,
  Clock,
  ChevronRight
} from "lucide-react";

interface MemorySnapshot {
  step: number;
  risks_count: number;
  strengths_count: number;
  contradiction_count: number;
  last_agent?: string;
}

interface MemoryTimelineProps {
  history: MemorySnapshot[];
}

export const MemoryTimeline: React.FC<MemoryTimelineProps> = ({ history }) => {
  if (!history || history.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-20 opacity-30 text-center">
        <Clock className="w-12 h-12 mb-4 text-slate-300" />
        <p className="text-sm font-black uppercase tracking-widest text-slate-400">Awaiting Memory Evolution...</p>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="flex items-center gap-3 mb-10">
        <div className="p-3 bg-indigo-600 rounded-2xl shadow-lg ring-4 ring-indigo-50">
          <History className="w-6 h-6 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-black text-slate-800 tracking-tighter uppercase">Memory Timeline</h2>
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Tracking logical evolution step by step</p>
        </div>
      </div>

      <div className="relative">
        {/* Connector Line */}
        <div className="absolute left-6 top-8 bottom-8 w-[2px] bg-slate-100" />

        <div className="space-y-12">
          {history.map((snapshot, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.1 }}
              className="relative flex items-start gap-12 group"
            >
              {/* Step Marker */}
              <div className={`
                relative z-10 w-12 h-12 rounded-2xl flex items-center justify-center shadow-md bg-white border-2 transition-colors duration-500
                ${snapshot.contradiction_count > 0 ? 'border-rose-400' : 'border-indigo-400'}
              `}>
                <span className="text-sm font-black text-slate-800">{snapshot.step}</span>
              </div>

              {/* Card */}
              <div className="flex-1 bg-white rounded-3xl border border-slate-100 p-6 shadow-sm group-hover:shadow-xl group-hover:border-indigo-100 transition-all duration-300">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Triggered by</span>
                    <span className="px-3 py-1 bg-slate-900 text-white text-[9px] font-black rounded-lg uppercase tracking-tight">
                      {snapshot.last_agent || 'System'}
                    </span>
                  </div>
                  {snapshot.contradiction_count > 0 && (
                    <div className="flex items-center gap-1.5 px-3 py-1 bg-rose-50 text-rose-600 text-[9px] font-black rounded-lg border border-rose-100">
                      <AlertCircle className="w-3 h-3" />
                      CONTRADICTION DETECTED
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-6">
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-emerald-600">
                      <CheckCircle2 className="w-3 h-3" />
                      <span className="text-[10px] font-bold uppercase tracking-widest">Strengths</span>
                    </div>
                    <p className="text-2xl font-black text-slate-800">{snapshot.strengths_count}</p>
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-rose-600">
                      <AlertCircle className="w-3 h-3" />
                      <span className="text-[10px] font-bold uppercase tracking-widest">Risks</span>
                    </div>
                    <p className="text-2xl font-black text-slate-800">{snapshot.risks_count}</p>
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-amber-600">
                      <MessageCircle className="w-3 h-3" />
                      <span className="text-[10px] font-bold uppercase tracking-widest">Conflicts</span>
                    </div>
                    <p className="text-2xl font-black text-slate-800">{snapshot.contradiction_count}</p>
                  </div>
                </div>

                {/* Progress Visualizer */}
                <div className="mt-6 flex h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
                   <div 
                     className="bg-emerald-500 h-full transition-all duration-1000" 
                     style={{ width: `${(snapshot.strengths_count / 10) * 100}%` }} 
                   />
                   <div 
                     className="bg-rose-500 h-full transition-all duration-1000" 
                     style={{ width: `${(snapshot.risks_count / 10) * 100}%` }} 
                   />
                   <div 
                     className="bg-amber-500 h-full transition-all duration-1000" 
                     style={{ width: `${(snapshot.contradiction_count / 10) * 100}%` }} 
                   />
                </div>
              </div>

              {/* Arrow */}
              <div className="flex items-center h-12 opacity-0 group-hover:opacity-100 transition-opacity">
                <ChevronRight className="w-5 h-5 text-indigo-400 ml-4" />
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
};
