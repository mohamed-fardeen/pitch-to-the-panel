"use client";

import React from "react";
import { AgentRole, AgentStatus } from "../types/v2_types";

interface AgentCardProps {
  id: string;
  name: string;
  role: string | AgentRole;
  status: AgentStatus;
  text?: string;
  avatarUrl?: string;
  isChallenged?: boolean;
}

export function AgentCard({ id, name, role, status, text, avatarUrl, isChallenged }: AgentCardProps) {
  const isSpeaking = status === "speaking";

  return (
    <div 
      className={`relative flex flex-col items-center p-10 rounded-[2.5rem] transition-all duration-700 border ${
        isSpeaking 
          ? "bg-emerald-50/40 border-emerald-200 shadow-[0_20px_50px_rgba(0,105,72,0.1)] scale-[1.02]" 
          : isChallenged
          ? "bg-rose-50/40 border-rose-200 shadow-[0_20px_50px_rgba(225,29,72,0.1)]"
          : "bg-white border-slate-100 shadow-sm hover:shadow-lg hover:border-slate-200"
      }`}
    >
       {/* Speaking/Challenged/Thinking Badge */}
      <div className="absolute top-8 left-0 right-0 flex justify-center px-6 pointer-events-none">
         {isSpeaking ? (
            <div className="flex items-center gap-1.5 px-4 py-1.5 bg-emerald-500 rounded-full shadow-lg shadow-emerald-500/20 duration-300">
               <div className="w-1.5 h-1.5 bg-white rounded-full animate-pulse"></div>
               <span className="text-[10px] font-black text-white uppercase tracking-[0.2em]">Speaking</span>
            </div>
         ) : isChallenged ? (
            <div className="flex items-center gap-1.5 px-4 py-1.5 bg-rose-500 rounded-full shadow-lg shadow-rose-500/20 duration-300">
               <div className="w-1.5 h-1.5 bg-white rounded-full"></div>
               <span className="text-[10px] font-black text-white uppercase tracking-[0.2em]">Challenged</span>
            </div>
         ) : status === "thinking" ? (
            <div className="flex items-center gap-1.5 px-4 py-1.5 bg-slate-800 rounded-full shadow-lg shadow-slate-900/20 duration-300">
               <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-ping"></div>
               <span className="text-[10px] font-black text-white uppercase tracking-[0.2em]">Thinking...</span>
            </div>
         ) : null}
      </div>

      <div className="relative mt-8 mb-6">
        <div className={`w-32 h-32 rounded-3xl overflow-hidden border-2 ${isSpeaking ? 'border-emerald-500' : 'border-slate-100'} shadow-2xl shadow-slate-200/40`}>
          {avatarUrl ? (
            <img src={avatarUrl} alt={name} className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full bg-slate-50 flex items-center justify-center">
              <span className="material-symbols-outlined text-4xl text-slate-200">person</span>
            </div>
          )}
        </div>
        {isSpeaking && (
          <div className="absolute -bottom-2 -right-2 w-10 h-10 bg-emerald-500 rounded-full border-4 border-white flex items-center justify-center shadow-xl">
             <span className="material-symbols-outlined text-white text-xs" style={{ fontVariationSettings: "'FILL' 1" }}>mic</span>
          </div>
        )}
      </div>

      <div className="text-center space-y-2 mb-8">
        <h3 className="text-2xl font-black text-slate-800 tracking-tight leading-none">{name}</h3>
        <p className={`text-[11px] font-extrabold uppercase tracking-[0.2em] px-3 py-1 rounded-full border border-current opacity-40 mx-auto w-fit ${isSpeaking ? 'text-emerald-600' : 'text-slate-400'}`}>
          {typeof role === 'string' ? role : role}
        </p>
      </div>

      <div className="w-full min-h-[80px] flex items-center justify-center">
         <p className="text-[15px] text-slate-500 font-medium leading-relaxed italic text-center opacity-90 line-clamp-3">
           {text ? `"${text}"` : "Waiting for the right moment to interject..."}
         </p>
      </div>
    </div>
  );
}
