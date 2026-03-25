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
    <div className="fixed inset-0 bg-surface/80 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-in fade-in duration-500" onClick={onClose}>
      <div 
        className="glass-card ghost-border max-w-2xl w-full rounded-3xl shadow-[0_32px_64px_-12px_rgba(0,0,0,0.5)] p-0 overflow-hidden transform transition-all translate-y-0" 
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Section */}
        <div className="p-8 pb-4 text-center relative border-b border-outline-variant/10">
          <button onClick={onClose} className="absolute top-6 right-6 text-on-surface-variant/40 hover:text-white transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
          
          <div className="inline-flex items-center gap-2 mb-4 bg-primary/10 px-4 py-1.5 rounded-full border border-primary/20">
             <span className="material-symbols-outlined text-[16px] text-primary">verified</span>
             <span className="text-[10px] font-black font-label uppercase tracking-[0.2em] text-primary">System Evaluation Complete</span>
          </div>
          
          <h2 className="text-4xl font-manrope font-black text-white uppercase tracking-tighter mb-2">
            Panel <span className="text-primary">Verdict</span>
          </h2>
          <p className="text-on-surface-variant/60 text-xs font-label uppercase tracking-widest">Protocol ID: {sessionId.slice(0, 8)}</p>
        </div>
        
        {/* Content Section */}
        <div className="p-8 space-y-6">
          {/* Strongest Point */}
          <div className="group transition-all duration-300">
            <h3 className="text-[10px] font-black font-label uppercase tracking-[0.2em] text-primary mb-3 flex items-center gap-2">
              <span className="w-4 h-px bg-primary/30"></span>
              Strongest Point
            </h3>
            <div className="bg-surface-container-low/40 border border-outline-variant/10 p-5 rounded-2xl text-on-surface transition-all group-hover:border-primary/20 group-hover:bg-primary/5">
              <p className="text-sm leading-relaxed">{strongest || verdict}</p>
            </div>
          </div>
          
          {/* Weakness */}
          {weakness && (
            <div className="group transition-all duration-300">
              <h3 className="text-[10px] font-black font-label uppercase tracking-[0.2em] text-tertiary mb-3 flex items-center gap-2">
                <span className="w-4 h-px bg-tertiary/30"></span>
                Critical Weakness
              </h3>
              <div className="bg-surface-container-low/40 border border-outline-variant/10 p-5 rounded-2xl text-on-surface transition-all group-hover:border-tertiary/20 group-hover:bg-tertiary/5">
                <p className="text-sm leading-relaxed">{weakness}</p>
              </div>
            </div>
          )}
          
          {/* Fix */}
          {toFix && (
            <div className="group transition-all duration-300">
              <h3 className="text-[10px] font-black font-label uppercase tracking-[0.2em] text-primary/70 mb-3 flex items-center gap-2">
                <span className="w-4 h-px bg-primary/20"></span>
                Optimization Required
              </h3>
              <div className="bg-surface-container-low/40 border border-outline-variant/10 p-5 rounded-2xl text-on-surface/80 transition-all group-hover:border-primary/20">
                <p className="text-sm leading-relaxed">{toFix}</p>
              </div>
            </div>
          )}
        </div>
        
        {/* Actions Section */}
        <div className="p-8 pt-0 flex flex-col items-center gap-6">
          <button 
            onClick={handleDownload} 
            className="cta-gradient w-full py-4 rounded-2xl font-bold text-white shadow-[0_8px_24px_-8px_rgba(24,200,151,0.5)] transition-all hover:scale-[1.02] flex items-center justify-center gap-3 active:scale-95 uppercase tracking-widest text-xs"
          >
            <span className="material-symbols-outlined text-[18px]">download</span>
            Generate Comprehensive Analysis
          </button>
          
          <div className="flex items-center gap-4 text-[9px] font-black font-label uppercase tracking-widest text-on-surface-variant/30">
            <span>Encrypted Ledger Saved</span>
            <span className="w-1 h-1 bg-on-surface-variant/20 rounded-full"></span>
            <span>Ref: PTTP-S{sessionId.slice(0,4)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
