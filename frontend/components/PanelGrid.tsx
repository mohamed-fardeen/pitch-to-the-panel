"use client";

import React from "react";

export type PanelState = {
  [agent: string]: {
    text: string;
    status: "idle" | "streaming" | "done" | "error";
  };
};

interface PanelGridProps {
  panelState: PanelState;
  onChallenge?: (agentId: string, claim: string) => void;
  factChecks?: Record<string, string>;
}

const ALL_AGENTS = {
  vc: { id: "vc", name: "Arjun Mehta", role: "Skeptical VC", color: "bg-red-600" },
  enthusiastic: { id: "enthusiastic", name: "Priya Sharma", role: "Enthusiastic User", color: "bg-emerald-500" },
  hostile: { id: "hostile", name: "Ravi Kumar", role: "Hostile User", color: "bg-amber-500" },
  expert: { id: "expert", name: "Dr. Ananya Iyer", role: "Domain Expert", color: "bg-purple-600" },
  competitor: { id: "competitor", name: "Meera Pillai", role: "Competitor's Customer", color: "bg-orange-600" },
  beginner: { id: "beginner", name: "Kiran", role: "Confused First-Timer", color: "bg-blue-500" },
  suresh: { id: "suresh", name: "Suresh Nair", role: "Operator / Store Owner", color: "bg-lime-600" },
  design_critic: { id: "design_critic", name: "Aisha Thomas", role: "Design Critic", color: "bg-pink-500" }
};

export function PanelGrid({ panelState, onChallenge, factChecks }: PanelGridProps) {
  const activeKeys = Object.keys(panelState).length > 0 
    ? Object.keys(panelState) 
    : ["vc", "enthusiastic", "hostile", "expert", "competitor", "beginner"];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 p-4">
      {activeKeys.map((key) => {
        const agent = ALL_AGENTS[key as keyof typeof ALL_AGENTS] || { id: key, name: key, role: "Panelist", color: "bg-gray-500" };
        const state = panelState[key] || { text: "", status: "idle" };
        
        return (
           <div key={key} className="bg-gray-900 border border-gray-700/50 rounded-2xl overflow-hidden shadow-2xl flex flex-col transition-all duration-300 hover:border-gray-600/50">
              <div className="flex items-center space-x-3 p-4 bg-gradient-to-r from-gray-800 to-gray-800/50 border-b border-gray-700/50">
                <div className={`w-12 h-12 rounded-full flex items-center justify-center text-xl font-bold ${agent.color} text-white shadow-lg`}>
                  {agent.name.charAt(0)}
                </div>
                <div>
                  <h3 className="font-semibold text-gray-100">{agent.name}</h3>
                  <p className="text-xs text-gray-400">{agent.role}</p>
                </div>
                <div className="ml-auto">
                   {state.status === "streaming" && (
                     <div className="w-3 h-3 bg-blue-400 rounded-full animate-ping"></div>
                   )}
                   {state.status === "idle" && (
                     <div className="w-2 h-2 bg-gray-600 rounded-full"></div>
                   )}
                   {state.status === "done" && (
                     <div className="w-2 h-2 bg-green-400 rounded-full shadow-[0_0_8px_rgba(7ade80,0.6)]"></div>
                   )}
                </div>
              </div>
              <div className="p-5 flex-grow text-sm text-gray-300 min-h-[160px] max-h-[240px] overflow-y-auto whitespace-pre-wrap leading-relaxed">
                  {state.text || "Waiting for pitch..."}
                  {state.status === "streaming" && (
                    <span className="inline-block w-1.5 h-4 ml-1 bg-white animate-pulse align-middle rounded-sm"></span>
                  )}
                  {factChecks && factChecks[key] && (
                    <div className="mt-4 p-3 bg-indigo-900/40 border border-indigo-700/50 rounded-xl text-indigo-200 text-xs italic animate-in fade-in slide-in-from-top-2">
                       <span className="font-bold not-italic block mb-1 uppercase text-[10px] text-indigo-400">Fact-Check:</span>
                       {factChecks[key]}
                    </div>
                  )}
              </div>
              
              {state.status === "done" && onChallenge && (
                  <div className="px-5 pb-4 mt-auto">
                     <button 
                       onClick={() => onChallenge(key, state.text)}
                       className="w-full py-2 bg-gray-800/50 hover:bg-rose-900/40 text-gray-400 hover:text-rose-400 border border-gray-700 hover:border-rose-800/50 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all"
                     >
                       Challenge Claim
                     </button>
                  </div>
              )}
           </div>
        );
      })}
    </div>
  );
}
