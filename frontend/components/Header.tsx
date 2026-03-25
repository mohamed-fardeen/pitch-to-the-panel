"use client";

import React from "react";
import { ModelSelector, Provider } from "./ModelSelector";

interface HeaderProps {
  provider: Provider;
  setProvider: (provider: Provider) => void;
  disabled: boolean;
}

export function Header({ provider, setProvider, disabled }: HeaderProps) {
  return (
    <header className="flex justify-between items-center w-full px-8 h-20 sticky top-0 bg-[#060e20]/60 backdrop-blur-xl z-40 border-b border-white/5">
      <div className="flex items-center gap-12">
        <span className="text-2xl font-manrope font-black bg-clip-text text-transparent bg-gradient-to-r from-[#68ffca] to-[#18c897] uppercase tracking-tighter">
          Pitch to the Panel
        </span>
        <nav className="hidden lg:flex items-center gap-8">
          {[
            { label: "Claude", id: "anthropic" },
            { label: "Gemini", id: "gemini" },
            { label: "GPT-4", id: "openai" },
            { label: "Groq", id: "groq" }
          ].map(link => (
            <button 
              key={link.id} 
              disabled={disabled}
              onClick={() => setProvider(link.id as Provider)}
              className={`font-black text-[10px] uppercase tracking-[0.2em] transition-all cursor-pointer ${
                provider === link.id ? 'text-primary' : 'text-on-surface-variant hover:text-white'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {link.label}
            </button>
          ))}
        </nav>
      </div>
      
      <div className="flex items-center gap-8">
        <div className="relative flex items-center bg-surface-container-low/50 px-5 py-2 rounded-full ring-1 ring-white/5 group focus-within:ring-primary/30 transition-all">
          <span className="material-symbols-outlined text-on-surface-variant text-sm mr-3 opacity-40 group-focus-within:text-primary transition-colors">search</span>
          <input className="bg-transparent border-none text-[10px] font-bold uppercase tracking-widest focus:ring-0 placeholder:text-on-surface-variant/20 w-48 text-white" placeholder="Global search..." type="text"/>
        </div>
        
        <div className="flex items-center gap-5 text-on-surface-variant">
          <span className="material-symbols-outlined cursor-pointer hover:text-primary transition-colors text-xl">notifications</span>
          <span className="material-symbols-outlined cursor-pointer hover:text-primary transition-colors text-xl">settings</span>
        </div>
      </div>
    </header>
  );
}
