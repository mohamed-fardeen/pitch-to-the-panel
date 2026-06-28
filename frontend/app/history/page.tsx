"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";

const API_BASE = "http://localhost:8000/api";

interface PitchRecord {
  id: string;
  session_id: string;
  pitch_summary: string;
  strongest: string;
  weakness: string;
  fix: string;
  confidence_score: number;
  timestamp: number;
}

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? "bg-emerald-100 text-emerald-700 border-emerald-200" :
    score >= 45 ? "bg-amber-100 text-amber-700 border-amber-200" :
                  "bg-rose-100 text-rose-700 border-rose-200";
  return (
    <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-black border ${color}`}>
      {score}<span className="font-medium opacity-60">/100</span>
    </span>
  );
}

function formatDate(ts: number) {
  if (!ts) return "Unknown date";
  return new Date(ts * 1000).toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit"
  });
}

export default function HistoryPage() {
  const router = useRouter();
  const [pitches, setPitches] = useState<PitchRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch(`${API_BASE}/pitch-history?limit=50`);
        if (!res.ok) throw new Error("Failed to load history");
        const data = await res.json();
        setPitches(data.pitches || []);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchHistory();
  }, []);

  const handleRePitch = (summary: string) => {
    localStorage.setItem("pttp_repitch", summary);
    router.push("/");
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* Top bar */}
      <div className="sticky top-0 z-10 bg-white/80 backdrop-blur-xl border-b border-slate-100 px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push("/")}
            className="flex items-center gap-2 text-slate-400 hover:text-slate-700 transition-colors"
          >
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          <div>
            <h1 className="text-xl font-black tracking-tight">Pitch History</h1>
            <p className="text-xs text-slate-400 font-medium">All sessions stored in Supabase pgvector</p>
          </div>
        </div>
        {!loading && (
          <span className="bg-indigo-50 text-indigo-600 text-xs font-black px-4 py-2 rounded-full border border-indigo-100">
            {pitches.length} session{pitches.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div className="max-w-5xl mx-auto px-8 py-12">
        {loading && (
          <div className="flex items-center justify-center py-32">
            <div className="text-center space-y-4">
              <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
              <p className="text-slate-400 text-sm font-bold uppercase tracking-widest">Loading from Supabase...</p>
            </div>
          </div>
        )}

        {error && (
          <div className="text-center py-32 space-y-4">
            <span className="material-symbols-outlined text-5xl text-slate-300">cloud_off</span>
            <p className="text-slate-500 font-bold">Could not load history</p>
            <p className="text-slate-400 text-sm">{error}</p>
            <p className="text-xs text-slate-300">Make sure SUPABASE_DB_URL is configured and the pgvector extension is enabled.</p>
          </div>
        )}

        {!loading && !error && pitches.length === 0 && (
          <div className="text-center py-32 space-y-4">
            <span className="material-symbols-outlined text-6xl text-slate-200">history</span>
            <h2 className="text-2xl font-black text-slate-300">No sessions yet</h2>
            <p className="text-slate-400">Complete a pitch session to see it appear here.</p>
            <button
              onClick={() => router.push("/")}
              className="mt-4 px-8 py-3 bg-indigo-600 text-white rounded-2xl font-bold text-sm uppercase tracking-widest hover:bg-indigo-500 transition-colors"
            >
              Start a Pitch
            </button>
          </div>
        )}

        {!loading && !error && pitches.length > 0 && (
          <div className="space-y-4">
            {pitches.map((pitch, i) => (
              <motion.div
                key={pitch.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                className="bg-white rounded-[2rem] border border-slate-100 shadow-sm overflow-hidden"
              >
                {/* Header Row */}
                <button
                  onClick={() => setExpanded(expanded === pitch.id ? null : pitch.id)}
                  className="w-full text-left px-8 py-6 flex items-start justify-between gap-6 hover:bg-slate-50 transition-colors"
                >
                  <div className="flex-1 space-y-2 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <ScoreBadge score={pitch.confidence_score} />
                      <span className="text-xs text-slate-400 font-mono">{formatDate(pitch.timestamp)}</span>
                    </div>
                    <p className="text-sm font-bold text-slate-700 line-clamp-2 leading-relaxed">
                      {pitch.pitch_summary || "No summary available"}
                    </p>
                  </div>
                  <span className={`material-symbols-outlined text-slate-300 transition-transform shrink-0 mt-1 ${expanded === pitch.id ? "rotate-180" : ""}`}>
                    expand_more
                  </span>
                </button>

                {/* Expanded Details */}
                {expanded === pitch.id && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="border-t border-slate-100 px-8 py-6 space-y-6"
                  >
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {pitch.strongest && (
                        <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-100 space-y-2">
                          <p className="text-[10px] font-black text-emerald-600 uppercase tracking-widest">Strongest Point</p>
                          <p className="text-sm text-slate-700 font-medium leading-snug">{pitch.strongest}</p>
                        </div>
                      )}
                      {pitch.weakness && (
                        <div className="p-4 rounded-2xl bg-rose-50 border border-rose-100 space-y-2">
                          <p className="text-[10px] font-black text-rose-600 uppercase tracking-widest">Biggest Weakness</p>
                          <p className="text-sm text-slate-700 font-medium leading-snug">{pitch.weakness}</p>
                        </div>
                      )}
                      {pitch.fix && (
                        <div className="p-4 rounded-2xl bg-indigo-50 border border-indigo-100 space-y-2">
                          <p className="text-[10px] font-black text-indigo-600 uppercase tracking-widest">Advised Fix</p>
                          <p className="text-sm text-slate-700 font-medium leading-snug">{pitch.fix}</p>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => handleRePitch(pitch.pitch_summary)}
                        className="flex items-center gap-2 px-5 py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold text-xs uppercase tracking-widest transition-colors"
                      >
                        <span className="material-symbols-outlined text-sm">send</span>
                        Re-Pitch This
                      </button>
                      {pitch.session_id && (
                        <button
                          onClick={() => router.push(`/report?sessionId=${pitch.session_id}`)}
                          className="flex items-center gap-2 px-5 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-bold text-xs uppercase tracking-widest transition-colors"
                        >
                          <span className="material-symbols-outlined text-sm">open_in_new</span>
                          View Report
                        </button>
                      )}
                    </div>
                  </motion.div>
                )}
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
