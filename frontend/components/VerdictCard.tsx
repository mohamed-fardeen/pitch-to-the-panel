"use client";

import React from "react";
const API_BASE = "http://localhost:8000/api";

interface VerdictCardProps {
  verdict: any;
  sessionId: string;
  onClose: () => void;
}

export function VerdictCard({ verdict, sessionId, onClose }: VerdictCardProps) {
  const verdictText = typeof verdict === "string" ? verdict : (verdict?.insight || verdict?.verdict || "");
  const isV3 = verdictText.includes("BLACK SWAN") || verdictText.includes("EXECUTIVE SUMMARY");
  
  const v2Parts = !isV3 ? verdictText.split(/Your biggest weakness:|Before your next pitch:/i) : [];
  const strongest = !isV3 ? (v2Parts[0]?.replace(/Your strongest point:/i, "").trim() || "") : "";
  const weakness = !isV3 ? (v2Parts[1]?.trim() || "") : "";
  const toFix = !isV3 ? (v2Parts[2]?.trim() || "") : "";

  const handleDownloadReport = async () => {
    try {
      const response = await fetch(`${API_BASE}/session/${sessionId}/report/pdf`);
      if (!response.ok) throw new Error("Report not ready");

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pitch-report-${sessionId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Defer revocation: some browsers cancel the download if the object URL
      // is revoked synchronously after click().
      setTimeout(() => window.URL.revokeObjectURL(url), 2000);
    } catch (err) {
      console.error("Download failed:", err);
    }
  };

  return (
    <div className="fixed inset-0 bg-surface/80 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-in fade-in duration-500" onClick={onClose}>
      <div 
        className="bg-surface-container border border-outline-variant/10 max-w-2xl w-full rounded-[2.5rem] shadow-2xl p-0 overflow-hidden transform transition-all translate-y-0 max-h-[90vh] flex flex-col" 
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Section */}
        <div className="p-10 pb-6 text-center relative border-b border-outline-variant/5">
          <button onClick={onClose} className="absolute top-8 right-8 text-slate-300 hover:text-on-surface transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
          
          <div className="inline-flex items-center gap-2 mb-6 bg-primary/10 px-6 py-2 rounded-full border border-primary/20">
             <span className="material-symbols-outlined text-[18px] text-primary">analytics</span>
             <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-primary">
               {isV3 ? "Black Swan Meta-Analysis" : "System Evaluation Complete"}
             </span>
          </div>
          
          <h2 className="text-4xl font-headline font-extrabold text-on-surface uppercase tracking-tighter mb-2">
            Focus Group <span className="text-primary italic">{isV3 ? "Intelligence" : "Verdict"}</span>
          </h2>
          <p className="text-slate-400 text-[10px] font-bold uppercase tracking-widest">Protocol ID: {sessionId.slice(0, 8)}</p>
        </div>
        
        {/* Content Section */}
        <div className="p-10 space-y-8 overflow-y-auto custom-scrollbar flex-1">
          {isV3 ? (
            <div className="text-on-surface leading-loose space-y-10">
              {verdictText.split('\n\n').map((p: string, i: number) => {
                const isHeader = p.startsWith('#') || p.toUpperCase() === p;
                if (isHeader) {
                  return (
                    <h4 key={i} className="text-[11px] font-extrabold uppercase tracking-[0.3em] text-primary mt-8 mb-4 border-l-4 border-primary/20 pl-6">
                      {p.replace(/#/g, '').trim()}
                    </h4>
                  );
                }
                return (
                  <p key={i} className="text-lg font-medium text-slate-600 leading-relaxed italic border-b border-outline-variant/5 pb-6 last:border-0">
                    {p}
                  </p>
                );
              })}
            </div>
          ) : (
            <div className="space-y-8">
              <div className="group transition-all">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-primary mb-4 flex items-center gap-3">
                  <span className="w-6 h-px bg-primary/20"></span>
                  Strongest Point
                </h3>
                <div className="bg-white border border-outline-variant/5 p-8 rounded-[2rem] text-on-surface shadow-sm group-hover:shadow-md transition-all">
                  <p className="text-lg font-medium leading-relaxed">{strongest || verdictText}</p>
                </div>
              </div>
              {weakness && (
                <div className="group transition-all">
                  <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-rose-500 mb-4 flex items-center gap-3">
                    <span className="w-6 h-px bg-rose-200"></span>
                    Critical Weakness
                  </h3>
                  <div className="bg-rose-50 border border-rose-100 p-8 rounded-[2rem] text-slate-800 shadow-sm group-hover:shadow-md transition-all">
                    <p className="text-lg font-medium leading-relaxed">{weakness}</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        
        {/* Actions Section */}
        <div className="p-10 pt-0">
          <button 
            onClick={handleDownloadReport} 
            className="w-full py-6 primary-gradient rounded-2xl font-headline font-extrabold text-white shadow-xl shadow-primary/20 hover:scale-[1.01] flex items-center justify-center gap-4 transition-all uppercase tracking-tighter text-xl"
          >
            <span className="material-symbols-outlined">download</span>
            Generate Full Report
          </button>
          
          <div className="mt-8 flex items-center justify-center gap-6 text-[10px] font-bold uppercase tracking-widest text-slate-300">
            <span>Encrypted Protocol</span>
            <span className="w-1.5 h-1.5 bg-slate-200 rounded-full"></span>
            <span>Ref: {sessionId.slice(0,6)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
