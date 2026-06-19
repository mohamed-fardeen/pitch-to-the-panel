"use client";

import React from "react";
import { AgentRole, AgentStatus, PanelState } from "../types/v2_types";
import { AgentCard } from "./AgentCard";

interface PanelGridProps {
  panelState: PanelState;
}

const ALL_AGENTS: Record<string, { id: string; name: string; role: AgentRole; color: string }> = {
  "vc": { id: "vc", name: "Arjun Mehta", role: "vc", color: "bg-red-600" },
  "enthusiastic": { id: "enthusiastic", name: "Priya Sharma", role: "enthusiastic", color: "bg-emerald-500" },
  "hostile": { id: "hostile", name: "Ravi Kumar", role: "hostile", color: "bg-slate-700" },
  "expert": { id: "expert", name: "Dr. Ananya Iyer", role: "expert", color: "bg-blue-600" },
  "competitor": { id: "competitor", name: "Meera Pillai", role: "competitor", color: "bg-amber-500" },
  "beginner": { id: "beginner", name: "Kiran", role: "beginner", color: "bg-indigo-500" },
  "suresh": { id: "suresh", name: "Suresh Nair", role: "hostile", color: "bg-orange-600" },
  "design_critic": { id: "design_critic", name: "Aisha Thomas", role: "enthusiastic", color: "bg-pink-600" },
  "dr_iyer_design": { id: "dr_iyer_design", name: "Dr. Ananya Iyer (Design)", role: "expert", color: "bg-blue-700" },
  "meera_design": { id: "meera_design", name: "Meera Pillai (Design)", role: "competitor", color: "bg-amber-600" },
  "interviewer": { id: "interviewer", name: "Claude", role: "interviewer", color: "bg-primary" },
};

const FALLBACK_KEYS = ["interviewer", "vc", "enthusiastic", "hostile", "expert", "competitor", "beginner"];

export function PanelGrid({ panelState }: PanelGridProps) {
  const activeKeys = Object.keys(panelState).length > 0
    ? Object.keys(panelState).filter(k => k !== "pitcher")
    : FALLBACK_KEYS;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 p-2 overflow-y-auto custom-scrollbar h-full max-h-[calc(100vh-250px)]">
      {activeKeys.map((key) => {
        const state = panelState[key];
        const agent = ALL_AGENTS[key];
        const name = state?.name || agent?.name || key;
        const role: AgentRole = (state?.role as AgentRole) || agent?.role || "vc";
        const status: AgentStatus = state?.status || "idle";
        const text = state?.text || "";
        const avatarUrl = state?.avatarUrl || agent?.color;

        return (
          <AgentCard
            key={key}
            id={key}
            name={name}
            role={role}
            status={status}
            text={text}
            avatarUrl={avatarUrl}
            isChallenged={false}
          />
        );
      })}
    </div>
  );
}
