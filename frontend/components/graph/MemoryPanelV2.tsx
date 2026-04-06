"use client";

import React, { useRef, useEffect } from "react";
import { motion, useAnimation } from "framer-motion";
import { 
  AlertTriangle, 
  TrendingUp, 
  ShieldCheck, 
  MessageSquare, 
  MinusCircle
} from "lucide-react";

interface Props {
  memory: {
    risks: string[];
    strengths: string[];
    claims: string[];
    contradictions: string[];
    opinions: string[];
  };
}

const SECTION_CONFIG = [
  { key: "risks", label: "Risks", icon: AlertTriangle, color: "text-red-500", bg: "bg-red-50/30", border: "border-red-100", glow: "shadow-red-500/10" },
  { key: "strengths", label: "Strengths", icon: TrendingUp, color: "text-emerald-500", bg: "bg-emerald-50/30", border: "border-emerald-100", glow: "shadow-emerald-500/10" },
  { key: "claims", label: "Key Claims", icon: ShieldCheck, color: "text-blue-500", bg: "bg-blue-50/30", border: "border-blue-100", glow: "shadow-blue-500/10" },
  { key: "contradictions", label: "Conflicts", icon: MinusCircle, color: "text-amber-500", bg: "bg-amber-50/30", border: "border-amber-100", glow: "shadow-amber-500/10" },
  { key: "opinions", label: "Agent Opinions", icon: MessageSquare, color: "text-indigo-500", bg: "bg-indigo-50/30", border: "border-indigo-100", glow: "shadow-indigo-500/10" },
];

export function MemoryPanelV2({ memory }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <div className="flex flex-col gap-8 p-10 h-full overflow-y-auto custom-scrollbar relative z-30">
      <div className="flex items-center gap-4 mb-2">
        <div className="w-14 h-14 rounded-3xl bg-slate-900 flex items-center justify-center shadow-2xl scale-110">
           <span className="material-symbols-outlined text-white text-3xl">database</span>
        </div>
        <div className="flex flex-col">
           <h2 className="text-xl font-black text-slate-800 uppercase tracking-tighter leading-none">Global Memory</h2>
           <span className="text-[11px] font-black text-slate-300 uppercase tracking-widest mt-1">Real-time Intelligence Feed</span>
        </div>
      </div>

      <div className="space-y-10 pb-20">
        {SECTION_CONFIG.map((section) => {
          const items = memory[section.key as keyof typeof memory] || [];
          const Icon = section.icon;

          return (
            <div key={section.key} className="space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                <div className="flex items-center gap-3">
                  <Icon className={`w-5 h-5 ${section.color}`} />
                  <span className="text-[12px] font-black text-slate-500 uppercase tracking-widest">{section.label}</span>
                </div>
                <span className={`text-[11px] font-black ${section.color} px-3 py-0.5 rounded-full bg-white border ${section.border} shadow-sm`}>
                  {items.length}
                </span>
              </div>

              <div className="flex flex-col gap-3">
                {items.length === 0 ? (
                   <div className="py-8 border-2 border-dashed border-slate-100 rounded-[2rem] flex flex-col items-center justify-center gap-2 opacity-50">
                     <span className="text-[11px] font-bold text-slate-300 uppercase tracking-widest italic">No insights identified</span>
                   </div>
                ) : (
                  items.slice().reverse().map((item, idx) => (
                    <MemoryItem 
                      key={`${section.key}-${item}-${idx}`} 
                      item={item} 
                      section={section} 
                      isNew={idx === 0} 
                    />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MemoryItem({ item, section, isNew }: any) {
  return (
    <motion.div
      initial={isNew ? { x: 50, opacity: 0, scale: 0.95 } : { opacity: 1, scale: 1 }}
      animate={{ x: 0, opacity: 1, scale: 1 }}
      whileHover={{ y: -2, x: -5 }}
      transition={{ 
        type: "spring", 
        stiffness: 400, 
        damping: 30,
        delay: isNew ? 0.1 : 0
      }}
      className={`
        p-4 rounded-[1.8rem] border shadow-sm transition-all duration-500
        ${isNew ? `${section.bg} ${section.border} ring-4 ring-white` : 'bg-white border-slate-50'}
        ${section.glow} group hover:shadow-xl hover:border-white
      `}
    >
      <div className="flex gap-4">
        <div className={`mt-1 h-2 w-2 rounded-full shrink-0 ${section.color.replace('text', 'bg')} ${isNew ? 'animate-ping' : ''}`} />
        <p className="text-xs font-bold text-slate-700 leading-relaxed antialiased first-letter:uppercase">
          {item}
        </p>
      </div>
    </motion.div>
  );
}
