"use client";

import React, { useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { GraphView } from "../../components/graph/GraphView";
import { useDebugStream } from "../../components/analytics/useDebugStream";
import { Sidebar } from "../../components/Sidebar";
import { Header } from "../../components/Header";

const API_BASE = "http://localhost:8000/api";

function GraphPageContent() {
  const searchParams = useSearchParams();
  const sessionIdParam = searchParams.get("session_id");
  const [sessionId, setSessionId] = useState<string | null>(sessionIdParam);
  const debugStream = useDebugStream();
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!sessionId) return;

    const url = new URL(`${API_BASE}/stream/main`);
    url.searchParams.append("session_id", sessionId);
    url.searchParams.append("debug_only", "true"); // Hint to backend to only send debug events if possible

    const eventSource = new window.EventSource(url.toString());
    eventSourceRef.current = eventSource;
    debugStream.setConnected(true);

    eventSource.addEventListener("debug_node", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        debugStream.pushEvent("debug_node", data);
      } catch {}
    });

    eventSource.addEventListener("memory_update", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        debugStream.pushEvent("memory_update", data);
      } catch {}
    });

    eventSource.addEventListener("conversation_complete", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        debugStream.pushEvent("conversation_complete", data);
      } catch {}
    });

    eventSource.onerror = () => {
      if (eventSource.readyState === EventSource.CLOSED) {
        debugStream.setConnected(false);
      }
    };

    return () => {
      eventSource.close();
      eventSourceRef.current = null;
    };
  }, [sessionId]);

  return (
    <div className="flex h-screen overflow-hidden bg-white text-slate-900">
      <Sidebar 
        currentView="graph" 
        onViewChange={(v) => {
          if (v !== "graph") window.location.href = `/?view=${v}${sessionId ? `&session_id=${sessionId}` : ''}`;
        }} 
        onNewPitch={() => window.location.href = '/'} 
      />

      <main className="flex-1 flex flex-col min-w-0 h-full relative">
        <Header />
        
        {!sessionId ? (
          <div className="flex-1 flex flex-col items-center justify-center p-20 text-center space-y-8 bg-slate-50">
            <div className="w-24 h-24 bg-indigo-50 rounded-[2rem] flex items-center justify-center border border-indigo-100 shadow-xl shadow-indigo-900/5">
               <span className="material-symbols-outlined text-4xl text-indigo-400">hub</span>
            </div>
            <div className="max-w-md space-y-4">
               <h2 className="text-3xl font-black text-slate-800 tracking-tight">Connect to Session</h2>
               <p className="text-slate-400 font-medium leading-relaxed">Please provide a valid session ID to visualize the agentic neural network in real-time.</p>
            </div>
            <div className="flex gap-4 w-full max-w-sm">
               <input 
                 value={sessionId || ""} 
                 onChange={(e) => setSessionId(e.target.value)}
                 placeholder="Enter Session UUID..." 
                 className="flex-1 bg-white border border-slate-200 rounded-2xl py-4 px-6 text-sm font-medium focus:ring-2 focus:ring-indigo-500/10 outline-none"
               />
               <button 
                 onClick={() => setSessionId(sessionId)}
                 className="px-8 py-4 bg-indigo-600 text-white font-bold rounded-2xl shadow-lg shadow-indigo-900/10 hover:bg-indigo-700 transition-all"
               >
                 Link
               </button>
            </div>
          </div>
        ) : (
          <GraphView debugStream={debugStream} />
        )}
      </main>
    </div>
  );
}

export default function GraphPage() {
  return (
    <Suspense fallback={<div className="h-screen w-screen flex items-center justify-center bg-white font-black text-3xl animate-pulse">LOADING NEURAL CORE...</div>}>
      <GraphPageContent />
    </Suspense>
  );
}
