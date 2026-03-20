"use client";

import React from "react";

export type Provider = "anthropic" | "gemini" | "openai" | "groq";

interface ModelSelectorProps {
  currentProvider: Provider;
  onChange: (provider: Provider) => void;
  disabled: boolean;
}

export function ModelSelector({ currentProvider, onChange, disabled }: ModelSelectorProps) {
  return (
    <div className="flex space-x-2 text-sm bg-gray-800 p-1 rounded-lg">
      <button
        disabled={disabled}
        onClick={() => onChange("anthropic")}
        className={`px-4 py-2 rounded-md transition-colors ${
          currentProvider === "anthropic" ? "bg-amber-600 text-white" : "text-gray-400 hover:text-white"
        } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        Claude 3.5
      </button>
      <button
        disabled={disabled}
        onClick={() => onChange("gemini")}
        className={`px-4 py-2 rounded-md transition-colors ${
          currentProvider === "gemini" ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white"
        } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        Gemini 1.5
      </button>
      <button
        disabled={disabled}
        onClick={() => onChange("openai")}
        className={`px-4 py-2 rounded-md transition-colors ${
          currentProvider === "openai" ? "bg-emerald-600 text-white" : "text-gray-400 hover:text-white"
        } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        GPT-4o
      </button>
      <button
        disabled={disabled}
        onClick={() => onChange("groq")}
        className={`px-4 py-2 rounded-md font-semibold transition-colors ${
          currentProvider === "groq" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"
        } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        Groq
      </button>
    </div>
  );
}
