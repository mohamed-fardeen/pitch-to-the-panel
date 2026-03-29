"use client";

import React from "react";
import { PanelState } from "../types/v2_types";
import { AgentCard } from "./AgentCard";

interface PanelGridProps {
  panelState: PanelState;
  onChallenge?: (agentId: string, claim: string) => void;
  factChecks?: Record<string, string>;
  challengingAgentId?: string | null;
  activeHosts?: { host_a: any, host_b: any } | null;
}

const ALL_AGENTS = {
  "vc": { id: "vc", name: "Arjun Mehta", role: "Skeptical VC", color: "bg-red-600" },
  "enthusiastic": { id: "enthusiastic", name: "Priya Sharma", role: "Product Manager", color: "bg-emerald-500" },
  "hostile": { id: "hostile", name: "Ravi Kumar", role: "Ops Manager", color: "bg-slate-700" },
  "expert": { id: "expert", name: "Dr. Ananya Iyer", role: "Industry Consultant", color: "bg-blue-600" },
  "competitor": { id: "competitor", name: "Meera Pillai", role: "Marketing Manager", color: "bg-amber-500" },
  "beginner": { id: "beginner", name: "Kiran", role: "Student", color: "bg-indigo-500" },
  "suresh": { id: "suresh", name: "Suresh Nair", role: "Shop Owner", color: "bg-orange-600" },
  "design_critic": { id: "design_critic", name: "Aisha Thomas", role: "Design Strategist", color: "bg-pink-600" },
  "dr_iyer_design": { id: "dr_iyer_design", name: "Dr. Ananya Iyer (Design)", role: "Technical Design Critic", color: "bg-blue-700" },
  "meera_design": { id: "meera_design", name: "Meera Pillai (Design)", role: "Design Client", color: "bg-amber-600" },
  "interviewer": { id: "interviewer", name: "Claude", role: "Lead Interviewer", color: "bg-primary" },
};

export function PanelGrid({ panelState, onChallenge, factChecks, challengingAgentId, activeHosts }: PanelGridProps) {
  // If panelState is empty, we show a default selection (standard panel)
  const activeKeys = Object.keys(panelState).length > 0 
    ? Object.keys(panelState).filter(k => k !== 'pitcher') 
    : ["interviewer", "vc", "enthusiastic", "hostile", "expert", "competitor", "beginner"];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 p-2 overflow-y-auto custom-scrollbar h-full max-h-[calc(100vh-250px)]">
      {activeKeys.map((key) => {
        const state = panelState[key] || { text: "", status: "idle", name: key, role: "Panelist" };
        const agent = ALL_AGENTS[key as keyof typeof ALL_AGENTS] || { id: key, name: state.name || key, role: state.role || "Panelist" };
        const isChallenged = challengingAgentId === key;
        const isHost = key === 'interviewer'; // Interviewer is always 'host'
        
        return (
          <AgentCard 
            key={key}
            id={key}
            name={state.name || agent.name}
            role={state.role || agent.role}
            status={state.status}
            text={state.text}
            isHost={!!isHost}
            isChallenged={!!isChallenged}
          />
        );
      })}
    </div>
  );
}
