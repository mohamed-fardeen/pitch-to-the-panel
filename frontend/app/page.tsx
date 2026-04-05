"use client";

import React, { useState, useEffect, useRef } from "react";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useAgentVoice } from "../hooks/useAgentVoice";
import { PanelState, AgentStatus, AgentRole, ConversationTurn } from "../types/v2_types";
import { Sidebar } from "../components/Sidebar";
import { Header } from "../components/Header";
import { LiveFeed } from "../components/LiveFeed";
import { AgentCard } from "../components/AgentCard";
import { VerdictCard } from "../components/VerdictCard";
import { Provider } from "../components/ModelSelector";
import { useDebugStream } from "../components/analytics/useDebugStream";
import { NodeCard } from "../components/analytics/NodeCard";
import { FlowTimeline } from "../components/analytics/FlowTimeline";
import { MemoryPanel } from "../components/analytics/MemoryPanel";

const API_BASE = "http://localhost:8000/api";

export default function Home() {
  const { isRecording, transcript, startRecording, stopRecording } = useSpeechRecognition();
  const { speak, stopSpeaking } = useAgentVoice();
  
  const [provider, setProvider] = useState<Provider>("anthropic");
  const [stage, setStage] = useState<"idle" | "pitching" | "hitl_summary" | "conversation" | "verdict">("idle");
  const [showVerdictModal, setShowVerdictModal] = useState(false);
  const [panelState, setPanelState] = useState<PanelState>({});
  const [logs, setLogs] = useState<string[]>([]);
  
  const [conversation, setConversation] = useState<ConversationTurn[]>([]);
  const [waitingForAnswer, setWaitingForAnswer] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState("");
  
  const [verdictData, setVerdictData] = useState<any>(null);
  const [domainData, setDomainData] = useState<any>(null);
  const [hitlData, setHitlData] = useState<any>(null);
  const [difficulty, setDifficulty] = useState("standard");
  const [radarChart, setRadarChart] = useState<string | null>(null);
  
  const [manualText, setManualText] = useState("");
  const [pushbackText, setPushbackText] = useState("");
  const [isPushbacking, setIsPushbacking] = useState(false);
  const [factChecks, setFactChecks] = useState<Record<string, string>>({});

  const [coachHints, setCoachHints] = useState<string | null>(null);
  const [coachLoading, setCoachLoading] = useState(false);
  const [weakAnswerDetected, setWeakAnswerDetected] = useState(false);
  const [currentAgentId, setCurrentAgentId] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [retryCounts, setRetryCounts] = useState<Record<string, number>>({});
  const [retryStatus, setRetryStatus] = useState<string | null>(null);
  
  const [challengingAgentId, setChallengingAgentId] = useState<string | null>(null);
  const [challengingAgentClaim, setChallengingAgentClaim] = useState<string | null>(null);
  const [isRebutting, setIsRebutting] = useState(false);
  const [needsSkipApproval, setNeedsSkipApproval] = useState(false);

  const [isInterrupting, setIsInterrupting] = useState(false);
  const [isAnsweringInterrupt, setIsAnsweringInterrupt] = useState(false);
  const [activeHosts, setActiveHosts] = useState<{host_a: any, host_b: any} | null>(null);

  // Agentic v4 States
  const [awaitingPitchConfirmation, setAwaitingPitchConfirmation] = useState(false);
  const [awaitingUserInput, setAwaitingUserInput] = useState(false);
  const [originalSummary, setOriginalSummary] = useState("");

  const audioQueueRef = useRef<{role: AgentRole, text: string}[]>([]);
  const isPlayingRef = useRef(false);

  const playNextInQueue = () => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return;
    isPlayingRef.current = true;
    const next = audioQueueRef.current.shift();
    if (next) {
      speak(next.role as AgentRole, next.text, () => {
        setTimeout(() => {
          isPlayingRef.current = false;
          playNextInQueue();
        }, 100);
      });
    }
  };

  const enqueueSpeech = (role: string, text: string) => {
    audioQueueRef.current.push({ role: role as AgentRole, text });
    playNextInQueue();
  };

  const cancelAllSpeech = () => {
    stopSpeaking();
    audioQueueRef.current = [];
    isPlayingRef.current = false;
  };

  const addLog = (msg: string) => setLogs((prev: string[]) => [...prev, msg]);

  useEffect(() => {
    if (transcript) setManualText(transcript);
  }, [transcript]);

  const updateAgentState = (agent: string, chunk: string, status: "idle" | "streaming" | "done" | "error", clear: boolean = false) => {
    setPanelState((prev: PanelState) => {
      const existing = prev[agent] || { text: "", status: "idle" as AgentStatus, role: "critic" as AgentRole, name: agent };
      return {
        ...prev,
        [agent]: {
          ...existing,
          text: clear ? chunk : (chunk === "" ? existing.text : existing.text + chunk),
          status: status === "streaming" ? "speaking" : "idle"
        }
      };
    });
  };

  const [view, setView] = useState<string>("panel");
  const [libraryData, setLibraryData] = useState<any>(null);

  const fetchLibrary = async () => {
    try {
      const res = await fetch(`${API_BASE}/memory`);
      const data = await res.json();
      setLibraryData(data.pitchers || {});
    } catch (err) {
      console.error("Failed to fetch library:", err);
    }
  };

  const [sessionId, setSessionId] = useState("");
  const [pitcherId, setPitcherId] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeAgent, setActiveAgent] = useState<{ id: string, name: string } | null>(null);

  // Analytics debug stream — passive accumulator fed by the main EventSource
  const debugStream = useDebugStream();
  const analyticsListEndRef = useRef<HTMLDivElement>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  const sessionInitialized = useRef(false);

  useEffect(() => {
    if (!sessionInitialized.current) {
      sessionInitialized.current = true;
      const newSessionId = crypto.randomUUID();
      setSessionId(newSessionId);
      console.log("Initial Session ID generated:", newSessionId);
    }
    
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (view === "library") {
      fetchLibrary();
    }
  }, [view]);

  const handleNewPitch = () => {
    setStage("idle");
    const newSessionId = crypto.randomUUID();
    setSessionId(newSessionId);
    console.log("New Session ID generated:", newSessionId);
    setLogs([]);
    setConversation([]);
    setPanelState({});
    setVerdictData(null);
    setShowVerdictModal(false);
    setView("panel");
    debugStream.reset();
  };

  const startPitch = () => {
    setStage("pitching");
    setManualText("");
    const newSessionId = crypto.randomUUID();
    setSessionId(newSessionId);
    console.log("Session ID for pitch:", newSessionId);
    setConversation([]);
    setPanelState({});
    setShowVerdictModal(false);
    debugStream.reset();
  };

  const finishPitch = async () => {
    stopRecording();
    const currentPitch = manualText;
    addLog("Evaluating Proposal...");

    const url = new URL(`${API_BASE}/stream/main`);
    url.searchParams.append("session_id", sessionId);
    url.searchParams.append("pitch", currentPitch);
    url.searchParams.append("provider", provider);
    url.searchParams.append("difficulty", difficulty);
    if (pitcherId) url.searchParams.append("pitcher_id", pitcherId);

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const eventSource = new window.EventSource(url.toString());
    eventSourceRef.current = eventSource;
    setIsStreaming(true);

    eventSource.onopen = () => {
      console.log("Stream connected for session:", sessionId);
      debugStream.setConnected(true);
    };

    eventSource.addEventListener("hitl_summary_approval", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Event received: hitl_summary_approval", data);
      setHitlData(data);
      setOriginalSummary(data.summary);
      setAwaitingPitchConfirmation(true);
      setStage("hitl_summary");
      setConversation([{
        type: "answer",
        agent_name: pitcherId || "Alex Chen",
        content: currentPitch
      }]);
    });

    eventSource.addEventListener("echochamber_start", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Event received: echochamber_start", data);
      setStage("conversation");
      const initialState: PanelState = {};
      initialState["interviewer"] = { text: "", status: "idle", role: "host", name: "Lead Interviewer" };
      if (data.personas && Array.isArray(data.personas)) {
        data.personas.forEach((p: any) => {
          initialState[p.id] = { text: "", status: "idle", role: "critic", name: p.name, avatarUrl: p.avatar };
        });
      }
      setPanelState(initialState);
    });

    eventSource.addEventListener("agent_start", (e: any) => {
        const data = JSON.parse(e.data);
        setActiveAgent({ id: data.agent_id, name: data.name });
    });

    eventSource.addEventListener("agent_turn", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Event received: agent_turn", data);
      setCurrentAgentId(data.agent_id);
      setActiveAgent(null);
      
      if (data.type === "interviewer_invitation") {
        setWaitingForAnswer(true);
      }
      
      if (data.token) {
        updateAgentState(data.agent_id, data.token, "streaming");
      } else if (data.content) {
        updateAgentState(data.agent_id, data.content, "done", true);
        enqueueSpeech(data.agent_id, data.content);
        
        setConversation((prev: ConversationTurn[]) => [...prev, {
          type: data.turn_type || data.type || "persona_response",
          agent_id: data.agent_id,
          agent_name: data.agent_name || data.name || data.agent_id,
          content: data.content
        }]);
      }
      debugStream.pushEvent("agent_turn", data);
    });

    eventSource.addEventListener("waiting_for_pitcher", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Event received: waiting_for_pitcher", data);
      setWaitingForAnswer(true);
      setAwaitingUserInput(true);
      setCurrentQuestion(data.question);
      setManualText("");
    });

    eventSource.addEventListener("black_swan_report", (e: any) => {
      const data = JSON.parse(e.data);
      setVerdictData(data);
      setStage("verdict");
      setShowVerdictModal(true);
    });

    eventSource.addEventListener("verdict_complete", (e: any) => {
      const data = JSON.parse(e.data);
      if (!verdictData) setVerdictData(data);
      setStage("verdict");
      setShowVerdictModal(true);
      setIsStreaming(false);
    });

    // Named 'error' events are fatal errors sent by the server explicitly
    eventSource.addEventListener("error", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        console.error("Fatal stream error from server:", data);
      } catch {
        console.error("Fatal stream error:", e);
      }
      eventSource.close();
      eventSourceRef.current = null;
      setIsStreaming(false);
      setActiveAgent(null);
    });

    // heartbeat events keep the connection alive — silently ignore them
    eventSource.addEventListener("heartbeat", () => {});

    // debug_node events feed the analytics execution graph
    eventSource.addEventListener("debug_node", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        debugStream.pushEvent("debug_node", data);
      } catch {}
    });

    // onerror fires on transient network issues — don't close if SSE is still trying to reconnect
    eventSource.onerror = (e: any) => {
      if (eventSource.readyState === EventSource.CLOSED) {
        console.error("SSE connection closed unexpectedly.");
        eventSourceRef.current = null;
        setIsStreaming(false);
        setActiveAgent(null);
      } else {
        // readyState is CONNECTING — browser is auto-reconnecting, don't interfere
        console.warn("SSE transient error, browser reconnecting...");
      }
    };
    
    eventSource.addEventListener("conversation_complete", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Event received: conversation_complete", data);
      setStage("verdict");
      setVerdictData(data);
      setShowVerdictModal(true);
      setIsStreaming(false);
      setActiveAgent(null);
      debugStream.pushEvent("conversation_complete", data);
      debugStream.setConnected(false);
    });
  };

  const approveSummary = async () => {
    if (!hitlData) return;
    console.log("Sending approval request...");
    const isEdited = hitlData.summary !== originalSummary;
    
    setStage("conversation");
    setAwaitingPitchConfirmation(false);
    
    // Update the first conversation turn (the pitch) with the refined/approved summary
    setConversation((prev: any[]) => {
      if (prev.length > 0) {
        const newConv = [...prev];
        newConv[0] = { ...newConv[0], content: hitlData.summary };
        return newConv;
      }
      return prev;
    });
    
    try {
      await fetch(`${API_BASE}/pitch/approve-summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          approved: true,
          corrected_summary: isEdited ? hitlData.summary : null
        })
      });
    } catch(e) {
      console.error("Failed to approve summary:", e);
    }
  };

  const submitAnswer = async () => {
    if (!manualText) return;
    const ans = manualText;
    setAwaitingUserInput(false);
    
    try {
      console.log("Sending answer to session:", sessionId);
      await fetch(`${API_BASE}/conversation/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: ans
        })
      });
      
      setManualText("");
    } catch(e) {}
  };

  const handleInterrupt = () => {
    cancelAllSpeech();
    setWaitingForAnswer(true);
    setCurrentQuestion("Jumping in...");
    setIsAnsweringInterrupt(true);
  };

  const endConversation = () => setStage("verdict");

  const getCoachHints = async () => {
    setCoachLoading(true);
    try {
      const res = await fetch(`${API_BASE}/conversation/coach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, agent_id: currentAgentId, question: currentQuestion })
      });
      const data = await res.json();
      setCoachHints(data.coach_hints);
    } catch (e) {}
    setCoachLoading(false);
  };

  const submitRebuttal = async () => {
    if (!manualText || !challengingAgentId || !challengingAgentClaim) return;
    const text = manualText;
    setIsRebutting(true);
    setManualText("");
    try {
      const res = await fetch(`${API_BASE}/conversation/rebuttal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
           session_id: sessionId,
           agent_id: challengingAgentId,
           agent_claim: challengingAgentClaim,
           rebuttal_text: text,
           provider
        })
      });
      const data = await res.json();
      updateAgentState(challengingAgentId, `\n\n💬 Reply: ${data.agent_response}`, "done");
      enqueueSpeech(challengingAgentId, data.agent_response);
      setConversation((prev: ConversationTurn[]) => [
        ...prev, 
        { type: "pitcher_interrupt", agent_name: pitcherId || "Alex Chen", content: text },
        { type: "persona_response", agent_name: data.name || challengingAgentId, content: data.agent_response }
      ]);
    } catch(e) {} finally {
      setIsRebutting(false);
    }
  };

  const handleChallenge = (agentId: string, claim: string) => {
    setChallengingAgentId(agentId);
    setChallengingAgentClaim(claim);
    setManualText("");
  };

  return (
    <div className="flex h-screen overflow-hidden bg-surface text-on-surface">
      <Sidebar 
        onNewPitch={handleNewPitch} 
        onViewChange={(v) => setView(v)}
        currentView={view}
      />

      <main className="flex-1 flex flex-col min-w-0 h-full relative">
        <Header 
          provider={provider} 
          setProvider={setProvider} 
          disabled={stage !== "idle" && stage !== "pitching"} 
        />

        <div className="bg-gradient-to-b from-surface-container-low to-transparent h-px w-full"></div>

        <div className="flex-1 overflow-hidden h-full relative">
          {view === "library" ? (
            <div className="p-16 max-w-[1600px] mx-auto w-full space-y-16 duration-700 h-full overflow-y-auto custom-scrollbar">
              <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-10">
                <div className="space-y-4">
                  <h2 className="text-6xl font-extrabold text-on-surface font-headline tracking-tighter leading-none">Resource Library</h2>
                  <p className="text-slate-400 font-medium text-xl max-w-2xl leading-relaxed">Access your pitch decks and research materials analyzed by the Digital Athenaeum.</p>
                </div>
                <div className="flex bg-surface-container-high p-1.5 rounded-2xl border border-outline-variant/10 shadow-sm">
                   {["All Files", "Recent"].map((tab, i) => (
                     <button key={tab} className={`px-8 py-3 rounded-xl text-[11px] font-bold uppercase tracking-widest transition-all ${i === 0 ? 'bg-primary text-white shadow-lg' : 'text-slate-400 hover:text-slate-600'}`}>
                       {tab}
                     </button>
                   ))}
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-12">
                <div className="md:col-span-3 flex flex-col gap-10">
                  <div className="bg-surface-container rounded-[2.5rem] p-10 border border-outline-variant/10 shadow-xl shadow-slate-200/20 text-center group cursor-pointer hover:border-primary/40 transition-all">
                    <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-8 group-hover:scale-110 transition-transform">
                       <span className="material-symbols-outlined text-4xl text-primary">upload_file</span>
                    </div>
                    <h3 className="text-2xl font-extrabold text-on-surface tracking-tight mb-3">Ingest Material</h3>
                    <p className="text-[11px] text-slate-400 font-bold uppercase tracking-[0.1em] mb-10 leading-relaxed px-4">PDF, PPTX, or Research Links.</p>
                    <button className="w-full bg-primary/5 py-4 rounded-full text-primary text-[11px] font-bold uppercase tracking-widest border border-primary/20 hover:bg-primary hover:text-white transition-all">Select Files</button>
                  </div>
                </div>
                <div className="md:col-span-9 space-y-16 pb-32">
                    <div className="space-y-8">
                       <div className="flex items-center justify-between">
                          <h3 className="text-2xl font-extrabold text-on-surface tracking-tight">Marketing & Brand</h3>
                          <button className="text-[11px] font-bold text-primary uppercase tracking-widest hover:underline">View All</button>
                       </div>
                       <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
                          {[
                             { title: "Brand Equity Analysis 2024", time: "Last used 2h ago", type: "PDF" },
                             { title: "Q3 Marketing Strategy", time: "Uploaded Sep 12", type: "PPTX" }
                          ].map((file, i) => (
                             <div key={i} className="bg-surface-container border border-outline-variant/10 rounded-[2rem] p-4 flex flex-col gap-6 group hover:shadow-2xl transition-all duration-500">
                                <div className="h-48 bg-surface-container-high rounded-[1.5rem] relative flex items-center justify-center">
                                   <span className="material-symbols-outlined text-6xl text-slate-200">description</span>
                                   <div className="absolute top-4 right-4 bg-white text-primary text-[10px] font-bold px-3 py-1 rounded-full">{file.type}</div>
                                </div>
                                <div className="px-4 pb-4">
                                   <h4 className="font-extrabold text-on-surface text-base truncate mb-2">{file.title}</h4>
                                   <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">{file.time}</p>
                                </div>
                             </div>
                          ))}
                       </div>
                    </div>
                </div>
              </div>
            </div>
          ) : view === "transcripts" ? (
            <div className="flex h-full overflow-hidden duration-500">
              <aside className="w-[450px] flex flex-col bg-slate-50 border-r border-slate-100 shadow-lg z-20">
                <div className="p-10 border-b border-slate-100 space-y-8 bg-white/50">
                  <h2 className="text-3xl font-black text-slate-800 tracking-tight font-headline">Session History</h2>
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-slate-300">search</span>
                    <input placeholder="Search archives..." className="w-full bg-slate-100/50 border border-slate-200/20 rounded-2xl py-4 pl-12 pr-6 text-sm font-medium focus:bg-white transition-all outline-none" />
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
                  {/* Current Active Session */}
                  {conversation.length > 0 && (
                    <div className="p-8 rounded-[2.5rem] border-2 border-[#006948] bg-emerald-50/30 shadow-xl shadow-emerald-900/5 cursor-pointer transition-all">
                       <div className="flex justify-between items-start mb-4">
                          <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-widest px-3 py-1 bg-emerald-100 rounded-full">Active Session</span>
                          <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest">Just now</span>
                       </div>
                       <h4 className="font-black text-xl tracking-tight mb-2 text-slate-800 line-clamp-1">{pitcherId || "New Pitch"} Analysis</h4>
                       <p className="text-xs text-slate-400 font-medium leading-relaxed line-clamp-2">Currently synthesizing {conversation.length} debate turns.</p>
                    </div>
                  )}
                  
                  {[
                    { title: "Venture Capital Strategy", date: "OCT 24, 2023", sub: "Discussion on Series A funding rounds for SaaS.", id: "1" },
                    { title: "Brand Identity Audit", date: "OCT 22, 2023", sub: "Evaluating visual language and tone of voice.", id: "2" }
                  ].map((s, i) => (
                    <div key={i} className="p-8 rounded-[2.5rem] border border-slate-100 bg-white hover:border-emerald-200 hover:shadow-xl transition-all cursor-pointer group">
                       <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest block mb-4 group-hover:text-emerald-400">{s.date}</span>
                       <h4 className="font-black text-xl tracking-tight mb-2 text-slate-800">{s.title}</h4>
                       <p className="text-xs text-slate-400 font-medium leading-relaxed line-clamp-2">{s.sub}</p>
                    </div>
                  ))}
                </div>
              </aside>

              <div className="flex-1 flex flex-col h-full bg-white relative overflow-hidden">
                 <div className="flex-1 overflow-y-auto p-16 space-y-12 custom-scrollbar">
                    <div className="max-w-4xl mx-auto space-y-16 pb-32">
                       <h1 className="text-6xl font-black text-slate-800 tracking-tight font-headline leading-none">
                         {stage === "conversation" ? `${pitcherId || "Alex Chen"}'s Pitch Analysis` : "Transcript Archive"}
                       </h1>
                       <div className="space-y-12">
                          {conversation.length === 0 ? (
                             <div className="h-96 flex flex-col items-center justify-center space-y-6 opacity-30 text-center">
                                <span className="material-symbols-outlined text-8xl text-slate-200">contract_edit</span>
                                <p className="text-xl font-bold text-slate-300 uppercase tracking-widest">No active turns detected</p>
                             </div>
                          ) : (
                             conversation.map((turn, i) => (
                                <div key={i} className="flex gap-8 transition-all duration-700">
                                   <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 border ${turn.type === "pitcher_response" ? "bg-emerald-50 border-emerald-100 text-[#006948]" : "bg-slate-50 border-slate-100 text-slate-400"}`}>
                                      <span className="material-symbols-outlined text-2xl">
                                        {turn.type === "pitcher_response" ? "person" : "bolt"}
                                      </span>
                                   </div>
                                   <div className={`flex-1 p-10 rounded-[3rem] rounded-tl-none border shadow-sm ${turn.type === "pitcher_response" ? "bg-emerald-50/30 border-emerald-100" : "bg-slate-50/50 border-slate-100"} space-y-4`}>
                                      <div className="flex justify-between items-center">
                                         <h4 className="text-xl font-black text-slate-800 tracking-tight uppercase text-xs tracking-[0.2em]">{turn.agent_name}</h4>
                                         <span className="text-[11px] font-bold text-slate-300 uppercase tracking-widest">14:22 PM</span>
                                      </div>
                                      <p className={`text-slate-600 leading-relaxed text-lg font-medium opacity-90 ${turn.type === "pitcher_response" ? "italic" : ""}`}>{turn.content}</p>
                                   </div>
                                </div>
                             ))
                          )}
                       </div>
                    </div>
                 </div>
                 <div className="absolute bottom-8 left-16 right-16 z-30">
                    <div className="max-w-4xl mx-auto relative group">
                       <span className="material-symbols-outlined absolute left-6 top-1/2 -translate-y-1/2 text-primary">search</span>
                       <input placeholder="Search this transcript..." className="w-full bg-surface-container py-6 pl-16 pr-12 rounded-[2rem] border border-outline-variant/10 shadow-2xl text-sm font-medium" />
                    </div>
                 </div>
              </div>
            </div>
          ) : view === "analytics" ? (
            <div className="p-16 max-w-[1600px] mx-auto w-full space-y-10 duration-700 h-full overflow-y-auto custom-scrollbar">
              {/* Header */}
              <div className="flex items-center justify-between">
                <div className="space-y-2">
                  <h2 className="text-5xl font-black text-slate-800 tracking-tight leading-none font-headline">Agent Execution Graph</h2>
                  <p className="text-slate-400 font-medium text-lg max-w-2xl leading-relaxed">
                    Real-time visualization of the LangGraph node execution flow.
                  </p>
                  {sessionId && (
                    <p className="text-xs text-slate-300 font-mono mt-1">session: {sessionId}</p>
                  )}
                </div>
                <div className="flex items-center gap-3 bg-white border border-slate-100 rounded-2xl px-5 py-3 shadow-sm">
                  <div className={`w-2.5 h-2.5 rounded-full ${debugStream.isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
                  <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">
                    {debugStream.isConnected ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
              </div>

              {/* No session warning */}
              {!sessionId && (
                <div className="p-5 bg-amber-50 border border-amber-200 rounded-2xl text-sm text-amber-800 font-medium">
                  No active session. Start a pitch from the Panel tab to see live execution data here.
                </div>
              )}

              {/* Current active node banner */}
              {debugStream.currentNode && (
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-2xl flex items-center gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-blue-500" style={{ animation: 'pulse 1.5s infinite' }} />
                  <span className="text-sm text-blue-700 font-semibold">
                    Active: <span className="font-bold">{debugStream.currentNode}</span>
                    {debugStream.executions.length > 0 && debugStream.executions[debugStream.executions.length - 1].action && (
                      <span className="text-blue-400 ml-2">
                        → {debugStream.executions[debugStream.executions.length - 1].action}
                        {debugStream.executions[debugStream.executions.length - 1].target && ` (${debugStream.executions[debugStream.executions.length - 1].target})`}
                      </span>
                    )}
                  </span>
                </div>
              )}

              {/* Flow Timeline */}
              <div className="bg-white border border-slate-100 rounded-[2rem] p-8 shadow-sm">
                <p className="text-[11px] font-bold text-slate-400 uppercase tracking-[0.15em] mb-4">Flow Timeline</p>
                <FlowTimeline executions={debugStream.executions} currentNode={debugStream.currentNode} />
              </div>

              {/* 2-column layout */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                {/* Execution History */}
                <div className="lg:col-span-8">
                  <div className="bg-white border border-slate-100 rounded-[2rem] p-8 shadow-sm">
                    <p className="text-[11px] font-bold text-slate-400 uppercase tracking-[0.15em] mb-4">
                      Execution History ({debugStream.executions.length} steps)
                    </p>
                    <div style={{ maxHeight: '560px', overflowY: 'auto', paddingRight: '4px' }}>
                      {debugStream.executions.length === 0 ? (
                        <div className="h-64 flex flex-col items-center justify-center text-slate-300 border border-dashed border-slate-200 rounded-2xl">
                          <span className="material-symbols-outlined text-5xl mb-3">timeline</span>
                          <p className="text-sm font-medium">Waiting for first node execution...</p>
                        </div>
                      ) : (
                        debugStream.executions.map((ex, i) => (
                          <NodeCard
                            key={ex.id}
                            execution={ex}
                            isActive={i === debugStream.executions.length - 1 && !debugStream.isComplete}
                            index={i}
                          />
                        ))
                      )}
                      <div ref={analyticsListEndRef} />
                    </div>
                  </div>
                </div>

                {/* Sidebar: Memory + Stats */}
                <div className="lg:col-span-4 space-y-6" style={{ position: 'sticky', top: '24px' }}>
                  <MemoryPanel
                    memory={debugStream.memorySnapshot}
                    totalTurns={debugStream.totalTurns}
                    isComplete={debugStream.isComplete}
                  />

                  {debugStream.executions.length > 0 && (
                    <div className="bg-white border border-slate-100 rounded-xl p-5">
                      <p className="text-[11px] font-bold text-slate-400 uppercase tracking-[0.15em] mb-3">Node Breakdown</p>
                      {Object.entries(
                        debugStream.executions.reduce((acc, ex) => {
                          acc[ex.node] = (acc[ex.node] ?? 0) + 1;
                          return acc;
                        }, {} as Record<string, number>)
                      )
                        .sort((a, b) => b[1] - a[1])
                        .map(([node, count]) => (
                          <div key={node} className="flex justify-between text-xs text-slate-600 mb-1">
                            <span>{node}</span>
                            <span className="font-bold">×{count}</span>
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              </div>

              <style>{`
                @keyframes pulse {
                  0%, 100% { opacity: 1; }
                  50% { opacity: 0.4; }
                }
              `}</style>
            </div>
          ) : (
            <div className="h-full flex flex-col overflow-hidden">
               {stage === "idle" || stage === "pitching" ? (
                  <div className="h-full flex flex-col items-center justify-start py-20 px-6 space-y-12 animate-in fade-in slide-in-from-bottom-5 duration-1000 overflow-y-auto custom-scrollbar">
                    <div className="text-center space-y-4">
                      <h1 className="text-6xl font-black text-slate-800 tracking-tight leading-none">Initialize New Pitch</h1>
                      <p className="text-slate-400 font-medium text-xl max-w-xl mx-auto leading-relaxed">Configure your environment and summon the panel of experts.</p>
                    </div>

                    <div className="w-full max-w-4xl bg-white border border-slate-100 rounded-[3rem] shadow-[0_40px_100px_rgba(0,0,0,0.06)] p-20 space-y-12">
                      <div className="space-y-12">
                        <div className="space-y-4">
                          <label className="text-[11px] font-bold text-[#006948] uppercase tracking-[0.2em] ml-2">Your Name (Optional)</label>
                          <input 
                            value={pitcherId} 
                            onChange={(e) => setPitcherId(e.target.value)} 
                            placeholder="Identity of the pitcher..." 
                            className="w-full bg-slate-50/50 border border-slate-100/50 rounded-2xl py-6 px-10 text-slate-900 text-lg placeholder:text-slate-300 focus:bg-white focus:ring-2 focus:ring-[#006948]/10 transition-all outline-none" 
                          />
                        </div>

                        <div className="space-y-4 relative">
                          <label className="text-[11px] font-bold text-[#006948] uppercase tracking-[0.2em] ml-2">Select Panel Configuration</label>
                          <select 
                            value={difficulty} 
                            onChange={(e) => setDifficulty(e.target.value)} 
                            className="w-full bg-slate-50/50 border border-slate-100/50 rounded-2xl py-6 px-10 text-slate-900 text-lg appearance-none cursor-pointer focus:bg-white focus:ring-2 focus:ring-[#006948]/10 transition-all outline-none"
                          >
                            <option value="gentle">Gentle — supportive panel</option>
                            <option value="standard">Standard — balanced panel</option>
                            <option value="brutal">Brutal — no mercy</option>
                          </select>
                          <span className="material-symbols-outlined absolute right-8 bottom-6 text-slate-300 pointer-events-none">expand_more</span>
                        </div>

                        <div className="space-y-4">
                          <label className="text-[11px] font-bold text-[#006948] uppercase tracking-[0.2em] ml-2">What would you like to pitch?</label>
                          <textarea 
                            value={manualText} 
                            onChange={(e) => setManualText(e.target.value)} 
                            className="w-full bg-slate-50/50 border border-slate-100/50 rounded-[2rem] py-8 px-10 text-slate-900 text-lg h-64 resize-none outline-none custom-scrollbar placeholder:text-slate-300 focus:bg-white focus:ring-2 focus:ring-[#006948]/10 transition-all" 
                            placeholder="e.g., a multiplayer game connecting players through shared emotional states and biometric feedback loops..." 
                          />
                        </div>
                      </div>

                      <div className="flex items-center gap-6 pt-10">
                         <button 
                            onClick={isRecording ? stopRecording : startRecording}
                            className={`flex-[0.3] py-6 px-8 rounded-full flex items-center justify-center gap-3 font-bold transition-all shadow-xl shadow-slate-200/40 ${
                              isRecording ? 'bg-rose-500 text-white animate-pulse' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                            }`}
                         >
                           <span className="material-symbols-outlined text-2xl">{isRecording ? 'stop_circle' : 'mic'}</span>
                           <span className="text-base uppercase tracking-widest">{isRecording ? 'Stop' : 'Speak'}</span>
                         </button>

                         <button 
                            onClick={finishPitch} 
                            disabled={!sessionId || !manualText}
                            className="flex-1 py-7 bg-[#006948] text-white font-extrabold text-2xl rounded-full shadow-2xl shadow-emerald-900/20 hover:scale-[1.02] active:scale-[0.98] transition-all flex items-center justify-center gap-4 uppercase tracking-tighter disabled:opacity-50"
                         >
                           Start Debate
                           <span className="material-symbols-outlined text-2xl">rocket_launch</span>
                         </button>
                      </div>
                    </div>
                  </div>
               ) : stage === "hitl_summary" && hitlData ? (
                  <div className="h-full flex flex-col items-center justify-center p-6 animate-in fade-in duration-700">
                    <div className="w-full max-w-2xl bg-white rounded-[32px] p-10 border border-slate-200/20 shadow-2xl text-center space-y-8">
                       <h2 className="text-3xl font-extrabold text-on-surface font-headline tracking-tighter uppercase">Confirm Intelligence</h2>
                       <textarea value={hitlData.summary} onChange={(e) => setHitlData({ ...hitlData, summary: e.target.value })} className="w-full bg-surface-container-low border-none rounded-2xl p-6 text-on-surface text-base outline-none h-48 resize-none leading-relaxed" />
                       <button onClick={approveSummary} className="w-full py-5 bg-[#006948] text-white font-headline font-extrabold text-xl rounded-2xl shadow-xl hover:scale-[1.01] transition-all uppercase tracking-tighter">Enter the Arena</button>
                    </div>
                  </div>
               ) : stage === "conversation" ? (
                  <div className="h-full flex px-12 pb-12 pt-6 overflow-hidden gap-12 animate-in fade-in duration-700">
                    <div className="flex-[0.8] overflow-y-auto pr-6 custom-scrollbar pb-12">
                      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                         {Object.entries(panelState).map(([id, agent]) => (
                            <AgentCard key={id} id={id} name={agent.name} role={agent.role} status={agent.status} text={agent.text} avatarUrl={agent.avatarUrl} isChallenged={challengingAgentId === id} />
                         ))}
                      </div>
                    </div>
                    <div className="flex-1 flex flex-col h-full bg-white border border-slate-100 rounded-[3rem] shadow-[0_20px_50px_rgba(0,0,0,0.04)] overflow-hidden">
                       <LiveFeed 
                          turns={conversation} 
                          agents={Object.values(panelState)} 
                          onJumpIn={handleInterrupt} 
                          isRecording={isRecording}
                          awaitingUserInput={awaitingUserInput}
                          userInput={manualText}
                          onUserInputChange={(val) => setManualText(val)}
                          onSendAnswer={submitAnswer}
                          currentQuestion={currentQuestion}
                          isAnsweringInterrupt={isAnsweringInterrupt}
                          isStreaming={isStreaming}
                          activeAgent={activeAgent}
                          onSetAwaitingUserInput={setAwaitingUserInput}
                        />
                    </div>
                  </div>
               ) : stage === "verdict" && verdictData ? (
                 <div className="p-12 max-w-4xl mx-auto w-full space-y-8 duration-800 overflow-y-auto custom-scrollbar">
                    <VerdictCard verdict={verdictData} sessionId={sessionId} onClose={() => setShowVerdictModal(false)} />
                 </div>
               ) : null}
            </div>
          )}
        </div>

        {/* Floating Actions */}
        {stage === "conversation" && (
           <div className="fixed bottom-12 left-1/2 -translate-x-1/2 lg:left-[calc(50%+144px)] z-50 flex items-center gap-6 duration-700">
              <button 
                onClick={endConversation} 
                className="w-16 h-16 rounded-full bg-white border border-slate-100 shadow-2xl text-slate-300 hover:text-rose-500 hover:border-rose-100 transition-all flex items-center justify-center group"
                title="End Debate"
              >
                <span className="material-symbols-outlined text-3xl group-hover:scale-110 transition-transform">stop_circle</span>
              </button>

              {/* Answer UI now handled inside LiveFeed */}
           </div>
        )}

        {challengingAgentId && (
          <div className="fixed inset-0 bg-background/80 backdrop-blur-md z-[60] flex items-center justify-center p-6 animate-in fade-in">
            <div className="max-w-3xl w-full bg-white rounded-[3rem] p-12 shadow-[0_40px_80px_rgba(0,0,0,0.1)] border border-primary/10">
              <div className="flex justify-between items-start mb-8">
                <h3 className="text-primary font-black uppercase text-xs tracking-widest flex items-center gap-2">Addressing: {challengingAgentId}</h3>
                <button onClick={() => setChallengingAgentId(null)} className="text-slate-300 hover:text-on-surface">
                  <span className="material-symbols-outlined">close</span>
                </button>
              </div>
              <blockquote className="text-3xl font-headline font-bold text-on-surface mb-10 pl-8 border-l-8 border-primary/20 leading-tight">"{challengingAgentClaim}"</blockquote>
              <textarea value={manualText} onChange={(e) => setManualText(e.target.value)} className="w-full bg-slate-50 p-8 rounded-[2rem] text-on-surface text-xl mb-10 outline-none h-48 focus:ring-2 focus:ring-primary/10 transition-all resize-none" placeholder="Defend your thesis..." />
              <div className="flex justify-end gap-6">
                 <button onClick={() => setChallengingAgentId(null)} className="px-8 py-4 font-bold text-slate-400 uppercase tracking-widest">Cancel</button>
                 <button onClick={submitRebuttal} disabled={isRebutting || !manualText} className="px-12 py-5 rounded-full primary-gradient text-white font-black text-xl hover:scale-105 transition-all">Submit Rebuttal</button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
