"use client";

import React from "react";
import { AgentRole, AgentStatus } from "../types/v2_types";

interface AgentCardProps {
  id: string;
  name: string;
  role: string | AgentRole;
  status: AgentStatus;
  text: string;
  avatarUrl?: string;
  isHost?: boolean;
  isChallenged?: boolean;
}

export function AgentCard({
  id,
  name,
  role,
  status,
  text,
  avatarUrl,
  isHost,
  isChallenged
}: AgentCardProps) {
  const isSpeaking = status === "speaking";

  return (
    <div 
      id={`agent-${id}`}
      className={`relative glass-card ghost-border rounded-3xl overflow-hidden transition-all duration-700 flex flex-col h-full min-h-[300px] border-white/5 group ${
        isSpeaking ? "ring-2 ring-primary/30 shadow-[0_40px_80px_-20px_rgba(24,200,151,0.3)] scale-[1.02] z-20" : "shadow-2xl opacity-80"
      } ${
        isChallenged ? "border-rose-500/50 ring-2 ring-rose-500/10" : ""
      } bg-gradient-to-br from-white/[0.02] to-transparent`}
    >
      {/* Background Decor */}
      {isSpeaking && (
        <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 blur-[60px] -mr-16 -mt-16 animate-pulse"></div>
      )}

      {/* Header Area */}
      <div className={`p-6 border-b border-white/5 flex items-center gap-5 transition-all ${
        isSpeaking ? "bg-primary/5 border-primary/10" : "bg-surface-container-low/20"
      }`}>
        {/* Avatar Sidebar */}
        <div className="relative">
          <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ring-1 transition-all duration-500 ${
            isSpeaking 
              ? 'bg-primary border-primary/40 text-[#003828] shadow-[0_0_20px_rgba(104,255,202,0.4)] rotate-3' 
              : 'bg-surface-container-highest border-white/10 text-on-surface-variant'
          }`}>
             <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: isSpeaking ? "'FILL' 1" : "'FILL' 0" }}>
               {isHost ? 'bolt' : id.includes('gemini') ? 'query_stats' : id.includes('gpt') ? 'neurology' : 'smart_toy'}
             </span>
          </div>
          {isSpeaking && (
            <div className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-[#060e20] flex items-center justify-center border border-white/10 shadow-xl overflow-hidden">
               <div className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse"></div>
            </div>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <h4 className="font-manrope font-black text-white truncate text-base uppercase tracking-tight">{name}</h4>
            {isHost && (
              <span className="text-[8px] font-black font-label uppercase tracking-widest bg-primary/10 text-primary border border-primary/20 px-2 py-1 rounded-full leading-none shadow-lg">
                Host
              </span>
            )}
          </div>
          <p className="text-[10px] font-black font-label uppercase tracking-widest text-[#68ffca] opacity-40">
            {role.replace("_", " ")}
          </p>
        </div>
      </div>

      {/* Text/Content Area */}
      <div className="flex-1 p-8 overflow-y-auto custom-scrollbar relative">
        <div className={`text-base leading-[1.8] transition-all duration-500 ${
          isSpeaking ? "text-white font-medium" : "text-on-surface-variant/80 font-normal italic italic"
        }`}>
          {text ? (
             text.split('\n\n').map((p, i) => <p key={i} className={i > 0 ? "mt-4" : ""}>{p}</p>)
          ) : (
            <span className="opacity-20 uppercase tracking-[0.2em] text-[10px] font-black">Waiting for turn...</span>
          )}
          {isSpeaking && (
            <span className="inline-block w-1.5 h-1.5 ml-2 bg-primary rounded-full animate-bounce align-middle shadow-[0_0_5px_#68ffca]"></span>
          )}
        </div>
      </div>

      {/* Footer Branding */}
      <div className="px-6 py-4 border-t border-white/5 flex justify-between items-center opacity-20 text-[8px] font-black uppercase tracking-[0.3em]">
        <div className="flex items-center gap-2">
           <span className="w-1 h-1 bg-primary rounded-full"></span>
           <span>Unit-0{id.charCodeAt(0) % 9}</span>
        </div>
        <span>Athenaeum Safe</span>
      </div>
    </div>
  );
}
