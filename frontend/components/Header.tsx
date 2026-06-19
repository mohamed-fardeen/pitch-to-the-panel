"use client";

import React from "react";
import { Provider } from "./ModelSelector";

interface HeaderProps {
  provider: Provider;
  setProvider: (provider: Provider) => void;
  disabled: boolean;
}

export function Header({ provider, setProvider, disabled }: HeaderProps) {
  return (
    <header className="flex justify-between items-center px-12 py-6 bg-white border-b border-slate-100/60 font-headline">
      <div className="flex items-center gap-12">
        <h2 className="text-2xl font-black text-[#006948] tracking-tight">Pitch to the Panel</h2>
        <ProviderTabs provider={provider} setProvider={setProvider} disabled={disabled} />
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

// Inline provider tabs styled to match the header aesthetic. Kept here
// because the default ModelSelector uses an Outline/M3 surface palette that
// clashes with the page-level design tokens used in Header.
const PROVIDER_TABS: { id: Provider; label: string }[] = [
  { id: "anthropic", label: "CLAUDE" },
  { id: "gemini", label: "GEMINI" },
  { id: "openai", label: "GPT" },
  { id: "groq", label: "GROQ" },
  { id: "ollama", label: "OLLAMA" },
];

function ProviderTabs({ provider, setProvider, disabled }: { provider: Provider; setProvider: (p: Provider) => void; disabled: boolean }) {
  return (
    <nav className="hidden md:flex gap-10">
      {PROVIDER_TABS.map((tab) => {
        const isActive = provider === tab.id;
        return (
          <button
            key={tab.id}
            disabled={disabled}
            onClick={() => setProvider(tab.id)}
            className={`transition-all duration-300 text-[11px] font-bold uppercase tracking-[0.2em] relative py-1 ${
              isActive
                ? "text-[#006948]"
                : "text-slate-300 hover:text-slate-500"
            } disabled:opacity-50`}
          >
            {tab.label}
            {isActive && (
              <div className="absolute -bottom-1 left-0 right-0 h-0.5 bg-[#006948] rounded-full duration-500" />
            )}
          </button>
        );
      })}
    </nav>
  );
}
