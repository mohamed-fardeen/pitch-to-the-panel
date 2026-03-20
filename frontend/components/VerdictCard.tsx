"use client";

import React from "react";

interface VerdictCardProps {
  verdict: string;
}

export function VerdictCard({ verdict }: VerdictCardProps) {
  const parts = verdict.split(/Your biggest weakness:|Before your next pitch:/i);
  
  const strongest = parts[0]?.replace(/Your strongest point:/i, "").trim() || "";
  const weakness = parts[1]?.trim() || "";
  const toFix = parts[2]?.trim() || "";

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50 animate-in fade-in duration-300">
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 border border-gray-700 max-w-2xl w-full rounded-2xl shadow-2xl p-8 transform transition-all translate-y-0 relative">
        <h2 className="text-3xl font-extrabold mb-6 text-center bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-cyan-400">
          Panel Verdict
        </h2>
        
        <div className="space-y-6">
          <div className="bg-emerald-500/10 border border-emerald-500/20 p-5 rounded-xl text-emerald-50">
            <h3 className="text-emerald-400 font-bold mb-2 uppercase tracking-wide text-xs">Your Strongest Point</h3>
            <p className="text-sm leading-relaxed">{strongest || verdict}</p>
          </div>
          
          {weakness && (
            <div className="bg-red-500/10 border border-red-500/20 p-5 rounded-xl text-red-50">
              <h3 className="text-red-400 font-bold mb-2 uppercase tracking-wide text-xs">Your Biggest Weakness</h3>
              <p className="text-sm leading-relaxed">{weakness}</p>
            </div>
          )}
          
          {toFix && (
            <div className="bg-blue-500/10 border border-blue-500/20 p-5 rounded-xl text-blue-50">
              <h3 className="text-blue-400 font-bold mb-2 uppercase tracking-wide text-xs">One Thing to Fix</h3>
              <p className="text-sm leading-relaxed">{toFix}</p>
            </div>
          )}
        </div>
        
        <div className="mt-8 text-center text-xs text-gray-500">
          Take a screenshot to save your verdict. Refresh to pitch again.
        </div>
      </div>
    </div>
  );
}
