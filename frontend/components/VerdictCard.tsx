"use client";

import React from "react";

interface VerdictCardProps {
  verdict: string;
  sessionId: string;
  onClose: () => void;
}

export function VerdictCard({ verdict, sessionId, onClose }: VerdictCardProps) {
  const parts = verdict.split(/Your biggest weakness:|Before your next pitch:/i);
  
  const strongest = parts[0]?.replace(/Your strongest point:/i, "").trim() || "";
  const weakness = parts[1]?.trim() || "";
  const toFix = parts[2]?.trim() || "";

  const handleDownload = () => {
    window.open(`http://localhost:8000/api/session/${sessionId}/report`, "_blank");
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50 animate-in fade-in duration-300" onClick={onClose}>
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 border border-gray-700 max-w-2xl w-full rounded-2xl shadow-2xl p-8 transform transition-all translate-y-0 relative" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute top-4 right-4 text-gray-400 hover:text-white flex items-center justify-center w-8 h-8 rounded-full bg-gray-800 hover:bg-gray-700 transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
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
        
        <div className="mt-8 flex justify-center gap-4 text-sm">
          <button onClick={handleDownload} className="bg-cyan-600 hover:bg-cyan-500 text-white px-6 py-2 rounded-full font-bold shadow-md transition-colors flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            Download Report PDF
          </button>
        </div>
        <div className="mt-4 text-center text-xs text-gray-500">
          Take a screenshot to save your verdict. Refresh to pitch again.
        </div>
      </div>
    </div>
  );
}
