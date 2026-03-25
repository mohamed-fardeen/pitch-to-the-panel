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
    { id: "transcripts", label: "Transcripts", icon: "description" },
    { id: "library", label: "Library", icon: "auto_stories" },
    { id: "analytics", label: "Analytics", icon: "analytics" },
  ];

  return (
    <aside className="hidden lg:flex fixed left-0 top-0 h-screen w-64 flex-col bg-[#091328] shadow-[0_20px_40px_rgba(0,0,0,0.4)] z-50 py-6 px-4">
      <div className="mb-10 px-2">
        <h1 className="text-xl font-headline font-extrabold tracking-tight text-[#68ffca]">Pitch Panel</h1>
        <p className="text-[10px] text-on-surface-variant font-label font-black uppercase tracking-widest mt-1 opacity-60">Digital Athenaeum</p>
      </div>

      <nav className="flex-1 space-y-2">
        {navItems.map((item) => {
          const isActive = currentView === item.id;
          return (
            <div
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`flex items-center px-4 py-3 rounded-xl transition-all duration-300 cursor-pointer ${
                isActive
                  ? "text-[#68ffca] font-bold border-r-4 border-[#68ffca] bg-gradient-to-r from-[#68ffca]/10 to-transparent"
                  : "text-slate-400 hover:text-slate-200 hover:bg-[#141f38] scale-95 active:scale-90"
              }`}
            >
              <span className="material-symbols-outlined mr-3 text-[20px]">{item.icon}</span>
              <span className="font-label text-sm uppercase tracking-widest font-black leading-none">{item.label}</span>
            </div>
          );
        })}
      </nav>

      <div className="mt-auto px-2 pt-6">
        <button
          onClick={onNewPitch}
          className="w-full bg-gradient-to-r from-[#68ffca] to-[#18c897] text-[#003828] py-4 rounded-full font-black text-xs uppercase tracking-[0.2em] flex items-center justify-center gap-2 hover:opacity-90 transition-all shadow-lg active:scale-95 mb-6"
        >
          <span className="material-symbols-outlined text-sm">add</span>
          New Session
        </button>

        <div className="flex items-center gap-3 p-3 rounded-2xl bg-surface-container-low/50 border border-white/5 group hover:bg-surface-container-low transition-colors cursor-pointer">
          <div className="relative">
             <img 
               alt="User profile" 
               className="w-10 h-10 rounded-full object-cover border border-primary/20" 
               src="https://lh3.googleusercontent.com/aida-public/AB6AXuAp-b425gZkkqfSrKzMv0vav1xELUmamRoWNik1D31q72PTjCT0ug8sOCl2niJ5cLpHpibFKU_s6Qn3hshn-CwBZOe4uN5zltbLMD8dcWfwKCSl2yis157bjIwT1Bpi9F6L6y-ep0hWj1UjqeD2ZcLDvYys7fWoJOneqa6bKTccJLh76ZB8QO6uGURxmTp9vuAddGiDyA49EKzxdMqN8QkLi2dCgi4ZZ1u3OCV4Ft0PFHRjB9cfbdzm1hswhHDsm99ljFQxQXDYW40" 
             />
             <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-primary rounded-full border-2 border-[#091328]"></div>
          </div>
          <div className="overflow-hidden">
            <p className="text-xs font-black text-white truncate font-manrope">Alex Chen</p>
            <p className="text-[9px] text-on-surface-variant font-black uppercase tracking-wider truncate opacity-50">Premium Curator</p>
          </div>
          <span className="material-symbols-outlined ml-auto text-on-surface-variant group-hover:text-white transition-colors text-sm">more_vert</span>
        </div>
      </div>
    </aside>
  );
}
