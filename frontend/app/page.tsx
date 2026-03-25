"use client";

import React, { useState, useEffect, useRef } from "react";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useAgentVoice } from "../hooks/useAgentVoice";
import { PanelState, AgentStatus, AgentRole, ConversationTurn } from "../types/v2_types";
import { Sidebar } from "../components/Sidebar";
import { Header } from "../components/Header";
import { LiveFeed } from "../components/LiveFeed";
import { PanelGrid } from "../components/PanelGrid";
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
  const needsSkipApprovalRef = useRef(false);

  const [isInterrupting, setIsInterrupting] = useState(false);
  const [isAnsweringInterrupt, setIsAnsweringInterrupt] = useState(false);
  const isInterruptingRef = useRef(false);
  const [activeHosts, setActiveHosts] = useState<{host_a: any, host_b: any} | null>(null);

  const audioQueueRef = useRef<{role: AgentRole, text: string}[]>([]);
  const isPlayingRef = useRef(false);
  const challengingAgentIdRef = useRef<string | null>(null);
  const flowLockRef = useRef(false);
 
  const summonableAgents = [
    { name: "The Disruptor", role: "critic", icon: "bolt", color: "text-amber-400" },
    { name: "The Financialist", role: "critic", icon: "payments", color: "text-emerald-400" },
    { name: "The Visionary", role: "host", icon: "visibility", color: "text-primary" },
    { name: "The Guardian", role: "observer", icon: "shield", color: "text-rose-400" },
  ];

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
    setStage("idle"); // Changed from "setup" to "idle" to match existing stage type
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
    setRetryCounts({});
    setShowVerdictModal(false);
    addLog("Ready. Speak or type your pitch...");
  };

  const finishPitch = async () => {
    stopRecording();
    const currentPitch = manualText;
    addLog("Starting evaluation panel...");

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
      addLog("Review your pitch summary.");
      
      // Add initial pitch to conversation
      setConversation([{
        type: "answer",
        agent_name: pitcherId || "Alex Chen",
        content: currentPitch
      }]);
    });

    eventSource.addEventListener("status", (e: any) => {
      const data = JSON.parse(e.data);
      addLog(data.message);
    });

    eventSource.addEventListener("hosts_selected", (e: any) => {
      const data = JSON.parse(e.data);
      setActiveHosts({ host_a: data.host_a, host_b: data.host_b });
      if (data.observers) {
        const initialState: PanelState = {};
        // Add hosts
        initialState[data.host_a.agent_id] = { text: "", status: "idle", role: "host", name: data.host_a.name };
        initialState[data.host_b.agent_id] = { text: "", status: "idle", role: "host", name: data.host_b.name };
        // Add observers
        data.observers.forEach((obs: any) => {
          initialState[obs.agent_id] = { text: "", status: "idle", role: "observer", name: obs.name };
        });
        setPanelState(initialState);
      }
      addLog(`Hosts: ${data.host_a.name} & ${data.host_b.name}`);
    });

    eventSource.addEventListener("domain_classified", (e: any) => {
      const data = JSON.parse(e.data);
      setDomainData(data);
      if (data.active_panel) {
        const initialState: PanelState = {};
        data.active_panel.forEach((id: string) => {
          initialState[id] = { text: "", status: "idle", role: "critic", name: id };
        });
        setPanelState(initialState);
      }
      addLog(`Domain: ${data.sub_domain}`);
    });

    eventSource.addEventListener("agent_utterance_start", (e: any) => {
      const data = JSON.parse(e.data);
      setCurrentAgentId(data.agent_id);
      updateAgentState(data.agent_id, "", "streaming", true);
    });

    eventSource.addEventListener("agent_token", (e: any) => {
      const data = JSON.parse(e.data);
      if (
        data.type === "host_utterance" ||
        data.type === "observer_utterance" ||
        data.type === "interrupt_ack"
      ) {
        updateAgentState(data.agent_id, data.token, "streaming");
      }
    });

    eventSource.addEventListener("agent_utterance_done", (e: any) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent_id, "", "done");
      
      if (isInterruptingRef.current && data.type !== "interrupt_ack") {
        // Drop the partial interrupted speech to prevent TTS engine crash
        // and avoid speaking it when the user just interrupted.
        console.log("Dropped interrupted speech:", data.content);
      } else {
        enqueueSpeech(data.agent_id, data.content);
      }
      
      // Update transcript only if it's not the partial interrupted speech
      if (!(isInterruptingRef.current && data.type !== "interrupt_ack")) {
        setConversation((prev: ConversationTurn[]) => [...prev, {
          type: data.type === "observer" ? "observer_utterance" : "host_utterance",
          agent_id: data.agent_id,
          agent_name: data.name || data.agent_id,
          content: data.content
        }]);
      }

      // If the host just acknowledged a pitcher interrupt, show the pitcher input
      if (data.type === "interrupt_ack") {
        setWaitingForAnswer(true);
        setCurrentQuestion("Go ahead — what did you want to say?");
        setManualText("");
        setIsAnsweringInterrupt(true);
        setIsInterrupting(false);
        isInterruptingRef.current = false;
      }
    });

    const triggerWaitingForAnswer = (data: any) => {
      setWaitingForAnswer(true);
      setCurrentQuestion(data.question);
      setCurrentAgentId(data.agent_id);
      setManualText("");
      setCoachHints(null);
      setWeakAnswerDetected(false);
      addLog(`Waiting for your answer to ${data.agent_name}...`);
    };

    eventSource.addEventListener("waiting_for_answer", (e: any) => {
      const data = JSON.parse(e.data);
      setWaitingForAnswer(true);
      setCurrentQuestion(data.question);
      setCurrentAgentId(data.agent_id);
      setIsAnsweringInterrupt(false);
      setManualText("");
      addLog(`The panel is waiting for your answer...`);
    });

    eventSource.addEventListener("waiting_for_pitcher_interrupt", (e: any) => {
      // No-op: we now show the input AFTER the interrupt_ack done event fires
      // This event is kept for backend compatibility only
    });

    eventSource.addEventListener("pitcher_interrupted", (e: any) => {
      const data = JSON.parse(e.data);
      setWaitingForAnswer(false);
      setChallengingAgentId(null);
      addLog("Your interruption was heard.");
    });

    eventSource.addEventListener("agent_reaction_start", (e: any) => {
      const data = JSON.parse(e.data);
      const checkAndReact = () => {
        if (window.speechSynthesis.speaking || challengingAgentIdRef.current || needsSkipApprovalRef.current || flowLockRef.current) {
          setTimeout(checkAndReact, 500);
        } else {
          updateAgentState(data.agent_id, "\n\nReaction: ", "streaming");
        }
      };
      checkAndReact();
    });

    eventSource.addEventListener("agent_reaction_done", (e: any) => {
      const data = JSON.parse(e.data);
      
      // If this is a placeholder for a turn handled via Challenge Mode, just move on
      if (data.reaction === "[Interaction Complete]") {
          flowLockRef.current = false;
          setNeedsSkipApproval(false);
          needsSkipApprovalRef.current = false;
          return;
      }

      updateAgentState(data.agent_id, "", "done");
      enqueueSpeech(data.agent_id, data.reaction);
      
      // LOCK Flow Instantly to prevent next agent from starting
      flowLockRef.current = true;
      
      const checkAndSetSkip = () => {
        if (window.speechSynthesis.speaking || audioQueueRef.current.length > 0) {
            // Wait for reaction speech to finish
            setTimeout(checkAndSetSkip, 500);
        } else {
           setNeedsSkipApproval(true);
           needsSkipApprovalRef.current = true;
           setChallengingAgentId(data.agent_id);
           setChallengingAgentClaim(data.reaction);
           // flowLock remains true until user chooses Skip or Challenge
        }
      };
      checkAndSetSkip();
    });

    eventSource.addEventListener("interrupt_start", (e: any) => {
      const data = JSON.parse(e.data);
      const checkAndInterrupt = () => {
        if (window.speechSynthesis.speaking || challengingAgentIdRef.current) {
          setTimeout(checkAndInterrupt, 500);
        } else {
          updateAgentState(data.agent_id, `\n\n[INTERRUPT]: ${data.question}`, "done");
          enqueueSpeech(data.agent_id, data.question);
          addLog(`${data.name} jumped in!`);
        }
      };
      checkAndInterrupt();
    });

    eventSource.addEventListener("conversation_complete", (e: any) => {
      addLog("Conversation complete. Final verdict incoming...");
    });

    eventSource.addEventListener("verdict_complete", (e: any) => {
      const data = JSON.parse(e.data);
      setVerdictData(data.verdict);
      setShowVerdictModal(true);
      setStage("verdict");
      enqueueSpeech("judge", data.verdict);
      
      // Update Radar
      fetch(`${API_BASE}/pitch/score`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, provider })
      }).then(r => r.json()).then(d => { if(d.image) setRadarChart(d.image); });
    });

    eventSource.addEventListener("error", (e: any) => {
      console.error("SSE Error", e);
      eventSource.close();
    });
  };

  const approveSummary = async () => {
    if (!hitlData) return;
    setStage("conversation");
    try {
      await fetch(`${API_BASE}/pitch/approve-summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: hitlData.session_id,
          approved: true,
          corrected_summary: hitlData.summary
        })
      });
      addLog("Summary approved.");
    } catch(e) {
      addLog("Failed to approve.");
    }
  };

  const handleRetry = async () => {
    if (!sessionId || !currentAgentId) return;
    
    const currentCount = retryCounts[currentAgentId] || 0;
    if (currentCount >= 2) return;

    setRetrying(true);
    setCoachHints(null);
    setWeakAnswerDetected(false);

    try {
      const res = await fetch(`${API_BASE}/conversation/retry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          agent_id: currentAgentId
        })
      });

      if (res.ok) {
        setManualText('');
        setRetryCounts((prev: Record<string, number>) => ({
          ...prev,
          [currentAgentId]: currentCount + 1
        }));

        setPanelState((prev: PanelState) => {
          const existing = prev[currentAgentId];
          if (!existing) return prev;
          const parts = existing.text.split("\n\nReaction: ");
          return {
            ...prev,
            [currentAgentId]: {
              ...existing,
              text: parts[0],
              status: "done"
            }
          };
        });

        setWaitingForAnswer(true);
        setRetryStatus("Answer cleared — give it another go");
        setTimeout(() => setRetryStatus(null), 2000);
      }
    } catch (err) {
      console.error('Retry failed:', err);
      addLog("Retry failed.");
    } finally {
      setRetrying(false);
    }
  };

  const isWeakAnswer = (text: string) => {
    if (text.trim().split(' ').length < 8) return true;
    const weakPhrases = [
      "i don't know",
      "not sure",
      "haven't thought",
      "no idea",
      "i'm not sure",
      "don't know",
      "good question",
      "maybe",
      "i think so",
      "probably"
    ];
    const lower = text.toLowerCase();
    return weakPhrases.some(phrase => lower.includes(phrase));
  };

  const getCoachHints = async () => {
    setCoachLoading(true);
    try {
      const res = await fetch(`${API_BASE}/conversation/coach`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          agent_id: currentAgentId,
          question: currentQuestion
        })
      });
      const data = await res.json();
      setCoachHints(data.coach_hints);
    } catch (e) {
      addLog("Failed to get coaching hints.");
    }
    setCoachLoading(false);
  };

  const submitRebuttal = async () => {
    if (!manualText || !challengingAgentId || !challengingAgentClaim) return;
    const text = manualText;
    setIsRebutting(true);
    setManualText("");
    addLog(`Sending rebuttal to ${challengingAgentId}...`);
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
      updateAgentState(challengingAgentId, `\n\n💬 Rebuttal: ${data.agent_response}`, "done");
      setChallengingAgentClaim(data.agent_response); // Show the latest reply in the box
      enqueueSpeech(challengingAgentId, data.agent_response);
      
      // Update local conversation
      setConversation((prev: ConversationTurn[]) => [
        ...prev, 
        { type: "pitcher_interrupt", agent_name: pitcherId || "Alex Chen", content: text },
        { type: "host_utterance", agent_id: challengingAgentId, agent_name: data.name || challengingAgentId, content: data.agent_response }
      ]);
    } catch(e) {
      addLog("Failed to send rebuttal.");
    } finally {
      setIsRebutting(false);
    }
  };

  const submitAnswer = async (overrideText?: string | any) => {
    const textToSubmit = typeof overrideText === 'string' ? overrideText : manualText;
    if (!textToSubmit) return;

    if (challengingAgentId && challengingAgentId !== "pitcher") {
      submitRebuttal();
      return;
    }

    if (isWeakAnswer(textToSubmit) && !weakAnswerDetected) {
      setWeakAnswerDetected(true);
      await getCoachHints();
      return;
    }

    const ans = textToSubmit;
    setWaitingForAnswer(false);
    setIsAnsweringInterrupt(false);
    setCoachHints(null);
    setWeakAnswerDetected(false);
    try {
      await fetch(`${API_BASE}/conversation/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          answer: ans,
          provider
        })
      });
      setConversation((prev: ConversationTurn[]) => [...prev, {
        type: "answer",
        agent_name: pitcherId || "Alex Chen",
        content: ans
      }]);
    } catch(e) {
      addLog("Failed to submit answer.");
    }
  };

  const submitPushback = async () => {
    if (!pushbackText) return;
    setIsPushbacking(true);
    addLog("Sending pushback to Judge...");
    
    const url = new URL(`${API_BASE}/stream/pushback`);
    url.searchParams.append("session_id", sessionId);
    url.searchParams.append("pushback", pushbackText);
    url.searchParams.append("provider", provider);

    const eventSource = new window.EventSource(url.toString());
    let fullPushbackResponse = "";

    eventSource.addEventListener("agent_token", (e: any) => {
        const data = JSON.parse(e.data);
        fullPushbackResponse += data.token;
    });

    eventSource.addEventListener("session_complete", (e: any) => {
        const data = JSON.parse(e.data);
        setVerdictData(data.verdict);
        setShowVerdictModal(true);
        setIsPushbacking(false);
        eventSource.close();
        enqueueSpeech("judge", "I have considered your point. " + fullPushbackResponse);
    });
  };

  const handleInterrupt = async () => {
    if (stage !== "conversation" || isInterrupting) return;
    setIsInterrupting(true);
    isInterruptingRef.current = true;
    cancelAllSpeech(); // INSTANT local cutoff
    try {
      await fetch(`${API_BASE}/conversation/interrupt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: "" })
      });
      addLog("Interruption requested...");
    } catch(e) {
      addLog("Interrupt failed.");
      setIsInterrupting(false);
    }
    // isInterrupting stays true until interrupt_ack done event clears it
  };

  const submitSkip = async () => {
    try {
      await fetch(`${API_BASE}/conversation/skip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId })
      });
    } catch(e) {
      console.error("Skip error:", e);
    }
  };

  const handleChallengeAction = () => {
    setNeedsSkipApproval(false);
    needsSkipApprovalRef.current = false;
    submitSkip(); // Release backend from waiting for a full answer
    // Keep flowLockRef.current = true to pause main stream while in sub-convo
    challengingAgentIdRef.current = challengingAgentId;
    setManualText("");
    addLog(`Challenge accepted. Speak your rebuttal to ${challengingAgentId}...`);
  };

  const handleSkip = () => {
    setNeedsSkipApproval(false);
    needsSkipApprovalRef.current = false;
    cancelAllSpeech(); // Deeply cancel speech and queue
    submitSkip(); // Release backend from waiting
    flowLockRef.current = false; // RELEASE LOCK to allow next agent
    setChallengingAgentId(null);
    challengingAgentIdRef.current = null;
    setChallengingAgentClaim(null);
    setManualText("");
    addLog("Interaction skipped. Panel continuing...");
  };

  const handleChallenge = (agentId: string, claim: string) => {
    // This is for legacy/from code if needed
    setChallengingAgentId(agentId);
    challengingAgentIdRef.current = agentId;
    setChallengingAgentClaim(claim);
    setManualText("");
    addLog(`Challenging ${agentId}'s claim. Speak your rebuttal...`);
  };

  const endChallengeMode = () => {
    setChallengingAgentId(null);
    challengingAgentIdRef.current = null;
    setNeedsSkipApproval(false);
    needsSkipApprovalRef.current = false;
    cancelAllSpeech(); // Deeply cancel speech and queue
    submitSkip(); 
    flowLockRef.current = false; // RELEASE LOCK to allow next agent
    setChallengingAgentClaim(null);
    setManualText("");
    addLog("Interaction ended. Panel continuing...");
  };

  return (
    <div className="flex min-h-screen bg-background text-on-background selection:bg-primary/30">
      <Sidebar 
        onNewPitch={handleNewPitch} 
        onViewChange={(v) => setView(v)}
        currentView={view}
      />

      <main className="flex-1 lg:ml-64 flex flex-col relative min-h-screen overflow-x-hidden">
        <Header 
          provider={provider} 
          setProvider={setProvider} 
          disabled={stage !== "idle"} 
        />

        <div className="bg-gradient-to-b from-surface-container-low to-transparent h-px w-full"></div>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {view === "library" ? (
            <div className="p-12 max-w-7xl mx-auto w-full space-y-16 animate-in fade-in duration-700 h-full overflow-y-auto custom-scrollbar">
              {/* Header Section */}
              <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-10">
                <div className="space-y-4">
                  <h2 className="text-5xl font-manrope font-black text-white uppercase tracking-tighter leading-none">
                    Resource <span className="text-primary">Athenaeum</span>
                  </h2>
                  <p className="text-on-surface-variant font-medium text-lg max-w-xl leading-relaxed">
                    Curated intelligence vectors, pitch artifacts, and strategic history captured by the Pitch to the Panel system.
                  </p>
                </div>
                <div className="flex items-center gap-2 bg-surface-container-low p-1.5 rounded-2xl border border-white/5 shadow-2xl">
                   {["All Files", "Favorites", "Recent"].map((tab, i) => (
                     <button key={tab} className={`px-6 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${i === 0 ? 'bg-surface-container-high text-primary shadow-lg border border-white/5' : 'text-on-surface-variant hover:text-white'}`}>
                       {tab}
                     </button>
                   ))}
                </div>
              </div>

              {/* Bento Grid Layout from Stitch Deliverable */}
              <div className="grid grid-cols-1 md:grid-cols-12 gap-8">
                {/* Fixed Action Column */}
                <div className="md:col-span-4 lg:col-span-3 flex flex-col gap-8">
                  {/* Upload Card */}
                  <div className="glass-card ghost-border rounded-3xl p-10 flex flex-col items-center justify-center text-center group cursor-pointer hover:border-primary/40 transition-all duration-500 bg-gradient-to-br from-primary/5 to-transparent relative overflow-hidden shadow-2xl">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 -mr-16 -mt-16 rounded-full blur-3xl group-hover:bg-primary/10 transition-colors"></div>
                    <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform border border-primary/20 rotate-3">
                       <span className="material-symbols-outlined text-4xl text-primary">upload_file</span>
                    </div>
                    <h3 className="text-xl font-manrope font-black text-white uppercase tracking-tight mb-3">Ingest Material</h3>
                    <p className="text-[10px] text-on-surface-variant font-black uppercase tracking-widest leading-loose mb-8 px-4 opacity-40">
                       Vectorize PDFs, decks, or research materials for strategic context.
                    </p>
                    <button className="bg-white/5 px-8 py-3 rounded-full text-primary text-[10px] font-black uppercase tracking-[0.2em] border border-primary/30 hover:bg-primary hover:text-on-primary transition-all active:scale-95 shadow-lg group-hover:shadow-primary/20">
                      Select Files
                    </button>
                  </div>

                  {/* Active Context Sidebar Item */}
                  <div className="bg-surface-container-low/50 rounded-3xl p-8 border border-white/5 space-y-6 shadow-xl">
                    <h4 className="text-[9px] font-black uppercase tracking-[0.2em] text-on-surface-variant opacity-60">Active Intelligence</h4>
                    <div className="space-y-5">
                       {[ 
                         { name: "Claude 3.5 Sonnet", icon: "bolt", color: "text-primary", count: "3 Files Citied" }, 
                         { name: "GPT-4o Research", icon: "neurology", color: "text-tertiary", count: "Inactive" } 
                       ].map((ref, i) => (
                         <div key={i} className={`flex items-center gap-4 transition-all ${i === 1 ? 'opacity-30' : 'hover:translate-x-1'}`}>
                           <div className={`w-10 h-10 rounded-xl bg-white/[0.02] flex items-center justify-center border border-white/5 shadow-inner`}>
                             <span className={`material-symbols-outlined text-xl ${ref.color}`}>{ref.icon}</span>
                           </div>
                           <div>
                              <p className="text-xs font-black font-manrope text-white uppercase tracking-tighter">{ref.name}</p>
                              <p className="text-[9px] font-label font-bold text-on-surface-variant uppercase tracking-widest">{ref.count}</p>
                           </div>
                         </div>
                       ))}
                    </div>
                  </div>
                </div>

                {/* Main Dashboard Area */}
                <div className="md:col-span-8 lg:col-span-9 space-y-12 pb-20">
                   {/* Artifact Results Ledger */}
                   <div className="space-y-8">
                      <div className="flex items-center justify-between">
                         <div className="flex items-center gap-4">
                            <span className="w-1.5 h-10 bg-primary rounded-full shadow-[0_0_20px_#68ffca]"></span>
                            <h3 className="text-2xl font-manrope font-black text-white uppercase tracking-tighter">Strategic Artifacts</h3>
                         </div>
                         <button className="text-[10px] font-black uppercase tracking-widest text-[#68ffca] hover:underline opacity-60 hover:opacity-100 transition-opacity">Full Ledger</button>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
                        {libraryData && Object.keys(libraryData).length > 0 ? (
                           Object.entries(libraryData).map(([id, data]: [string, any]) => (
                              <div key={id} className="glass-card ghost-border rounded-3xl overflow-hidden group hover:translate-y-[-10px] transition-all duration-500 hover:shadow-[0_30px_60px_-15px_rgba(0,0,0,0.5)] bg-gradient-to-b from-white/[0.02] to-transparent border-white/5">
                                 <div className="h-44 bg-surface-container-high/30 relative overflow-hidden flex items-center justify-center p-6 border-b border-white/5">
                                    <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                                    <span className="material-symbols-outlined text-7xl text-white/5 transition-all duration-700 group-hover:scale-125 group-hover:text-primary/10" style={{ fontVariationSettings: "'FILL' 0" }}>inventory_2</span>
                                    <div className="absolute top-5 right-5 ring-1 ring-primary/30 px-3 py-1.5 rounded-full bg-background/80 backdrop-blur-md text-[9px] font-black text-primary uppercase tracking-widest shadow-2xl">
                                       Score: {data.score || "7.5"}
                                    </div>
                                 </div>
                                 <div className="p-8 space-y-5">
                                    <div>
                                       <h4 className="font-manrope font-black text-white uppercase text-base truncate mb-1.5 group-hover:text-primary transition-colors">{id}</h4>
                                       <p className="text-[10px] text-on-surface-variant font-black uppercase tracking-[0.2em] opacity-40">System Vector ID: {id.slice(0,8)}</p>
                                    </div>
                                    <p className="text-xs text-on-surface-variant/80 line-clamp-2 leading-relaxed italic italic opacity-90">"{data.summary || "No automated summary generated for this session yet."}"</p>
                                    <div className="flex items-center justify-between pt-6 border-t border-white/5">
                                       <div className="flex items-center gap-4">
                                          <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center shadow-lg transition-transform hover:scale-110">
                                            <span className="material-symbols-outlined text-sm text-primary">bolt</span>
                                          </div>
                                          <div className="w-8 h-8 rounded-full bg-tertiary/10 border border-tertiary/30 flex items-center justify-center shadow-lg transition-transform hover:scale-110">
                                            <span className="material-symbols-outlined text-sm text-tertiary">neurology</span>
                                          </div>
                                       </div>
                                       <button className="text-on-surface-variant hover:text-white transition-colors hover:scale-125 active:scale-90 transition-all">
                                          <span className="material-symbols-outlined text-lg">more_vert</span>
                                       </button>
                                    </div>
                                 </div>
                              </div>
                           ))
                        ) : (
                          <div className="col-span-full py-32 flex flex-col items-center justify-center text-on-surface-variant/20 border-2 border-dashed border-white/5 rounded-[40px] bg-white/[0.01]">
                            <span className="material-symbols-outlined text-[100px] mb-8 font-thin opacity-10">database</span>
                            <p className="font-manrope font-black text-3xl uppercase tracking-[0.6em] opacity-40">Artifacts Empty</p>
                            <p className="mt-4 text-[10px] uppercase tracking-widest font-black opacity-30">The Digital Athenaeum awaits ingest</p>
                          </div>
                        )}
                      </div>
                   </div>
                </div>
              </div>
            </div>
          ) : view === "transcripts" ? (
            <div className="flex flex-1 overflow-hidden h-full">
              {/* Sessions Sidebar List - Matching Stitch */}
              <section className="w-80 flex flex-col bg-[#091328]/50 h-full shadow-inner border-r border-white/5">
                <div className="p-8 flex flex-col h-full">
                  <h2 className="font-manrope text-2xl font-black text-white uppercase tracking-tighter mb-6">Past Sessions</h2>
                  {/* Search Bar for Sessions */}
                  <div className="relative flex items-center bg-surface-container-low px-4 py-3 rounded-2xl ring-1 ring-white/5 mb-8">
                    <span className="material-symbols-outlined text-on-surface-variant text-base mr-3 opacity-40">search</span>
                    <input className="bg-transparent border-none text-xs focus:ring-0 placeholder:text-on-surface-variant/40 w-full font-bold uppercase tracking-widest" placeholder="Search sessions..." type="text"/>
                  </div>
                  
                  {/* Session list items */}
                  <div className="space-y-4 overflow-y-auto custom-scrollbar flex-1 pr-2">
                    {/* Active Session Highlighted */}
                    <div className="p-5 rounded-2xl bg-primary/5 ring-1 ring-primary/20 border-l-4 border-primary cursor-pointer transition-all shadow-xl group">
                      <div className="flex justify-between items-start mb-3">
                        <span className="text-[10px] font-black text-primary uppercase tracking-widest">Active Research</span>
                        <span className="text-[10px] font-bold text-on-surface-variant/50">14:22</span>
                      </div>
                      <h3 className="font-manrope font-black text-sm text-white uppercase tracking-tight mb-2 group-hover:text-primary transition-colors">Venture Capital Strategy</h3>
                      <p className="text-[11px] text-on-surface-variant/70 line-clamp-2 leading-relaxed italic italic">Live evaluation of SaaS growth distribution models.</p>
                      <div className="mt-5 flex -space-x-2">
                        <div className="w-6 h-6 rounded-full bg-primary border border-[#091328] flex items-center justify-center text-[8px] font-black text-[#004b36] shadow-lg">CL</div>
                        <div className="w-6 h-6 rounded-full bg-tertiary border border-[#091328] flex items-center justify-center text-[8px] font-black text-on-tertiary shadow-lg">GP</div>
                        <div className="w-6 h-6 rounded-full bg-secondary-container border border-[#091328] flex items-center justify-center text-[8px] font-black text-on-secondary shadow-lg">GE</div>
                      </div>
                    </div>
                    
                    {/* List from libraryData */}
                    {Object.entries(libraryData || {}).slice(0, 5).map(([id, data]: [string, any]) => (
                       <div key={id} className="p-5 rounded-2xl hover:bg-surface-container-high transition-all cursor-pointer group border border-transparent hover:border-white/5">
                         <div className="flex justify-between items-center mb-3">
                            <span className="text-[10px] font-black text-on-surface-variant/30 uppercase tracking-widest">Archive Vector</span>
                            <span className="text-[10px] font-bold text-on-surface-variant/30">Mar {(Math.floor(Math.random() * 20) + 1)}</span>
                         </div>
                         <h3 className="font-manrope font-black text-sm text-white uppercase tracking-tight mb-2 group-hover:text-primary transition-colors">{id} Strategy</h3>
                         <p className="text-[11px] text-on-surface-variant/60 line-clamp-1 italic italic italic opacity-70">"{data.summary || "Archived session findings and metrics."}"</p>
                       </div>
                    ))}
                  </div>
                </div>
              </section>

              {/* Main Transcript Area - Matching Stitch Deliverable */}
              <section className="flex-1 flex flex-col bg-[#060e20] overflow-hidden relative">
                {/* Transcript Header Decoration */}
                <div className="absolute top-0 right-0 w-96 h-96 bg-primary/5 blur-[120px] -mr-48 -mt-48 pointer-events-none"></div>
                
                {/* Transcript Header */}
                <div className="p-10 pb-6 flex justify-between items-end bg-gradient-to-b from-[#060e20] via-[#060e20]/80 to-transparent sticky top-0 z-10 backdrop-blur-md">
                  <div>
                    <div className="flex items-center gap-3 mb-3">
                      <span className="px-3 py-1 rounded-full bg-primary/10 text-primary text-[9px] font-black uppercase tracking-[0.2em] border border-primary/20 animate-pulse">Research Active</span>
                      <span className="w-1 h-1 rounded-full bg-on-surface-variant/40"></span>
                      <span className="text-on-surface-variant text-[10px] font-black uppercase tracking-widest opacity-40">Session ID: {sessionId ? sessionId.slice(0, 8) : "XP-8821"}</span>
                    </div>
                    <h2 className="text-4xl font-manrope font-black text-white uppercase tracking-tighter">
                      Venture <span className="text-primary italic">Capital Strategy</span>
                    </h2>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex bg-surface-container-low p-1 rounded-full border border-white/5 shadow-2xl">
                      <button className="px-6 py-2.5 text-[10px] font-black uppercase tracking-widest hover:bg-surface-container-high rounded-full transition-all flex items-center gap-2 text-on-surface-variant hover:text-white">
                        <span className="material-symbols-outlined text-sm">picture_as_pdf</span> PDF
                      </button>
                      <button className="px-6 py-2.5 text-[10px] font-black uppercase tracking-widest hover:bg-surface-container-high rounded-full transition-all flex items-center gap-2 text-on-surface-variant hover:text-white">
                        <span className="material-symbols-outlined text-sm">description</span> TXT
                      </button>
                    </div>
                    <button className="bg-primary text-on-primary-container px-8 py-3 rounded-full font-black text-[11px] uppercase tracking-[0.2em] hover:scale-105 active:scale-95 transition-all shadow-[0_20px_40px_rgba(24,200,151,0.25)] border border-primary/20">
                      Share Session
                    </button>
                  </div>
                </div>

                {/* Messages Area */}
                <div className="flex-1 overflow-y-auto px-12 pb-40 pt-8 space-y-16 custom-scrollbar">
                   {conversation.map((turn, idx) => {
                     const isUser = turn.type.includes('pitcher') || turn.type === 'answer';
                     const isAlpha = turn.agent_id?.toLowerCase().includes('alpha') || turn.agent_id?.toLowerCase().includes('claude');
                     const isBravo = turn.agent_id?.toLowerCase().includes('bravo') || turn.agent_id?.toLowerCase().includes('ge');
                     const isGamma = turn.agent_id?.toLowerCase().includes('gpt');
                     
                     return (
                        <div key={idx} className="flex gap-8 max-w-5xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-700">
                          {/* Avatar Sidebar */}
                          <div className="flex-shrink-0 relative">
                            <div className={`w-12 h-12 rounded-full flex items-center justify-center ring-2 ring-white/5 shadow-2xl transition-all hover:scale-110 ${
                              isUser ? 'bg-surface-container-highest text-primary' : isAlpha ? 'bg-primary text-[#003828] shadow-primary/30' : isGamma ? 'bg-tertiary text-on-tertiary shadow-tertiary/30' : 'bg-secondary-container text-on-secondary shadow-secondary/30'
                            }`}>
                              <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                                {isUser ? 'person' : isAlpha ? 'smart_toy' : isGamma ? 'neurology' : 'query_stats'}
                              </span>
                            </div>
                            {!isUser && (
                              <div className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-[#060e20] flex items-center justify-center border border-white/10 shadow-xl">
                                <div className="w-2.5 h-2.5 rounded-full bg-primary animate-pulse shadow-[0_0_10px_#68ffca]"></div>
                              </div>
                            )}
                          </div>

                          {/* Message Bubble - Premium Glass Effect */}
                          <div className={`flex-1 ${!isUser ? 'glass-panel p-10 rounded-3xl rounded-tl-none ring-1 ring-white/5 shadow-[0_30px_60px_-15px_rgba(0,0,0,0.6)]' : 'pt-3'}`}>
                            <div className="flex items-center justify-between mb-6">
                              <div className="flex items-center gap-4">
                                <span className={`font-manrope font-black uppercase tracking-[0.1em] text-sm ${isUser ? 'text-white' : isAlpha ? 'text-primary' : isBravo ? 'text-secondary' : isGamma ? 'text-tertiary' : 'text-primary'}`}>
                                  {turn.agent_name || (isUser ? (pitcherId || 'Alex Chen') : 'System Agent')}
                                </span>
                                {!isUser && (
                                  <span className={`px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border border-white/5 ${
                                    isAlpha ? 'bg-primary/10 text-primary' : isGamma ? 'bg-tertiary/10 text-tertiary' : 'bg-secondary/10 text-secondary'
                                  }`}>
                                    {isAlpha ? 'Lead Strategist' : isGamma ? 'Economic Advisor' : 'Market Analyst'}
                                  </span>
                                )}
                              </div>
                              <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant opacity-30 font-label">14:22 PM</span>
                            </div>

                            <div className={`text-on-surface leading-[1.8] text-lg ${isUser ? 'font-medium opacity-90' : 'font-normal opacity-95'}`}>
                               {turn.content.split('\n\n').map((p, i) => (
                                 <p key={i} className={i > 0 ? 'mt-4' : ''}>{p}</p>
                               ))}
                            </div>

                            {!isUser && (
                              <div className="mt-10 pt-6 border-t border-white/5 flex gap-8">
                                <button className="text-[10px] font-black uppercase tracking-[0.2em] text-on-surface-variant/40 hover:text-primary transition-all flex items-center gap-2.5 group">
                                   <span className="material-symbols-outlined text-sm group-hover:rotate-12 transition-transform">content_copy</span> Copy Response
                                </button>
                                <button className="text-[10px] font-black uppercase tracking-[0.2em] text-on-surface-variant/40 hover:text-primary transition-all flex items-center gap-2.5 group">
                                   <span className="material-symbols-outlined text-sm group-hover:scale-125 transition-transform">bookmark</span> Save Artifact
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                     )
                   })}
                   
                   {conversation.length === 0 && (
                      <div className="flex flex-col items-center justify-center h-[500px] opacity-10 animate-pulse">
                         <span className="material-symbols-outlined text-9xl mb-8 font-thin">history_edu</span>
                         <p className="font-manrope font-black text-4xl uppercase tracking-[0.6em] text-center">Transcript<br/>Void</p>
                         <p className="mt-6 uppercase tracking-[0.4em] text-[10px] font-black">Initiate first session to populate history</p>
                      </div>
                   )}
                </div>

                {/* Footer Search - Matching Stitch Floating Design */}
                <div className="absolute bottom-10 left-0 right-0 p-8 flex justify-center pointer-events-none">
                   <div className="max-w-3xl w-full relative group pointer-events-auto">
                     <div className="absolute inset-0 bg-primary/10 blur-[60px] rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700"></div>
                     <div className="relative bg-[#192540]/60 backdrop-blur-3xl ring-1 ring-white/10 rounded-full px-10 py-5 flex items-center gap-8 shadow-[0_50px_100px_-20px_rgba(0,0,0,0.7)] border border-white/5">
                       <span className="material-symbols-outlined text-primary text-3xl">search</span>
                       <input className="bg-transparent border-none flex-1 focus:ring-0 text-white text-lg placeholder:text-on-surface-variant/20 font-bold uppercase tracking-widest" placeholder="Search this session..." type="text"/>
                       <div className="flex items-center gap-8">
                         <div className="flex gap-3">
                           <button className="w-10 h-10 rounded-full hover:bg-white/5 flex items-center justify-center transition-all hover:scale-110 active:scale-95 border border-white/5 text-on-surface-variant">
                             <span className="material-symbols-outlined text-base">keyboard_arrow_up</span>
                           </button>
                           <button className="w-10 h-10 rounded-full hover:bg-white/5 flex items-center justify-center transition-all hover:scale-110 active:scale-95 border border-white/5 text-on-surface-variant">
                             <span className="material-symbols-outlined text-base">keyboard_arrow_down</span>
                           </button>
                         </div>
                         <div className="w-px h-8 bg-white/5"></div>
                         <button className="px-8 py-3 rounded-full bg-primary/10 text-primary font-black uppercase tracking-[0.2em] text-[10px] hover:bg-primary hover:text-[#004b36] transition-all active:scale-95 border border-primary/20 shadow-lg">
                           Filter
                         </button>
                       </div>
                     </div>
                   </div>
                </div>
              </section>
            </div>
          ) : view === "analytics" ? (
            <div className="max-w-4xl mx-auto w-full p-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
               <div className="mb-10 text-center">
                 <h2 className="text-4xl font-manrope font-black text-white uppercase tracking-tighter mb-2">
                    Visual <span className="text-primary">Intelligence</span>
                 </h2>
                 <p className="text-on-surface-variant/60 text-xs font-label uppercase tracking-widest">Strategic Performance Analytics</p>
               </div>
               
               <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="glass-card ghost-border p-8 rounded-3xl flex flex-col items-center justify-center min-h-[400px]">
                     <h3 className="text-on-surface-variant font-bold mb-8 tracking-wider uppercase text-[10px] w-full text-left font-label">Session Scoring</h3>
                     {radarChart ? (
                        <img src={`data:image/png;base64,${radarChart}`} alt="Radar" className="w-full max-w-[320px] filter drop-shadow-[0_0_20px_rgba(24,200,151,0.2)]" />
                     ) : (
                        <div className="flex flex-col items-center text-on-surface-variant/30">
                           <span className="material-symbols-outlined text-6xl mb-4">analytics</span>
                           <p className="text-xs uppercase tracking-widest font-black">No Active Evaluation</p>
                        </div>
                     )}
                  </div>
                  
                  <div className="glass-card ghost-border p-8 rounded-3xl">
                     <h3 className="text-on-surface-variant font-bold mb-6 tracking-wider uppercase text-[10px] font-label">Host Sentiment</h3>
                     <div className="space-y-6">
                        {["Host Alpha", "Host Bravo", "Mediator"].map(name => (
                           <div key={name} className="space-y-2">
                              <div className="flex justify-between text-[10px] font-black uppercase tracking-widest">
                                 <span className="text-white">{name}</span>
                                 <span className="text-primary">Optimistic</span>
                              </div>
                              <div className="h-1 w-full bg-surface-container-highest rounded-full overflow-hidden">
                                 <div className="h-full bg-primary" style={{ width: `${60 + Math.random() * 30}%` }}></div>
                              </div>
                           </div>
                        ))}
                     </div>
                  </div>
               </div>
            </div>
          ) : (
            <>
              {(stage === "idle" || stage === "pitching") && (
                <div className="min-h-full flex items-center justify-center py-12 px-4 lg:pr-12">
                  <div className="max-w-2xl w-full space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
                    <div className="text-center space-y-2">
                      <h1 className="text-4xl font-extrabold font-headline tracking-tight text-white uppercase tracking-tighter">Initialize <span className="text-primary italic">New Pitch</span></h1>
                      <p className="text-on-surface-variant font-body text-xs uppercase tracking-[0.3em] opacity-40">Configure your environment and summon the panel of experts.</p>
                    </div>
                    
                    <div className="glass-card ghost-border rounded-3xl p-10 lg:p-12 shadow-[0_40px_80px_rgba(0,0,0,0.5)] bg-gradient-to-br from-white/[0.02] to-transparent border-white/5">
                      <div className="space-y-8">
                        <div className="space-y-3">
                          <label className="text-[10px] font-black uppercase tracking-[0.3em] text-primary/60 ml-1">Identity Vector</label>
                          <input 
                            type="text"
                            value={pitcherId}
                            onChange={(e) => setPitcherId(e.target.value)}
                            placeholder="Alex Chen..."
                            className="w-full bg-[#060e20]/50 border border-white/5 rounded-2xl py-4 px-6 text-white focus:ring-1 focus:ring-primary/30 transition-all placeholder:text-white/10 outline-none font-bold uppercase tracking-widest text-xs"
                          />
                        </div>
                        
                        <div className="space-y-3">
                          <label className="text-[10px] font-black uppercase tracking-[0.3em] text-primary/60 ml-1">Panel Configuration</label>
                          <div className="relative">
                            <select 
                              value={difficulty}
                              onChange={(e) => setDifficulty(e.target.value)}
                              className="w-full bg-[#060e20]/50 border border-white/5 rounded-2xl py-4 px-6 text-white focus:ring-1 focus:ring-primary/30 transition-all appearance-none outline-none cursor-pointer font-bold uppercase tracking-widest text-xs"
                            >
                              <option value="gentle">Standard Panel (Gentle)</option>
                              <option value="standard">Standard Panel (Default)</option>
                              <option value="brutal">Standard Panel (Brutal)</option>
                              <option value="contrarians">The Contrarians (Devils Advocate)</option>
                            </select>
                            <span className="material-symbols-outlined absolute right-6 top-1/2 -translate-y-1/2 pointer-events-none text-primary/40">expand_more</span>
                          </div>
                        </div>

                        <div className="space-y-3">
                          <label className="text-[10px] font-black uppercase tracking-[0.3em] text-primary/60 ml-1">Submission Content</label>
                          <textarea 
                            value={manualText}
                            onChange={(e) => setManualText(e.target.value)}
                            className="w-full bg-[#060e20]/50 border border-white/5 rounded-3xl py-6 px-6 text-white focus:ring-1 focus:ring-primary/30 transition-all placeholder:text-white/5 resize-none outline-none h-48 custom-scrollbar font-medium leading-relaxed"
                            placeholder="Describe your initiative..."
                          />
                        </div>

                        <div className="pt-6 flex flex-col sm:flex-row gap-6">
                          {stage === "idle" ? (
                            <button 
                              onClick={() => setStage("pitching")}
                              className="flex-1 py-5 px-8 cta-gradient text-on-primary-container font-black font-manrope text-lg rounded-full shadow-[0_30px_60px_-15px_rgba(24,200,151,0.4)] hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center gap-4 uppercase tracking-tighter"
                            >
                              New Session
                              <span className="material-symbols-outlined">add</span>
                            </button>
                          ) : (
                            <>
                              <button 
                                onClick={isRecording ? stopRecording : startRecording}
                                className={`flex-1 py-5 px-8 rounded-full flex items-center justify-center gap-3 transition-all active:scale-95 border uppercase font-black text-[11px] tracking-widest ${
                                  isRecording ? "bg-error/10 border-error/20 text-error animate-pulse" : "bg-white/5 border-white/10 text-white hover:bg-white/10"
                                }`}
                              >
                                <span className="material-symbols-outlined text-xl">
                                  {isRecording ? "stop" : "mic"}
                                </span>
                                {isRecording ? "Listening..." : "Voice Input"}
                              </button>
                              <button 
                                onClick={finishPitch}
                                className="flex-[2] py-5 px-8 cta-gradient text-on-primary-container font-black font-manrope text-lg rounded-full shadow-[0_30px_60px_-15px_rgba(24,200,151,0.4)] hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center gap-4 uppercase tracking-tighter"
                              >
                                Submit Proposal
                                <span className="material-symbols-outlined">rocket_launch</span>
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {stage === "hitl_summary" && hitlData && (
                <div className="max-w-7xl mx-auto px-6 py-12 flex flex-col items-center justify-center min-h-[70vh] animate-in fade-in zoom-in-95 duration-700">
                  <div className="glass-card ghost-border p-10 rounded-[40px] border-primary/20 shadow-[0_50px_100px_-20px_rgba(24,200,151,0.3)] bg-[#192540]/80 backdrop-blur-3xl max-w-2xl w-full text-center">
                    <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-8 border border-primary/20 animate-pulse">
                      <span className="material-symbols-outlined text-4xl text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>verified</span>
                    </div>
                    <h2 className="text-4xl font-black text-white mb-4 font-manrope tracking-tighter uppercase">Confirm Your Pitch</h2>
                    <p className="text-on-surface-variant/70 mb-10 text-lg leading-relaxed font-label px-10">Review and refine the core proposal before our specialist panel begins their scrutiny.</p>
                    <textarea 
                      value={hitlData.summary}
                      onChange={(e) => setHitlData({ ...hitlData, summary: e.target.value })}
                      className="w-full bg-[#060e20]/50 border border-white/5 rounded-2xl p-6 text-white text-lg mb-8 outline-none focus:border-primary/30 transition-all resize-none h-40 custom-scrollbar"
                    />
                    <button onClick={approveSummary} className="w-full cta-gradient text-on-primary-container px-12 py-5 rounded-full font-black text-xl shadow-[0_30px_60px_-15px_rgba(24,200,151,0.5)] active:scale-95 transition-all uppercase tracking-widest">
                      Enter the Arena
                    </button>
                  </div>
                </div>
              )}

              {stage === "conversation" && (
                <div className="flex flex-col lg:flex-row h-full p-8 gap-8 animate-in fade-in duration-500">
                  <div className="flex-1 flex flex-col gap-6">
                    <div className="flex justify-between items-center mb-2">
                       <div className="flex items-center gap-3">
                        <span className="text-[10px] font-label uppercase tracking-widest text-primary/80">Active Domain</span>
                        <span className="text-white font-bold font-manrope">
                          {domainData?.sub_domain || "Analyzing Pitch..."}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                        <span className="text-[10px] font-label uppercase tracking-widest text-primary">Live Session</span>
                      </div>
                    </div>

                    <div className="flex-1 overflow-y-auto custom-scrollbar pr-2">
                      <PanelGrid 
                        panelState={panelState} 
                        onChallenge={handleChallenge} 
                        factChecks={factChecks} 
                        challengingAgentId={challengingAgentId}
                        activeHosts={activeHosts}
                      />
                    </div>
                  </div>

                  <div className="w-full lg:w-[450px] flex flex-col gap-6 h-full">
                    <div className="flex-1 flex flex-col bg-surface-container-low rounded-xl overflow-hidden border border-outline-variant/10 shadow-xl">
                      <div className="p-6 border-b border-outline-variant/10 flex items-center justify-between bg-surface-container/30">
                        <h4 className="font-manrope font-bold text-lg text-white">Live Transcript</h4>
                        <span className="text-[10px] font-label uppercase tracking-widest bg-surface-container-highest/50 px-3 py-1 rounded-full text-primary/80 border border-primary/10">Synthesis</span>
                      </div>
                      <div className="flex-1 overflow-hidden flex flex-col">
                        <LiveFeed logs={logs} conversation={conversation} />
                      </div>
                    </div>

                    {radarChart && (
                      <div className="glass-panel border border-outline-variant/10 rounded-xl p-6 flex flex-col items-center">
                        <h3 className="text-on-surface-variant font-bold mb-4 tracking-wider uppercase text-[10px] w-full text-left font-label">Pitch Evaluation</h3>
                        <img src={`data:image/png;base64,${radarChart}`} alt="Radar" className="w-full max-w-[280px] filter drop-shadow-[0_0_15px_rgba(24,200,151,0.1)]" />
                      </div>
                    )}
                  </div>
                </div>
              )}

              {verdictData && (
                <div className="max-w-4xl mx-auto py-12 px-6 flex flex-col gap-8 animate-in slide-in-from-bottom-8">
                  {showVerdictModal && <VerdictCard verdict={verdictData} sessionId={sessionId} onClose={() => setShowVerdictModal(false)} />}
                  {!showVerdictModal && (
                    <div className="flex justify-end">
                      <button onClick={() => setShowVerdictModal(true)} className="text-sm text-primary font-bold hover:underline">Re-examine Verdict</button>
                    </div>
                  )}
                  <div className="glass-card ghost-border p-8 rounded-2xl shadow-2xl border-rose-500/20">
                    <h2 className="text-2xl font-black text-rose-500 mb-4 font-manrope">Negotiate Findings</h2>
                    <textarea 
                      value={pushbackText}
                      onChange={(e) => setPushbackText(e.target.value)}
                      className="w-full bg-surface-container-low text-on-surface text-sm border border-outline-variant/10 rounded-xl p-4 h-32 mb-6 outline-none focus:ring-1 focus:ring-rose-500/20 transition-all"
                      placeholder="Challenge the judge's reasoning..."
                    />
                    <button disabled={isPushbacking} onClick={submitPushback} className="w-full bg-rose-600 hover:bg-rose-500 text-white px-6 py-4 rounded-full font-bold shadow-lg shadow-rose-900/20 transition-all active:scale-95">
                      {isPushbacking ? 'Negotiating Systemic Shift...' : 'Submit Pushback'}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Floating Actions */}
        {stage === "conversation" && !isInterrupting && (
          <div className="fixed bottom-12 left-1/2 -ml-32 lg:left-[calc(50%+128px)] -translate-x-1/2 z-50">
            <button 
              onClick={handleInterrupt}
              className="px-12 py-6 rounded-full cta-gradient text-on-primary-container font-manrope font-black text-2xl shadow-[0_30px_60px_-15px_rgba(24,200,151,0.5)] hover:scale-105 active:scale-95 transition-all duration-500 group flex items-center gap-5 border border-white/20 animate-in slide-in-from-bottom-10"
            >
              <div className="relative">
                <span className="material-symbols-outlined text-3xl group-hover:rotate-12 transition-transform" style={{ fontVariationSettings: "'FILL' 1" }}>back_hand</span>
                <span className="absolute -top-1 -right-1 w-3 h-3 bg-white rounded-full animate-ping opacity-50"></span>
              </div>
              <span className="tracking-tighter uppercase">Jump In</span>
            </button>
          </div>
        )}

        {/* Floating Answer Box */}
        {waitingForAnswer && !challengingAgentId && (
          <div className="fixed bottom-10 left-1/2 -translate-x-1/2 lg:left-[calc(50%+128px)] w-full max-w-2xl z-50 px-6 animate-in slide-in-from-bottom-10">
            <div className="glass-card ghost-border p-8 rounded-[32px] border-primary/20 shadow-[0_50px_100px_-20px_rgba(0,0,0,0.7)] bg-[#192540]/80 backdrop-blur-3xl relative">
              
              {isAnsweringInterrupt && (
                <button 
                  onClick={() => submitAnswer("Nevermind, go ahead.")}
                  className="absolute top-6 right-6 text-on-surface-variant hover:text-white transition-colors p-2 bg-white/5 rounded-full hover:bg-rose-500/20 font-black text-[10px] tracking-widest uppercase items-center flex gap-2"
                >
                  <span className="material-symbols-outlined text-[16px]">close</span> Cancel
                </button>
              )}

              <div className="flex items-center gap-3 mb-4">
                <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-primary">
                  {isAnsweringInterrupt ? "You have the floor" : "Panel is Waiting"}
                </span>
              </div>
              
              <h3 className="text-white font-manrope font-bold text-xl mb-6 leading-tight">
                "{currentQuestion}"
              </h3>

              <div className="relative group">
                <textarea 
                  value={manualText}
                  onChange={(e) => setManualText(e.target.value)}
                  className="w-full bg-[#060e20]/50 border border-white/5 rounded-2xl p-5 text-white placeholder:text-on-surface-variant/20 focus:border-primary/30 transition-all outline-none resize-none h-28 custom-scrollbar mb-6"
                  placeholder="Formulate your response..."
                />
                
                <div className="flex items-center justify-between">
                  <div className="flex gap-4">
                    <button 
                      onClick={isRecording ? stopRecording : startRecording}
                      className={`w-12 h-12 rounded-full flex items-center justify-center transition-all ${
                        isRecording ? "bg-error text-white scale-110 shadow-[0_0_20px_rgba(255,0,0,0.5)] animate-pulse" : "bg-white/5 text-on-surface-variant hover:text-white"
                      }`}
                    >
                      <span className="material-symbols-outlined text-xl">{isRecording ? "mic_off" : "mic"}</span>
                    </button>
                    {!isAnsweringInterrupt && (
                      <button 
                         onClick={getCoachHints}
                         disabled={coachLoading}
                         className="px-6 rounded-full bg-primary/10 text-primary text-[10px] font-black uppercase tracking-widest border border-primary/20 hover:bg-primary/20 transition-all"
                      >
                        {coachLoading ? "..." : "Get Hint"}
                      </button>
                    )}
                  </div>
                  
                  <button 
                    onClick={() => submitAnswer()}
                    disabled={!manualText && !isAnsweringInterrupt}
                    className="bg-primary text-[#003828] px-10 py-3 rounded-full font-black text-[11px] uppercase tracking-[0.2em] hover:scale-105 active:scale-95 transition-all shadow-[0_20px_40px_rgba(24,200,151,0.2)] disabled:opacity-50"
                  >
                    Transmit Response
                  </button>
                </div>
              </div>

              {coachHints && (
                <div className="mt-6 p-4 bg-primary/5 rounded-xl border border-primary/10 animate-in fade-in">
                  <p className="text-[10px] text-primary/70 italic leading-relaxed">{coachHints.split('\n')[0]}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {challengingAgentId && (
          <div className="fixed inset-0 bg-background/80 backdrop-blur-md z-[60] flex items-center justify-center p-6 animate-in fade-in">
            <div className="max-w-3xl w-full glass-card ghost-border rounded-3xl p-10 shadow-[0_40px_80px_rgba(0,0,0,0.6)] border-rose-500/30">
              <div className="flex justify-between items-start mb-8">
                <div className="space-y-1">
                  <h3 className="text-rose-500 font-black uppercase text-xs tracking-widest flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
                    Direct Challenge: {challengingAgentId}
                  </h3>
                  <p className="text-on-surface-variant text-sm font-medium">Defend your vision or clarify the point.</p>
                </div>
                <button onClick={endChallengeMode} className="text-on-surface-variant hover:text-white transition-colors">
                  <span className="material-symbols-outlined">close</span>
                </button>
              </div>

              <blockquote className="text-2xl text-white font-manrope font-bold mb-10 pl-6 border-l-4 border-rose-500 leading-tight">
                "{challengingAgentClaim}"
              </blockquote>

              <textarea 
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
                className="w-full bg-surface-container-low/50 p-6 rounded-2xl text-white text-lg mb-8 border border-white/5 outline-none h-40 focus:border-rose-500/50 transition-all shadow-inner custom-scrollbar"
                placeholder="Speak your rebuttal..."
              />

              <div className="flex items-center gap-6">
                <button 
                  disabled={isRebutting}
                  onClick={isRecording ? stopRecording : startRecording} 
                  className={`w-16 h-16 rounded-full flex items-center justify-center transition-all ${
                    isRecording ? "bg-error text-white scale-110 shadow-2xl" : "bg-surface-container-highest text-white hover:bg-surface-bright"
                  }`}
                >
                  <span className="material-symbols-outlined text-2xl">{isRecording ? "stop" : "mic"}</span>
                </button>

                <button 
                  onClick={getCoachHints} 
                  disabled={coachLoading}
                  className="px-6 py-2 rounded-full font-bold text-primary bg-primary/10 border border-primary/20 hover:bg-primary/20 transition-all disabled:opacity-50 flex items-center gap-2"
                >
                  <span className="material-symbols-outlined text-sm">psychology</span>
                  {coachLoading ? "Consulting..." : "Coach Hint"}
                </button>

                <div className="flex-grow"></div>

                <button 
                  onClick={submitRebuttal} 
                  disabled={isRebutting || !manualText}
                  className="px-10 py-5 rounded-full bg-rose-600 text-white font-black text-xl hover:bg-rose-500 transition-all disabled:opacity-50 shadow-2xl shadow-rose-900/40 font-headline"
                >
                  {isRebutting ? "Transmitting..." : "Send Rebuttal"}
                </button>
              </div>

              {coachHints && (
                <div className="mt-8 p-6 bg-surface-container/50 rounded-2xl border border-primary/20 animate-in fade-in slide-in-from-bottom-4">
                  <div className="flex items-center gap-2 text-primary mb-3">
                    <span className="material-symbols-outlined text-sm">lightbulb</span>
                    <span className="text-[10px] font-black uppercase tracking-widest font-label">Coach Strategy</span>
                  </div>
                  <ul className="space-y-2 text-on-surface-variant text-sm italic leading-relaxed">
                    {coachHints.split('\n').filter(l => l.trim().length > 5).map((hint, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-primary">•</span>
                        {hint.replace(/^-?\s*Think about:\s*/i, '').trim()}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}

        {needsSkipApproval && !challengingAgentId && (
          <div className="fixed inset-0 bg-background/60 backdrop-blur-sm z-50 flex items-center justify-center p-6 animate-in fade-in">
            <div className="glass-card ghost-border p-10 rounded-3xl max-w-md w-full shadow-2xl flex flex-col items-center text-center">
              <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mb-8 border border-primary/20 text-primary">
                <span className="material-symbols-outlined text-4xl">priority_high</span>
              </div>
              <h3 className="text-2xl font-black text-white mb-3 font-manrope">Panel Interaction</h3>
              <p className="text-on-surface-variant text-sm mb-10 leading-relaxed">
                An agent has posed a challenge. Address it now, or allow the debate to continue.
              </p>
              
              <div className="w-full flex flex-col gap-4">
                <button 
                  onClick={handleChallengeAction}
                  className="w-full cta-gradient text-on-primary-container py-4 rounded-2xl font-black text-lg transition-all shadow-lg active:scale-95"
                >
                  INTERACT NOW
                </button>
                <button 
                  onClick={handleSkip}
                  className="w-full bg-surface-container-highest text-on-surface-variant py-4 rounded-2xl font-bold hover:text-white transition-all text-sm uppercase tracking-widest"
                >
                  Skip →
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Ambient Effects */}
        <div className="fixed top-1/4 -left-24 w-[600px] h-[600px] bg-primary/10 blur-[160px] pointer-events-none -z-10 animate-pulse-slow"></div>
        <div className="fixed bottom-0 -right-24 w-[700px] h-[700px] bg-tertiary/10 blur-[160px] pointer-events-none -z-10 animate-pulse-slow delay-700"></div>
      </main>
    </div>
  );
}
