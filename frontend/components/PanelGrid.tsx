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
  vc: { id: "vc", name: "Arjun Mehta", role: "Skeptical VC", color: "bg-red-600" },
  enthusiastic: { id: "enthusiastic", name: "Priya Sharma", role: "Enthusiastic User", color: "bg-emerald-500" },
  hostile: { id: "hostile", name: "Ravi Kumar", role: "Hostile User", color: "bg-amber-500" },
  expert: { id: "expert", name: "Dr. Ananya Iyer", role: "Domain Expert", color: "bg-purple-600" },
  competitor: { id: "competitor", name: "Meera Pillai", role: "Competitor's Customer", color: "bg-orange-600" },
  beginner: { id: "beginner", name: "Kiran", role: "Confused First-Timer", color: "bg-blue-500" },
  suresh: { id: "suresh", name: "Suresh Nair", role: "Operator / Store Owner", color: "bg-lime-600" },
  design_critic: { id: "design_critic", name: "Aisha Thomas", role: "Design Critic", color: "bg-pink-500" }
};

export function PanelGrid({ panelState, onChallenge, factChecks, challengingAgentId, activeHosts }: PanelGridProps) {
  const activeKeys = Object.keys(panelState).length > 0 
    ? Object.keys(panelState).filter(k => k !== 'pitcher') // Hide pitcher from grid
    : ["vc", "enthusiastic", "hostile", "expert", "competitor", "beginner"];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8 p-2 pb-20">
      {activeKeys.map((key) => {
        const state = panelState[key] || { text: "", status: "idle", name: key, role: "Panelist" };
        const agent = ALL_AGENTS[key as keyof typeof ALL_AGENTS] || { id: key, name: state.name || key, role: state.role || "Panelist" };
        const isChallenged = challengingAgentId === key;
        const isHost = activeHosts && (activeHosts.host_a?.agent_id === key || activeHosts.host_b?.agent_id === key);
        
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
