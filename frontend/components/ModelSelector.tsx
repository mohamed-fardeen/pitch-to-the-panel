"use client";

import React from "react";

export type Provider = "anthropic" | "gemini" | "openai" | "groq" | "ollama";

interface ModelSelectorProps {
  currentProvider: Provider;
  onChange: (provider: Provider) => void;
  disabled: boolean;
}

export function ModelSelector({ currentProvider, onChange, disabled }: ModelSelectorProps) {
  const providers: { id: Provider; label: string }[] = [
    { id: "anthropic", label: "Claude" },
    { id: "gemini", label: "Gemini" },
    { id: "openai", label: "GPT" },
    { id: "groq", label: "Groq" },
    { id: "ollama", label: "Ollama" },
  ];

  return (
    <nav className="hidden md:flex items-center bg-surface-container-low rounded-full px-1 py-1 gap-1 border border-outline-variant/10">
      {providers.map((p) => {
        const isActive = currentProvider === p.id;
        return (
          <button
            key={p.id}
            disabled={disabled}
            onClick={() => onChange(p.id)}
            className={`px-4 pb-1 text-[10px] font-label uppercase tracking-widest transition-all duration-200 border-b-2 font-black ${
              isActive
                ? "text-primary border-primary"
                : "text-outline hover:text-white border-transparent"
            } ${disabled ? "opacity-30 cursor-not-allowed" : "cursor-pointer"}`}
          >
            {p.label}
          </button>
        );
      })}
    </nav>
  );
}
