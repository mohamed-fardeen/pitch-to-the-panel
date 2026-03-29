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
  
  const [verdictData, setVerdictData] = useState<string | null>(null);
  const [domainData, setDomainData] = useState<any>(null);
  const [hitlData, setHitlData] = useState<any>(null);
  const [sessionId, setSessionId] = useState("");
  const [pitcherId, setPitcherId] = useState("");
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

  useEffect(() => {
    if (view === "library") {
      fetchLibrary();
    }
  }, [view]);

  const handleNewPitch = () => {
    setStage("idle");
    setSessionId(`session_${Math.random().toString(36).substr(2, 9)}`);
    setLogs([]);
    setConversation([]);
    setPanelState({});
    setVerdictData(null);
    setShowVerdictModal(false);
    setView("panel");
  };

  const startPitch = () => {
    setStage("pitching");
    setManualText("");
    setSessionId(Math.random().toString(36).substring(2, 10));
    setConversation([]);
    setPanelState({});
    setShowVerdictModal(false);
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

    const eventSource = new window.EventSource(url.toString());

    eventSource.addEventListener("hitl_summary_approval", (e: any) => {
      const data = JSON.parse(e.data);
      setHitlData(data);
      setStage("hitl_summary");
      setConversation([{
        type: "answer",
        agent_name: pitcherId || "Alex Chen",
        content: currentPitch
      }]);
    });

    eventSource.addEventListener("echochamber_start", (e: any) => {
      const data = JSON.parse(e.data);
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

    eventSource.addEventListener("agent_turn", (e: any) => {
      const data = JSON.parse(e.data);
      setCurrentAgentId(data.agent_id);
      
      if (data.token) {
        updateAgentState(data.agent_id, data.token, "streaming");
      } else if (data.content) {
        updateAgentState(data.agent_id, data.content, "done", true);
        enqueueSpeech(data.agent_id, data.content);
        
        setConversation((prev: ConversationTurn[]) => [...prev, {
          type: data.turn_type || "persona_response",
          agent_id: data.agent_id,
          agent_name: data.name || data.agent_id,
          content: data.content
        }]);
      }
    });

    eventSource.addEventListener("waiting_for_pitcher", (e: any) => {
      const data = JSON.parse(e.data);
      setWaitingForAnswer(true);
      setCurrentQuestion(data.question);
      setManualText("");
    });

    eventSource.addEventListener("black_swan_report", (e: any) => {
      const data = JSON.parse(e.data);
      setVerdictData(data.report);
      setStage("verdict");
      setShowVerdictModal(true);
    });

    eventSource.addEventListener("error", (e: any) => {
      eventSource.close();
    });
  };

  const approveSummary = async () => {
    if (!hitlData) return;
    setStage("conversation");
    try {
      await fetch(`${API_BASE}/hitl/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: hitlData.session_id,
          approved: true,
          corrected_summary: hitlData.summary
        })
      });
    } catch(e) {}
  };

  const submitAnswer = async () => {
    if (!manualText) return;
    const ans = manualText;
    setWaitingForAnswer(false);
    setIsAnsweringInterrupt(false);
    
    try {
      await fetch(`${API_BASE}/conversation/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: ans
        })
      });
      
      setConversation((prev: ConversationTurn[]) => [...prev, {
        type: "pitcher_response",
        agent_name: pitcherId || "Alex Chen",
        content: ans
      }]);
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
            <div className="p-16 max-w-[1600px] mx-auto w-full space-y-16 duration-700 h-full overflow-y-auto custom-scrollbar">
              <div className="space-y-4">
                <h2 className="text-6xl font-black text-slate-800 tracking-tight leading-none">Market Intel Analysis</h2>
                <p className="text-slate-400 font-medium text-xl max-w-2xl leading-relaxed">Synthesis of panel insights against global market trends and adversarial threats.</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-12 gap-12 pt-10">
                 <div className="md:col-span-8 bg-white border border-slate-100 rounded-[3rem] p-12 shadow-xl shadow-slate-200/20">
                    <div className="flex items-center justify-between mb-12">
                       <h3 className="text-2xl font-bold text-slate-800 tracking-tight">Vulnerability Heatmap</h3>
                       <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full uppercase tracking-widest">Active Model</span>
                    </div>
                    <div className="h-96 w-full bg-slate-50/50 rounded-[2rem] flex items-center justify-center border border-dashed border-slate-200">
                       <p className="text-slate-300 font-medium">Aggregating real-time debate vectors...</p>
                    </div>
                 </div>
                 <div className="md:col-span-4 space-y-12">
                    <div className="bg-[#0d1c2e] rounded-[3rem] p-12 text-white shadow-2xl shadow-emerald-950/20">
                       <h3 className="text-xl font-bold mb-6 tracking-tight">Panel Sentiment</h3>
                       <div className="space-y-6">
                          {['Strategic Fit', 'Technical Feasibility', 'Market Viability'].map(metric => (
                             <div key={metric} className="space-y-2">
                                <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest opacity-60">
                                   <span>{metric}</span>
                                   <span>85%</span>
                                </div>
                                <div className="h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
                                   <div className="h-full bg-emerald-400 w-[85%]" />
                                </div>
                             </div>
                          ))}
                       </div>
                    </div>
                 </div>
              </div>
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
                            <option value="standard">Standard Panel (4 Strategic Agents)</option>
                            <option value="adversarial">Adversarial (High Scrutiny Focus)</option>
                            <option value="consensus">Consensus (Balanced Growth Panel)</option>
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
                            className="flex-1 py-7 bg-[#006948] text-white font-extrabold text-2xl rounded-full shadow-2xl shadow-emerald-900/20 hover:scale-[1.02] active:scale-[0.98] transition-all flex items-center justify-center gap-4 uppercase tracking-tighter"
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
                       <LiveFeed turns={conversation} agents={Object.values(panelState)} onJumpIn={handleInterrupt} isRecording={isRecording} />
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

              {waitingForAnswer && (
                <div className="bg-white/95 backdrop-blur-md rounded-[2.5rem] p-4 shadow-[0_40px_80px_rgba(0,0,0,0.12)] border border-slate-100 flex items-center gap-4 w-[650px] duration-500 ring-8 ring-slate-900/[0.02]">
                  <textarea 
                    value={manualText} 
                    onChange={(e) => setManualText(e.target.value)} 
                    onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), submitAnswer())} 
                    className="flex-1 bg-slate-50 border-none rounded-[1.5rem] py-5 px-8 text-slate-800 placeholder:text-slate-300 focus:bg-white focus:ring-2 focus:ring-[#006948]/10 transition-all outline-none resize-none h-20 text-base font-medium" 
                    placeholder={isAnsweringInterrupt ? "What is your counter-argument?..." : "Respond to the panel..."} 
                    autoFocus
                  />
                  <button 
                    onClick={submitAnswer} 
                    disabled={!manualText} 
                    className="w-20 h-20 rounded-full bg-[#006948] hover:bg-[#005a3e] text-white flex items-center justify-center shadow-2xl shadow-emerald-950/20 disabled:opacity-30 disabled:grayscale transition-all active:scale-95 group"
                  >
                    <span className="material-symbols-outlined text-3xl group-hover:translate-x-0.5 transition-transform">send</span>
                  </button>
                </div>
              )}
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
