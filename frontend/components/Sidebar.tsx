"use client";

import React from "react";

interface SidebarProps {
  onNewPitch: () => void;
  onViewChange: (view: string) => void;
  currentView?: string;
}

export function Sidebar({ onNewPitch, onViewChange, currentView = "panel" }: SidebarProps) {
  const navItems = [
    { id: "panel", label: "Panel", icon: "group" },
    { id: "graph", label: "Agent Graph", icon: "hub" },
    { id: "transcripts", label: "Transcripts", icon: "chat" },
    { id: "library", label: "Library", icon: "book" },
    { id: "analytics", label: "Analytics", icon: "query_stats" },
  ];

  return (
    <aside className="h-full w-72 flex flex-col z-40 bg-slate-50/50 border-r border-slate-200/40 font-headline antialiased">
      <div className="p-8 flex items-center gap-3">
        <div className="w-10 h-10 bg-[#006948] rounded-xl flex items-center justify-center shadow-lg shadow-emerald-900/20">
          <span className="material-symbols-outlined text-white text-2xl">gavel</span>
        </div>
        <div>
          <h1 className="text-lg font-bold text-slate-900 leading-none">Digital Athenaeum</h1>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">v2.4.0-ALPHA</span>
        </div>
      </div>
      
      <nav className="flex flex-col gap-2 px-4 flex-1 mt-8">
        {navItems.map((item) => {
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`flex items-center gap-4 px-6 py-4 rounded-2xl transition-all duration-200 group ${
                isActive
                  ? "bg-emerald-50 text-[#006948] shadow-sm"
                  : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"
              }`}
            >
              <span 
                className={`material-symbols-outlined text-2xl ${isActive ? 'fill-1' : ''}`}
                style={{ fontVariationSettings: isActive ? "'FILL' 1" : "" }}
              >
                {item.icon}
              </span>
              <span className="text-sm font-bold tracking-tight">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="p-6 mt-auto space-y-6">
        <button 
          onClick={onNewPitch}
          className="w-full py-4 rounded-full bg-[#006948] text-white flex items-center justify-center gap-3 shadow-xl shadow-emerald-900/10 hover:scale-[1.02] active:scale-[0.98] transition-all"
        >
          <span className="material-symbols-outlined text-xl">add</span>
          <span className="text-sm font-bold">New Pitch</span>
        </button>
        
        <div className="flex flex-col gap-4 px-6 pb-4">
           <button className="flex items-center gap-4 text-slate-400 hover:text-slate-600 transition-colors">
              <span className="material-symbols-outlined text-2xl">help</span>
              <span className="text-sm font-bold">Support</span>
           </button>
           <button className="flex items-center gap-4 text-slate-400 hover:text-slate-600 transition-colors">
              <span className="material-symbols-outlined text-2xl">person</span>
              <span className="text-sm font-bold">Account</span>
           </button>
        </div>
      </div>
    </aside>
  );
}
