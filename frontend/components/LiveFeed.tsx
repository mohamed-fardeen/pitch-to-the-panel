"use client";

import React, { useEffect, useRef } from "react";
import { ConversationTurn, AgentRole } from "../types/v2_types";

interface LiveFeedProps {
  turns: ConversationTurn[];
  agents: any[];
  onJumpIn?: () => void;
  isRecording?: boolean;
}

export function LiveFeed({ turns, agents, onJumpIn, isRecording }: LiveFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const getAgentData = (name: string) => {
    return agents.find(a => a.name === name || a.agent_id === name);
  };

  // Find the currently speaking agent to show their streaming text
  const activeAgent = agents.find(a => a.status === "speaking" && a.text);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns, activeAgent?.text]);

  return (
    <div className="flex flex-col h-full bg-white/80 backdrop-blur-sm rounded-[3rem] border border-slate-100 shadow-xl overflow-hidden relative font-headline">
      {/* Glossy Header Area */}
      <div className="p-8 border-b border-slate-100/60 bg-white/40 backdrop-blur-md flex justify-between items-center z-10">
        <div className="flex items-center gap-3">
           <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
           <h2 className="text-xl font-bold text-slate-800 tracking-tight">Live Transcript</h2>
        </div>
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest bg-slate-50 border border-slate-100/50 px-4 py-2 rounded-full">Real-Time Synthesis</span>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-10 space-y-8 custom-scrollbar scroll-smooth pb-32">
        {turns.length === 0 && !activeAgent ? (
          <div className="h-full flex flex-col items-center justify-center space-y-8 opacity-60 text-center">
            <div className="w-24 h-24 bg-emerald-50 rounded-full flex items-center justify-center border border-emerald-100/50">
               <span className="material-symbols-outlined text-4xl text-emerald-300">history_edu</span>
            </div>
            <div className="space-y-3">
              <h3 className="text-xl font-bold text-slate-400 uppercase tracking-widest px-2">Session Active</h3>
              <p className="text-sm font-medium text-slate-300 max-w-[240px] mx-auto leading-relaxed">The panel is ready. Start your pitch to begin the synthesis.</p>
            </div>
          </div>
        ) : (
          <>
            {turns.map((turn, i) => {
              const agent = getAgentData(turn.agent_name || "");
              const isPitcher = turn.agent_name === "Pitcher" || turn.agent_name === "Alex Chen";
              
              return (
                <div key={i} className={`flex flex-col gap-2 transition-all duration-700`}>
                  <div className="flex items-center gap-3 ml-1">
                    <div className={`w-2 h-2 rounded-full ${isPitcher ? 'bg-emerald-500' : 'bg-slate-300'}`} style={{ backgroundColor: agent?.color }}></div>
                    <span className={`text-[10px] font-bold uppercase tracking-[0.2em] ${isPitcher ? 'text-emerald-600' : 'text-slate-400'}`}>
                      {turn.agent_name || "Specialist"}
                    </span>
                  </div>
                  
                  <div 
                    className={`p-8 rounded-[2rem] border-l-4 shadow-sm transition-all ${
                      isPitcher 
                        ? "bg-slate-50/50 border-emerald-500/20 text-slate-500 italic font-medium" 
                        : "bg-slate-50 border-slate-200/50 text-slate-700"
                    }`}
                    style={!isPitcher ? { borderLeftColor: agent?.color || '#e2e8f0' } : {}}
                  >
                    <p className="text-base leading-relaxed opacity-90">
                      {turn.content}
                    </p>
                  </div>
                </div>
              );
            })}

            {/* Active Streaming Bubble */}
            {activeAgent && (
              <div className="flex flex-col gap-2 transition-all duration-300">
                <div className="flex items-center gap-3 ml-1">
                  <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" style={{ backgroundColor: activeAgent.color }}></div>
                  <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-600">
                    {activeAgent.name} <span className="opacity-50 lowercase font-medium italic">(streaming)</span>
                  </span>
                </div>
                <div 
                  className="p-8 rounded-[2rem] border-l-4 shadow-sm transition-all bg-emerald-50/30 border-emerald-200 text-slate-800"
                  style={{ borderLeftColor: activeAgent.color || '#10b981' }}
                >
                  <p className="text-base leading-relaxed">
                    {activeAgent.text}
                    <span className="inline-block w-1 h-4 bg-emerald-500 ml-1 animate-pulse align-middle" />
                  </p>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Floating Action Container */}
      <div className="absolute bottom-8 left-0 right-0 px-10 pointer-events-none flex justify-center z-20">
         {onJumpIn && (
            <button 
               onClick={onJumpIn}
               className={`pointer-events-auto flex items-center gap-4 py-5 px-10 rounded-full bg-[#006948] hover:bg-[#005a3e] text-white font-bold uppercase tracking-widest shadow-2xl shadow-emerald-950/20 hover:scale-[1.05] active:scale-[0.95] transition-all ring-4 ring-emerald-500/10 ${isRecording ? 'bg-rose-500 hover:bg-rose-600 ring-rose-500/20' : ''}`}
            >
               <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                 {isRecording ? 'stop_circle' : 'pan_tool'}
               </span>
               <span className="text-sm">{isRecording ? 'Stop Recording' : 'JUMP IN'}</span>
            </button>
         )}
      </div>

      {/* Typing Indicator */}
      {turns.length > 0 && turns[turns.length - 1].agent_name !== "Pitcher" && !activeAgent && (
         <div className="absolute bottom-4 left-10 flex items-center gap-2 py-4 opacity-40">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse" />
            <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse delay-75" />
            <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse delay-150" />
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest ml-1">{turns[turns.length-1].agent_name || "Agent"} is typing</span>
         </div>
      )}
    </div>
  );
}
