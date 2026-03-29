"use client";

import React from "react";
import { Provider } from "./ModelSelector";

interface HeaderProps {
  provider: Provider;
  setProvider: (provider: Provider) => void;
  disabled: boolean;
}

export function Header({ provider, setProvider, disabled }: HeaderProps) {
  const models = [
    { label: "CLAUDE", id: "anthropic" },
    { label: "GEMINI", id: "gemini" },
    { label: "GPT", id: "openai" },
    { label: "GROQ", id: "groq" }
  ];

  return (
    <header className="flex justify-between items-center px-12 py-6 bg-white border-b border-slate-100/60 font-headline">
      <div className="flex items-center gap-12">
        <h2 className="text-2xl font-black text-[#006948] tracking-tight">Pitch to the Panel</h2>
        
        <nav className="hidden md:flex gap-10">
          {models.map((model) => {
            const isActive = provider === model.id;
            return (
              <button
                key={model.id}
                disabled={disabled}
                onClick={() => setProvider(model.id as Provider)}
                className={`transition-all duration-300 text-[11px] font-bold uppercase tracking-[0.2em] relative py-1 ${
                  isActive
                    ? "text-[#006948]"
                    : "text-slate-300 hover:text-slate-500"
                } disabled:opacity-50`}
              >
                {model.label}
                {isActive && (
                  <div className="absolute -bottom-1 left-0 right-0 h-0.5 bg-[#006948] rounded-full duration-500" />
                )}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="flex items-center gap-8">
        <div className="flex items-center gap-6 text-slate-300">
           <button className="hover:text-[#006948] transition-colors">
             <span className="material-symbols-outlined text-2xl">history</span>
           </button>
           <button className="hover:text-[#006948] transition-colors">
             <span className="material-symbols-outlined text-2xl">settings</span>
           </button>
        </div>
        <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center cursor-pointer border border-slate-200/40 hover:border-[#006948]/20 transition-all">
           <span className="material-symbols-outlined text-slate-400">person</span>
        </div>
      </div>
    </header>
  );
}
