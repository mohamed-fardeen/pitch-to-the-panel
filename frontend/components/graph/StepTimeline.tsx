"use client";

import React, { useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Zap, 
  Activity, 
  Search, 
  Database, 
  Brain, 
  User, 
  ShieldCheck,
  ChevronRight
} from "lucide-react";

interface NodeExecution {
  node: string;
  step: number;
  action: string | null;
  agentName: string | null;
}

interface Props {
  executions: NodeExecution[];
}

const ICON_MAP: Record<string, any> = {
  controller: Brain,
  persona: User,
  memory: Database,
  reflection: Zap,
  tool: Search,
  final: ShieldCheck,
};

export function StepTimeline({ executions }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest step
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        left: scrollRef.current.scrollWidth,
        behavior: "smooth",
      });
    }
  }, [executions.length]);

  return (
    <div className="absolute bottom-8 left-8 right-8 z-50">
      <div className="bg-white/80 backdrop-blur-3xl border border-white/50 shadow-2xl rounded-[3.5rem] p-6 lg:p-8 overflow-hidden group/timeline ring-1 ring-slate-100">
        <div className="flex items-center gap-6 border-b border-slate-100 pb-6 mb-6">
           <div className="flex items-center gap-3">
              <div className="p-2.5 bg-slate-900 rounded-2xl shadow-lg ring-4 ring-slate-100">
                 <Zap className="w-5 h-5 text-white" fill="white" />
              </div>
              <div className="flex flex-col">
                 <h3 className="text-sm font-black text-slate-800 uppercase tracking-tighter leading-none">Decision Sequence</h3>
                 <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">Timeline Archive</span>
              </div>
           </div>
           
           <div className="flex-1 flex gap-2 overflow-x-hidden opacity-30 select-none">
              {[...Array(20)].map((_, i) => <div key={i} className="h-1 w-8 rounded-full bg-slate-200" />)}
           </div>

           <div className="bg-indigo-50 px-5 py-2 rounded-2xl border border-indigo-100 flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-indigo-600 animate-pulse" />
              <span className="text-[11px] font-black text-indigo-600 uppercase tracking-[0.1em]">
                {executions.length} STEPS LOGGED
              </span>
           </div>
        </div>

        <div 
          ref={scrollRef}
          className="flex gap-4 overflow-x-auto pb-4 custom-scrollbar-hide"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
        >
          {executions.length === 0 ? (
             <div className="w-full flex flex-col items-center justify-center py-4 opacity-30 space-y-2">
               <Brain className="w-8 h-8 text-slate-300" strokeWidth={1} />
               <p className="text-[11px] font-black text-slate-400 uppercase tracking-widest">Awaiting system activation</p>
             </div>
          ) : (
             <div className="flex gap-4 min-w-full">
              {executions.map((exec, idx) => {
                const isLatest = idx === executions.length - 1;
                const Icon = ICON_MAP[exec.node] || User;

                return (
                  <motion.div
                    key={`${exec.step}-${idx}`}
                    initial={{ opacity: 0, x: 20, scale: 0.9 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    whileHover={{ y: -5 }}
                    className={`
                      relative group flex-shrink-0 cursor-pointer w-48 transition-all duration-300
                    `}
                  >
                    <div className={`
                      flex flex-col gap-4 p-5 rounded-[2.5rem] border shadow-sm h-full
                      ${isLatest ? 'bg-slate-900 border-slate-900 shadow-2xl scale-105 z-20' : 'bg-white border-slate-100 hover:border-indigo-200 hover:shadow-xl'}
                    `}>
                      <div className="flex items-center justify-between">
                        <div className={`p-2 rounded-xl ${isLatest ? 'bg-indigo-500/20' : 'bg-slate-50'}`}>
                           <Icon className={`w-4 h-4 ${isLatest ? 'text-indigo-400' : 'text-slate-500'}`} />
                        </div>
                        <span className={`text-[11px] font-black tracking-tight ${isLatest ? 'text-indigo-400/80' : 'text-slate-300'}`}>
                          #{exec.step}
                        </span>
                      </div>

                      <div className="flex flex-col gap-1">
                        <span className={`text-[10px] font-black uppercase tracking-widest ${isLatest ? 'text-slate-400' : 'text-slate-300'}`}>
                          {exec.agentName || exec.node}
                        </span>
                        <p className={`text-sm font-black tracking-tight leading-tight line-clamp-2 ${isLatest ? 'text-white' : 'text-slate-800'}`}>
                          {exec.action || "Executing..."}
                        </p>
                      </div>

                      {isLatest && (
                         <div className="absolute -top-1.5 -right-1.5 flex h-4 w-4">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-4 w-4 bg-emerald-500 border-2 border-white"></span>
                         </div>
                      )}
                    </div>
                    
                    {!isLatest && (
                       <div className="absolute top-1/2 -right-2 -translate-y-1/2 text-slate-200 opacity-0 group-hover:opacity-100 transition-opacity">
                          <ChevronRight className="w-4 h-4" />
                       </div>
                    )}
                  </motion.div>
                );
              })}
             </div>
          )}
        </div>
      </div>
    </div>
  );
}
