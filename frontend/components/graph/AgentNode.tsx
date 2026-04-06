"use client";

import React, { memo } from "react";
import { Handle, Position, NodeProps } from "reactflow";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Gavel, 
  Brain, 
  Database, 
  Wand2, 
  User, 
  Search, 
  Zap,
  CheckCircle2,
  Clock
} from "lucide-react";

const NODE_CONFIG: Record<string, { color: string, glow: string, icon: any, label: string }> = {
  controller: { color: "from-indigo-600 to-blue-700", glow: "shadow-indigo-500/50", icon: Brain, label: "Controller" },
  persona: { color: "from-cyan-400 to-blue-500", glow: "shadow-cyan-400/40", icon: User, label: "Agent" },
  memory: { color: "from-emerald-400 to-teal-500", glow: "shadow-emerald-400/40", icon: Database, label: "Memory" },
  reflection: { color: "from-orange-400 to-amber-500", glow: "shadow-orange-400/40", icon: Wand2, label: "Reflection" },
  tool: { color: "from-yellow-400 to-orange-500", glow: "shadow-yellow-400/40", icon: Search, label: "Research Tool" },
  pitcher: { color: "from-pink-400 to-rose-500", glow: "shadow-pink-400/40", icon: Gavel, label: "Pitcher" },
  final: { color: "from-purple-400 to-indigo-500", glow: "shadow-purple-400/40", icon: Zap, label: "Verdict" },
};

export const AgentNode = memo(({ data }: NodeProps) => {
  const { type, isActive, step, action, agentName, isCompleted } = data;
  const config = NODE_CONFIG[type] || NODE_CONFIG.persona;
  const Icon = config.icon;
  const isController = type === "controller";

  return (
    <div className="relative">
      <motion.div
        layout
        whileHover={{ y: -5, scale: 1.02 }}
        animate={{
          scale: isActive ? (isController ? 1.15 : 1.12) : 1,
          opacity: isActive ? 1 : (isCompleted ? 0.8 : 0.6),
        }}
        className={`
          relative rounded-[2.5rem] p-[2px] transition-all duration-700
          ${isActive ? `bg-gradient-to-br ${config.color} ${config.glow} shadow-2xl animate-neural-pulse` : 'bg-slate-200/30 shadow-sm'}
          ${isController ? 'w-56 h-56' : 'w-48 h-48'}
          ${isActive && isController ? 'animate-breathing' : ''}
          ${isCompleted && !isActive ? 'border-2 border-emerald-400/30' : ''}
        `}
      >
        <div className="bg-white/90 backdrop-blur-3xl rounded-[2.4rem] h-full flex flex-col items-center justify-center p-6 gap-3 relative overflow-hidden group">
          {/* Subtle Neural Background Lines (SVG) */}
          <div className="absolute inset-0 opacity-[0.03] pointer-events-none">
             <svg width="100%" height="100%" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="40" fill="none" stroke="currentColor" strokeWidth="0.5" />
                <path d="M10 50 L90 50 M50 10 L50 90" stroke="currentColor" strokeWidth="0.2" />
             </svg>
          </div>

          {/* Icon Area */}
          <motion.div 
            animate={isActive ? { rotate: [0, 5, -5, 0] } : {}}
            transition={{ duration: 4, repeat: Infinity }}
            className={`
              p-4 rounded-[1.5rem] bg-gradient-to-br ${config.color} shadow-lg 
              ${isActive ? 'ring-4 ring-white/50' : 'opacity-80'}
            `}
          >
            <Icon className={`text-white ${isController ? 'w-8 h-8' : 'w-6 h-6'}`} />
          </motion.div>

          {/* Labels */}
          <div className="flex flex-col items-center text-center z-10">
            <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-1">
              {agentName || config.label}
            </span>
            <div className="flex flex-col items-center gap-1">
               {isActive ? (
                 <div className="flex flex-col items-center">
                    <span className="text-xs font-black text-indigo-600 uppercase tracking-tighter animate-pulse">
                       Thinking...
                    </span>
                    <div className="flex gap-1 mt-1">
                       {[0, 1, 2].map(i => (
                         <motion.div 
                           key={i}
                           animate={{ y: [0, -3, 0] }}
                           transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.1 }}
                           className="w-1 h-1 rounded-full bg-indigo-400"
                         />
                       ))}
                    </div>
                 </div>
               ) : isCompleted ? (
                 <div className="flex items-center gap-1.5 text-emerald-500">
                    <CheckCircle2 className="w-3 h-3" />
                    <span className="text-[10px] font-bold uppercase tracking-widest">Awaiting</span>
                 </div>
               ) : (
                 <div className="flex items-center gap-1.5 text-slate-300">
                    <Clock className="w-3 h-3" />
                    <span className="text-[10px] font-bold uppercase tracking-widest">Idle</span>
                 </div>
               )}
            </div>
          </div>

          {/* Action Overlay for Active State */}
          <AnimatePresence>
            {isActive && action && (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="absolute bottom-4 left-4 right-4 bg-slate-900/5 backdrop-blur-md rounded-2xl p-2 border border-slate-200/20"
              >
                <p className="text-[9px] font-bold text-slate-500 uppercase tracking-tighter truncate text-center">
                   {action}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Tooltip on Hover */}
          <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-white/40 flex items-center justify-center pointer-events-none">
             <div className="bg-slate-900 text-white text-[10px] font-black uppercase px-3 py-1.5 rounded-full shadow-2xl tracking-[0.1em]">
                {config.label} #ST-{step || 0}
             </div>
          </div>
        </div>
      </motion.div>

      {/* Connection Handles */}
      <Handle 
        type="target" 
        position={Position.Top} 
        className="!opacity-0" 
      />
      <Handle 
        type="source" 
        position={Position.Bottom} 
        className="!opacity-0" 
      />
    </div>
  );
});

AgentNode.displayName = "AgentNode";
