"use client";

import React, { useEffect, useRef } from "react";
import { ConversationTurn } from "../types/v2_types";

interface LiveFeedProps {
  logs: string[];
  conversation?: ConversationTurn[];
}

export function LiveFeed({ logs, conversation = [] }: LiveFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, conversation]);

  return (
    <div className="flex flex-col h-full bg-[#0a1224]/50 backdrop-blur-3xl rounded-3xl overflow-hidden border border-white/5 shadow-2xl">
      {/* Athena Title Bar */}
      <div className="px-6 py-4 flex items-center justify-between border-b border-white/[0.03] bg-white/[0.01]">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse shadow-[0_0_10px_rgba(24,200,151,0.5)]"></div>
          <h3 className="text-[10px] font-black font-label uppercase tracking-[0.25em] text-on-surface-variant flex items-center gap-2">
            Digital Athenaeum <span className="text-white/20 font-light">|</span> <span className="text-primary/60">Synthesis Engine</span>
          </h3>
        </div>
        <div className="flex gap-2">
           <span className="material-symbols-outlined text-xs text-on-surface-variant/40 hover:text-primary transition-colors cursor-pointer">download</span>
           <span className="material-symbols-outlined text-xs text-on-surface-variant/40 hover:text-primary transition-colors cursor-pointer">fullscreen</span>
        </div>
      </div>

      {/* Content Area */}
      <div 
        ref={scrollRef}
        className="flex-1 p-6 overflow-y-auto custom-scrollbar bg-gradient-to-b from-transparent to-[#060e20]/20"
      >
        <div className="space-y-6">
          {conversation.map((turn, idx) => {
            const isPitcher = turn.type.includes('pitcher') || turn.type === 'answer';
            const isObserver = turn.type === 'observer_utterance';
            const isAck = turn.type === 'interrupt_ack';
            
            return (
              <div 
                key={idx} 
                className={`animate-in fade-in slide-in-from-bottom-2 duration-500 ease-out group ${
                  isPitcher ? 'flex flex-col items-end' : 'flex flex-col items-start'
                }`}
              >
                <div className={`flex items-center gap-2 mb-2 px-1 ${isPitcher ? 'flex-row-reverse' : 'flex-row'}`}>
                  <span className={`text-[9px] font-black font-label uppercase tracking-widest ${
                    isPitcher ? 'text-primary' : 'text-on-surface-variant/70'
                  }`}>
                    {turn.agent_name || (isPitcher ? 'Alex Chen' : 'Panelist')}
                  </span>
                  
                  {!isPitcher && (
                    <span className={`text-[8px] px-2 py-0.5 rounded-full border ${
                      isObserver 
                        ? 'bg-blue-500/10 border-blue-500/20 text-blue-400' 
                        : isAck 
                          ? 'bg-purple-500/10 border-purple-500/20 text-purple-400'
                          : 'bg-primary/10 border-primary/20 text-primary/80'
                    } uppercase font-black tracking-tighter opacity-80`}>
                      {isObserver ? 'Observer' : isAck ? 'Acknowledgment' : 'Host'}
                    </span>
                  )}
                  
                  <span className="text-[8px] font-mono text-on-surface-variant/20 group-hover:opacity-100 opacity-0 transition-opacity">0{idx}:{(idx * 13) % 60}</span>
                </div>

                <div className={`max-w-[85%] p-4 rounded-2xl relative transition-all duration-300 ${
                  isPitcher 
                    ? 'bg-primary/10 border border-primary/20 rounded-tr-none text-white' 
                    : isObserver 
                      ? 'bg-blue-500/5 border border-blue-500/10 rounded-tl-none text-on-surface-variant/90'
                      : isAck
                        ? 'bg-purple-500/5 border border-purple-500/10 rounded-tl-none text-on-surface-variant/90'
                        : 'bg-white/[0.03] border border-white/[0.05] rounded-tl-none text-on-surface-variant/90'
                }`}>
                   <p className="text-xs leading-relaxed font-medium">
                    {turn.content}
                  </p>
                  
                  {/* Subtle glass effect highlight */}
                  <div className="absolute inset-x-0 top-0 h-[1px] bg-white/5 rounded-full"></div>
                </div>
              </div>
            );
          })}

          {conversation.length === 0 && logs.map((log, idx) => (
            <div key={idx} className="flex gap-4 items-start animate-in fade-in duration-700">
               <span className="text-[9px] font-mono text-primary/30 mt-1">[{idx.toString().padStart(3, '0')}]</span>
               <div className="text-[10px] font-mono text-on-surface-variant/40 leading-relaxed max-w-[90%]">
                 {log}
               </div>
            </div>
          ))}

          {logs.length === 0 && conversation.length === 0 && (
            <div className="flex flex-col items-center justify-center min-h-[300px] gap-6">
              <div className="relative">
                <div className="w-16 h-16 rounded-full border border-primary/20 animate-ping absolute inset-0"></div>
                <div className="w-16 h-16 rounded-full bg-primary/5 border border-primary/20 flex items-center justify-center relative z-10">
                   <span className="material-symbols-outlined text-primary/40 text-2xl">terminal</span>
                </div>
              </div>
              <div className="text-center space-y-1">
                <span className="text-[10px] font-black uppercase tracking-[0.4em] text-on-surface-variant/40 block">Awaiting Synthesis</span>
                <span className="text-[9px] font-mono text-on-surface-variant/20 block">Establishing SSE Context...</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Analytics Footer */}
      <div className="px-6 py-4 bg-white/[0.01] border-t border-white/[0.03] flex items-center justify-between">
        <div className="flex items-center gap-4">
           <div className="flex gap-1 items-center">
             <div className="w-1 h-3 bg-primary/40 rounded-full animate-[bounce_1s_infinite_0ms]"></div>
             <div className="w-1 h-5 bg-primary/60 rounded-full animate-[bounce_1s_infinite_200ms]"></div>
             <div className="w-1 h-2 bg-primary/30 rounded-full animate-[bounce_1s_infinite_400ms]"></div>
           </div>
           <span className="text-[9px] font-black uppercase tracking-widest text-on-surface-variant/30">Live Stream: Decrypted</span>
        </div>
        <div className="px-3 py-1 bg-primary/5 border border-primary/10 rounded-full">
           <span className="text-[8px] font-black text-primary uppercase tracking-widest">v1.2 // Secure</span>
        </div>
      </div>
    </div>
  );
}
