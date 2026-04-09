"use client";

import React, { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Header } from "../../components/Header";
import { Sidebar } from "../../components/Sidebar";

const API_BASE = "http://localhost:8000/api";

interface ReportData {
  pitch_summary: string;
  strengths: string[];
  risks: string[];
  claims: string[];
  contradictions: string[];
  missing_points: string[];
  verdict: string;
  confidence_score: number;
  investment_signal: "STRONG" | "MEDIUM" | "WEAK";
  black_swan_insight?: string;
  charts: {
    bar_chart?: string;
    pie_chart?: string;
  };
  scores: {
    strength: number;
    risk: number;
    clarity: number;
    consistency: number;
  };
}

export default function ReportPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const sessionId = searchParams.get("sessionId");
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setError("No session ID provided");
      setLoading(false);
      return;
    }

    const fetchReport = async () => {
      try {
        const response = await fetch(`${API_BASE}/session/${sessionId}/report`);
        if (!response.ok) throw new Error("Failed to fetch report");
        const data = await response.json();
        setReport(data);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchReport();
  }, [sessionId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-50">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="text-slate-500 font-bold uppercase tracking-widest text-xs">Synthesizing Final Analysis...</p>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-50">
        <div className="text-center space-y-6">
          <span className="material-symbols-outlined text-6xl text-rose-500">error</span>
          <p className="text-slate-800 font-bold text-xl">{error || "Report not found"}</p>
          <button 
            onClick={() => router.push("/")}
            className="px-8 py-3 bg-indigo-600 text-white rounded-full font-bold uppercase tracking-widest text-xs"
          >
            Back to Home
          </button>
        </div>
      </div>
    );
  }

  const signalColors = {
    STRONG: "bg-emerald-500 text-white shadow-emerald-500/40",
    MEDIUM: "bg-amber-500 text-white shadow-amber-500/40",
    WEAK: "bg-rose-500 text-white shadow-rose-500/40",
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden text-slate-900">
      <Sidebar onNewPitch={() => router.push("/")} currentView="report" onViewChange={() => {}} />

      <main className="flex-1 flex flex-col h-full overflow-hidden">
        <Header provider="anthropic" setProvider={() => {}} disabled={true} />

        <div className="flex-1 overflow-y-auto p-12 custom-scrollbar">
          <div className="max-w-6xl mx-auto space-y-12 pb-20">
            {/* Page Title & Signal */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 animate-in fade-in slide-in-from-bottom-5 duration-700">
              <div className="space-y-4">
                <p className="text-[11px] font-black text-indigo-600 uppercase tracking-[0.3em]">Evaluation Complete</p>
                <h1 className="text-6xl font-black tracking-tighter leading-none">Investment Analysis</h1>
                <p className="text-xl text-slate-400 font-medium">Session ID: <span className="font-mono text-sm">{sessionId}</span></p>
              </div>
              <div className="flex items-center gap-6">
                <div className="text-right space-y-2">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Signal Confidence</p>
                  <div className={`px-8 py-3 rounded-2xl font-black text-xl tracking-tighter shadow-lg ${signalColors[report.investment_signal]}`}>
                    {report.investment_signal}
                  </div>
                </div>
                <div className="w-24 h-24 rounded-3xl bg-white border border-slate-100 shadow-xl flex flex-col items-center justify-center">
                  <span className="text-3xl font-black text-slate-800">{report.confidence_score}</span>
                  <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Points</span>
                </div>
              </div>
            </div>

            {/* Section 1: Summary & Verdict */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
              <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="lg:col-span-12 bg-white rounded-[3rem] p-12 shadow-sm border border-slate-100 space-y-8"
              >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-16">
                  <div className="space-y-6">
                    <h3 className="text-2xl font-black tracking-tight flex items-center gap-3">
                      <span className="material-symbols-outlined text-indigo-600">summary</span>
                      Pitch Summary
                    </h3>
                    <p className="text-lg text-slate-600 leading-relaxed font-medium bg-slate-50 p-8 rounded-[2rem]">
                      {report.pitch_summary}
                    </p>
                  </div>
                  <div className="space-y-6">
                     <h3 className="text-2xl font-black tracking-tight flex items-center gap-3">
                        <span className="material-symbols-outlined text-indigo-600">gavel</span>
                        Final Verdict
                      </h3>
                      <div className="bg-indigo-600 text-white p-8 rounded-[2rem] shadow-xl shadow-indigo-600/10 min-h-[160px] flex items-center">
                        <p className="text-xl font-bold leading-relaxed italic opacity-95">
                          "{report.verdict}"
                        </p>
                      </div>
                  </div>
                </div>
              </motion.div>
            </div>

            {/* Section 2: Key Insights Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {/* Strengths */}
              <motion.div 
                whileHover={{ y: -5 }}
                className="bg-white rounded-[2.5rem] p-10 border border-slate-100 shadow-sm space-y-8"
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-black tracking-tight flex items-center gap-3">
                    <span className="material-symbols-outlined text-emerald-500">add_circle</span>
                    Strengths
                  </h3>
                  <span className="bg-emerald-50 text-emerald-600 text-[10px] font-black px-3 py-1 rounded-full">{report.strengths.length}</span>
                </div>
                <div className="space-y-4">
                  {report.strengths.map((item, i) => (
                    <div key={i} className="flex gap-4 p-4 rounded-2xl bg-emerald-50/30 border border-emerald-100/30">
                      <span className="text-emerald-500 font-black">•</span>
                      <p className="text-sm font-medium text-slate-700 leading-snug">{item}</p>
                    </div>
                  ))}
                </div>
              </motion.div>

              {/* Risks */}
              <motion.div 
                whileHover={{ y: -5 }}
                className="bg-white rounded-[2.5rem] p-10 border border-slate-100 shadow-sm space-y-8"
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-black tracking-tight flex items-center gap-3">
                    <span className="material-symbols-outlined text-rose-500">warning</span>
                    Risks
                  </h3>
                  <span className="bg-rose-50 text-rose-600 text-[10px] font-black px-3 py-1 rounded-full">{report.risks.length}</span>
                </div>
                <div className="space-y-4">
                  {report.risks.map((item, i) => (
                    <div key={i} className="flex gap-4 p-4 rounded-2xl bg-rose-50/30 border border-rose-100/30">
                      <span className="text-rose-500 font-black">•</span>
                      <p className="text-sm font-medium text-slate-700 leading-snug">{item}</p>
                    </div>
                  ))}
                </div>
              </motion.div>

              {/* Contradictions */}
              <motion.div 
                whileHover={{ y: -5 }}
                className="bg-white rounded-[2.5rem] p-10 border border-slate-100 shadow-sm space-y-8"
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-black tracking-tight flex items-center gap-3">
                    <span className="material-symbols-outlined text-amber-500">emergency</span>
                    Contradictions
                  </h3>
                  <span className="bg-amber-50 text-amber-600 text-[10px] font-black px-3 py-1 rounded-full">{report.contradictions.length}</span>
                </div>
                <div className="space-y-4">
                  {report.contradictions.map((item, i) => (
                    <div key={i} className="flex gap-4 p-4 rounded-2xl bg-amber-50/30 border border-amber-100/30">
                      <span className="text-amber-500 font-black">•</span>
                      <p className="text-sm font-medium text-slate-700 leading-snug">{item}</p>
                    </div>
                  ))}
                </div>
              </motion.div>
            </div>

            {/* Section 3: Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
              {report.charts.bar_chart && (
                <div className="lg:col-span-8 bg-white rounded-[3rem] p-12 shadow-sm border border-slate-100 space-y-8">
                  <h3 className="text-2xl font-black tracking-tight uppercase text-xs tracking-[0.2em] text-slate-400">Competitive Landscape & Readiness</h3>
                  <img 
                    src={`data:image/png;base64,${report.charts.bar_chart}`} 
                    alt="Bar Chart Analysis" 
                    className="w-full h-auto rounded-3xl"
                  />
                </div>
              )}

              {report.charts.pie_chart && (
                <div className="lg:col-span-4 bg-white rounded-[3rem] p-12 shadow-sm border border-slate-100 space-y-8 flex flex-col justify-center">
                  <h3 className="text-2xl font-black tracking-tight uppercase text-xs tracking-[0.2em] text-slate-400">Equilibrium</h3>
                  <img 
                    src={`data:image/png;base64,${report.charts.pie_chart}`} 
                    alt="Pie Chart Analysis" 
                    className="w-full h-auto"
                  />
                </div>
              )}
            </div>

            {/* Section 4: Black Swan & Missing Points */}
            {(report.black_swan_insight || report.missing_points.length > 0) && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {report.black_swan_insight && (
                  <div className="bg-slate-900 text-white rounded-[3rem] p-12 space-y-8 shadow-2xl relative overflow-hidden group">
                    <div className="absolute -top-10 -right-10 w-40 h-40 bg-indigo-600/20 rounded-full blur-3xl group-hover:bg-indigo-600/40 transition-all"></div>
                    <div className="space-y-2 relative">
                      <h3 className="text-2xl font-black tracking-tight flex items-center gap-3">
                        <span className="material-symbols-outlined text-indigo-400">science</span>
                        Black Swan Insight
                      </h3>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Unexpected Market Opportunity/Risk</p>
                    </div>
                    <p className="text-lg leading-relaxed font-medium opacity-80 relative italic">
                      {report.black_swan_insight}
                    </p>
                  </div>
                )}

                {report.missing_points.length > 0 && (
                  <div className="bg-white rounded-[3rem] p-12 border border-slate-100 shadow-sm space-y-8">
                    <div className="space-y-2">
                       <h3 className="text-2xl font-black tracking-tight flex items-center gap-3">
                          <span className="material-symbols-outlined text-indigo-600">help_center</span>
                          Missing Information
                        </h3>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Critical fields for next pitch</p>
                    </div>
                    <div className="space-y-4">
                      {report.missing_points.map((item, i) => (
                        <div key={i} className="p-5 rounded-2xl bg-slate-50 border border-slate-100 text-sm font-bold text-slate-600">
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}