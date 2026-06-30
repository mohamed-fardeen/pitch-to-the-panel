"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
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
import { FlowTimeline } from "../components/analytics/FlowTimeline";
import { MemoryPanel } from "../components/analytics/MemoryPanel";
import { NodeCard } from "../components/analytics/NodeCard";
import { AgentThoughtsPanel } from "../components/AgentThoughtsPanel";
import { GraphView } from "../components/graph/GraphView";
import { AgentIntelligencePanel } from "../components/intelligence/AgentIntelligencePanel";

const API_BASE = "http://localhost:8000/api";

export default function Home() {
  const { isRecording, transcript, startRecording, stopRecording } = useSpeechRecognition();
  const { speak, stopSpeaking } = useAgentVoice();
  const router = useRouter();
  
  const [provider, setProvider] = useState<Provider>("groq");
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
  const [difficulty, setDifficulty] = useState("venture");
  const [aggressiveness, setAggressiveness] = useState<number>(5);
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
  const [agentMemory, setAgentMemory] = useState<Record<string, any>>({});
  const [memoryHistory, setMemoryHistory] = useState<any[]>([]);
  const [activePersonas, setActivePersonas] = useState<Array<{id: string, name: string, role: string}>>([]);
  const [globalMemory, setGlobalMemory] = useState<any>({});

  const [currentlySpeaking, setCurrentlySpeaking] = useState<string | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const turnQueueRef = useRef<any[]>([]);
  const isProcessingQueueRef = useRef(false);

  // Connection state for the START DEBATE click — gives the user immediate
  // visual feedback while the SSE connection is being established.
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  // Mirror of `stage` for use inside async callbacks (where the closure would
  // otherwise capture a stale value).
  const stageRef = useRef(stage);
  useEffect(() => { stageRef.current = stage; }, [stage]);

  const speakAsync = (role: AgentRole, text: string): Promise<void> => {
    return new Promise((resolve) => {
      speak(role, text, resolve);
    });
  };

  const processNextTurn = async () => {
    if (isProcessingQueueRef.current || turnQueueRef.current.length === 0) return;
    isProcessingQueueRef.current = true;

    const turn = turnQueueRef.current.shift();
    if (!turn) {
      isProcessingQueueRef.current = false;
      return;
    }

    // 1. Set Status
    setCurrentlySpeaking(turn.agent_id);
    updateAgentState(turn.agent_id, turn.content, "streaming", true);

    // 2. Render in Chat
    setConversation((prev: ConversationTurn[]) => [...prev, {
      type: turn.turn_type,
      agent_id: turn.agent_id,
      agent_name: turn.agent_name,
      content: turn.content
    }]);

    // 3. Start TTS - await sequentially
    await speakAsync(turn.role as AgentRole, turn.content);

    // Notify backend that speech is complete to unlock the controller
    try {
      await fetch(`${API_BASE}/conversation/speech_complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId })
      });
    } catch (err) {
      console.error("Failed to notify speech complete:", err);
    }

    // 4. Clean up after speaking
    setTimeout(() => {
      // Clear agent text so bubble resets
      updateAgentState(turn.agent_id, "", "idle", true);
      setCurrentlySpeaking(null);
      isProcessingQueueRef.current = false;
      processNextTurn(); // Loop
    }, 100);
  };

  const enqueueTurn = (data: any) => {
    turnQueueRef.current.push({
      agent_id: data.agent_id,
      agent_name: data.agent_name || data.name || data.agent_id,
      role: data.role || "critic",
      content: data.content,
      turn_type: data.turn_type || data.type || "persona_response"
    });
    processNextTurn();
  };

  const cancelAllTurns = () => {
    stopSpeaking();
    turnQueueRef.current = [];
    isProcessingQueueRef.current = false;
    setCurrentlySpeaking(null);
  };

  const addLog = (msg: string) => setLogs((prev: string[]) => [...prev, msg]);

  useEffect(() => {
    if (transcript) setManualText(transcript);
  }, [transcript]);

  const updateAgentState = (agent: string, chunk: string, status: "idle" | "streaming" | "done" | "error", clear: boolean = false) => {
    setPanelState((prev: PanelState) => {
      const newState = { ...prev };
      
      // Update targeted agent
      const existing = newState[agent] || { text: "", status: "idle" as AgentStatus, role: "critic" as AgentRole, name: agent };
      newState[agent] = {
        ...existing,
        text: clear ? chunk : (chunk === "" ? existing.text : existing.text + chunk),
        status: status === "streaming" ? "speaking" : "idle"
      };

      // Set others to 'thinking' if debate is active and we are speaking
      if (status === "streaming") {
        Object.keys(newState).forEach(id => {
          if (id !== agent) newState[id].status = "thinking";
        });
      } else if (status === "idle") {
          // Reset others to idle if no one is speaking
          Object.keys(newState).forEach(id => {
            if (newState[id].status === "thinking") newState[id].status = "idle";
          });
      }

      return newState;
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
    
    // Phase 4: Load revised pitch if user clicked "Re-Pitch to Panel" from report page
    const rePitch = localStorage.getItem("pttp_repitch");
    if (rePitch) {
      localStorage.removeItem("pttp_repitch");
      setManualText(rePitch);
      // Don't change stage — let the user review the revised pitch and
      // click 'Start Debate' themselves. We do add a short toast so it's
      // obvious the text has been pre-loaded.
      addLog("✏️ Revised pitch loaded — review and click Start Debate.");
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
    setAgentMemory({});
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
    setAgentMemory({});
    debugStream.reset();
  };

  const finishPitch = async () => {
    stopRecording();
    const currentPitch = manualText;
    addLog("Evaluating Proposal...");
    setIsConnecting(true);
    setConnectionError(null);

    const url = new URL(`${API_BASE}/stream/main`);
    url.searchParams.append("session_id", sessionId);
    url.searchParams.append("pitch", currentPitch);
    url.searchParams.append("provider", provider);
    url.searchParams.append("mode", difficulty);
    url.searchParams.append("aggressiveness", String(aggressiveness));
    if (pitcherId) url.searchParams.append("pitcher_id", pitcherId);

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const eventSource = new window.EventSource(url.toString());
    eventSourceRef.current = eventSource;
    setIsStreaming(true);

    // Hard timeout: if the backend never sends the first event in 60s,
    // surface a clear error to the user instead of letting them stare at
    // an idle screen.
    const connectionTimeout = setTimeout(() => {
      if (eventSourceRef.current === eventSource && stageRef.current !== "hitl_summary") {
        console.error("[SSE] Connection timeout — no response in 60s");
        eventSource.close();
        eventSourceRef.current = null;
        setIsStreaming(false);
        setIsConnecting(false);
        setConnectionError(
          `Backend at ${API_BASE} did not respond within 60s. ` +
          `Is the FastAPI server running? Try: cd backend && uvicorn main:app --reload`
        );
      }
    }, 60_000);

    eventSource.onopen = () => {
      console.log("Stream connected for session:", sessionId);
      debugStream.setConnected(true);
    };

    eventSource.addEventListener("hitl_summary_approval", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Event received: hitl_summary_approval", data);
      clearTimeout(connectionTimeout);
      setIsConnecting(false);
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
        setActivePersonas(data.personas);
        data.personas.forEach((p: any) => {
          initialState[p.id] = { text: "", status: "idle", role: p.role as AgentRole, name: p.name, avatarUrl: p.avatar };
        });
      }
      setPanelState(initialState);
    });

    eventSource.addEventListener("agent_thinking", (e: any) => {
      const data = JSON.parse(e.data);
      setPanelState((prev: PanelState) => {
        const newState = { ...prev };
        const existing = newState[data.agent_id] || { text: "", status: "idle", role: "critic", name: data.name };
        newState[data.agent_id] = {
          ...existing,
          thinkingSignals: data.signals,
          status: "thinking"
        };
        return newState;
      });
    });

    eventSource.addEventListener("agent_start", (e: any) => {
        const data = JSON.parse(e.data);
        setActiveAgent({ id: data.agent_id, name: data.name });
    });

    eventSource.addEventListener("agent_token", (e: any) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent_id, data.token, "streaming");
    });

    eventSource.addEventListener("speech_start", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Speech started:", data.agent_id);
      setIsSpeaking(true);
      // Optional: highlight graph here if needed
    });

    eventSource.addEventListener("speech_stop", (e: any) => {
      console.log("Speech STOPPED (interrupt)");
      stopSpeaking();
      turnQueueRef.current = []; // Clear pending turns
      setIsSpeaking(false);
    });

    eventSource.addEventListener("speech_end", (e: any) => {
      console.log("Speech ends (resuming backend)");
      setIsSpeaking(false);
    });

    eventSource.addEventListener("agent_turn", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Event received: agent_turn", data);
      setCurrentAgentId(data.agent_id);
      setActiveAgent(null);

      const turnNeedsAnswer =
        data.type === "interviewer_invitation" ||
        data.type === "interviewer_question";

      if (turnNeedsAnswer) {
        setWaitingForAnswer(true);
        setAwaitingUserInput(true);
        setCurrentQuestion(data.content);
        setManualText("");
      }

      if (data.content) {
        enqueueTurn(data);
      }
      debugStream.pushEvent("agent_turn", data);
    });

    eventSource.addEventListener("waiting_for_pitcher", (e: any) => {
      const data = JSON.parse(e.data);
      console.info("[UI] awaiting_user_input triggered");
      setWaitingForAnswer(true);
      setAwaitingUserInput(true);
      setCurrentQuestion(data.question);
      setManualText("");
    });

    eventSource.addEventListener("black_swan_report", (e: any) => {
      const data = JSON.parse(e.data);
      // Store the insight for later use in the report — modal opens on verdict_complete
      setVerdictData((prev: any) => ({ ...prev, black_swan: data.insight }));
    });

    eventSource.addEventListener("verdict_complete", (e: any) => {
      const data = JSON.parse(e.data);
      clearTimeout(connectionTimeout);
      setIsConnecting(false);
      setVerdictData(data);
      setStage("verdict");
      setIsStreaming(false);
      // Stop any speaking agents before navigating
      cancelAllTurns();
      stopSpeaking();
      setIsSpeaking(false);
      setActiveAgent(null);

      // Navigate to report page after a short delay
      setTimeout(() => {
        router.push(`/report?sessionId=${sessionId}`);
      }, 1500);
    });

    // Named 'error' events are fatal errors sent by the server explicitly
    eventSource.addEventListener("error", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        console.error("Fatal stream error from server:", data);
        setConnectionError(typeof data === "string" ? data : (data?.data ?? JSON.stringify(data)));
      } catch {
        console.error("Fatal stream error:", e);
      }
      clearTimeout(connectionTimeout);
      eventSource.close();
      eventSourceRef.current = null;
      setIsStreaming(false);
      setIsConnecting(false);
      setActiveAgent(null);
    });

    // heartbeat events keep the connection alive — silently ignore them
    eventSource.addEventListener("heartbeat", () => {});

    // past_pitches_found — show toast when history is found
    eventSource.addEventListener("past_pitches_found", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        addLog(`📚 ${data.message}`);
        console.log("[Memory] Past pitches found:", data);
      } catch {}
    });

    // debug_node events feed the analytics execution graph
    eventSource.addEventListener("debug_node", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        debugStream.pushEvent("debug_node", data);
      } catch {}
    });

    // memory_update events update agent private thoughts
    eventSource.addEventListener("memory_update", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Memory update:", data);
      if (data.agent_memory) setAgentMemory(data.agent_memory);
      if (data.memory_history) setMemoryHistory(data.memory_history);
      if (data.memory) setGlobalMemory(data.memory);
    });

    // onerror fires on transient network issues — don't close if SSE is still trying to reconnect
    eventSource.onerror = (e: any) => {
      if (eventSource.readyState === EventSource.CLOSED) {
        console.error("SSE connection closed unexpectedly.");
        clearTimeout(connectionTimeout);
        eventSourceRef.current = null;
        setIsStreaming(false);
        setIsConnecting(false);
        setActiveAgent(null);
        // Only set the error if we never received any event (otherwise it's
        // likely a transient mid-session disconnect).
        if (stageRef.current === "idle" || stageRef.current === "pitching") {
          setConnectionError(
            `Lost connection to backend at ${API_BASE}. ` +
            `Is uvicorn still running on port 8000?`
          );
        }
      } else {
        // readyState is CONNECTING — browser is auto-reconnecting, don't interfere
        console.warn("SSE transient error, browser reconnecting...");
      }
    };

    eventSource.addEventListener("conversation_complete", (e: any) => {
      const data = JSON.parse(e.data);
      console.log("Event received: conversation_complete", data);
      // Panel is done — stop all TTS and clear active agents
      // The verdict_complete event will handle navigation to the report
      cancelAllTurns();
      setIsSpeaking(false);
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
    
    console.log("[UI] answer submitted:", ans.substring(0, 50));
    // If we're interrupting while somebody is talking, cancel current speech immediately
    if (isSpeaking || currentlySpeaking) {
      stopSpeaking();
      turnQueueRef.current = [];
      setIsSpeaking(false);
    }

    try {
      const resp = await fetch(`${API_BASE}/conversation/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: manualText,
          interrupt: false // HITL direct answer — NOT an interrupt
        })
      });

      const result = await resp.json().catch(() => ({}));
      if (!resp.ok || result.status !== "answer_received") {
        setAwaitingUserInput(true);
        setWaitingForAnswer(true);
        setConnectionError("The panel was not ready for that answer yet. Please send it again.");
        return;
      }

      setAwaitingUserInput(false);
      setWaitingForAnswer(false);
      setManualText("");
    } catch(e) {
      console.error("Failed to submit answer:", e);
      setAwaitingUserInput(true);
      setWaitingForAnswer(true);
    }
  };

  const submitSkip = async () => {
    console.log("[UI] answer skipped");
    if (isSpeaking || currentlySpeaking) {
      stopSpeaking();
      turnQueueRef.current = [];
      setIsSpeaking(false);
    }

    try {
      const resp = await fetch(`${API_BASE}/conversation/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: "[SKIPPED]",
          interrupt: false
        })
      });

      const result = await resp.json().catch(() => ({}));
      if (!resp.ok || result.status !== "answer_received") {
        setAwaitingUserInput(true);
        setWaitingForAnswer(true);
        setConnectionError("The panel was not ready for that answer yet. Please try again.");
        return;
      }

      setAwaitingUserInput(false);
      setWaitingForAnswer(false);
      setManualText("");
    } catch(e) {
      console.error("Failed to skip answer:", e);
      setAwaitingUserInput(true);
      setWaitingForAnswer(true);
    }
  };

  const submitInterrupt = async () => {
    if (!manualText) return;
    const msg = manualText;
    setIsInterrupting(false);
    
    // 1. Clear speech/queue immediately
    cancelAllTurns();
    addLog("Interrupting panel...");

    console.log("[UI] interrupt submitted:", msg.substring(0, 50));
    try {
      await fetch(`${API_BASE}/conversation/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: msg,
          interrupt: true
        })
      });

      // 2. Add user message to chat instantly
      setConversation((prev: ConversationTurn[]) => [
        ...prev, 
        { type: "pitcher_interrupt", agent_name: pitcherId || "Alex Chen", content: msg }
      ]);

      setManualText("");
    } catch(e) {
      console.error("Failed to submit interrupt:", e);
    }
  };

  const handleInterrupt = () => {
    cancelAllTurns();
    setIsInterrupting(true);
    setManualText("");
    console.log("[UI] interrupt flow triggered");
  };

  const endConversation = async () => {
    addLog("Ending conversation...");
    try {
      await fetch(`${API_BASE}/conversation/end`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId })
      });
      // Once ended, the backend will stream the verdict data via SSE.
      // The event listener for 'black_swan_report' or 'verdict_complete' will set the stage to 'verdict'.
    } catch (e) {
      console.error("Failed to end conversation:", e);
    }
  };

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
      // 1. Cancel ongoing speech for immediate impact
      cancelAllTurns();

      // 2. Submit rebuttal
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
      
      // 3. Render user interruption in chat
      setConversation((prev: ConversationTurn[]) => [
        ...prev, 
        { type: "pitcher_interrupt", agent_name: pitcherId || "Alex Chen", content: text }
      ]);
      
      // 4. Enqueue the AI rebuttal response
      enqueueTurn({
        agent_id: challengingAgentId,
        agent_name: data.name || challengingAgentId,
        content: data.agent_response,
        type: "persona_response"
      });
    } catch(e) {
      console.error("Rebuttal failed:", e);
    } finally {
      setIsRebutting(false);
      setChallengingAgentId(null);
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
        />

        <div className="bg-gradient-to-b from-surface-container-low to-transparent h-px w-full"></div>

        <div className="flex-1 overflow-hidden h-full relative">
          {view === "graph" ? (
             <GraphView debugStream={debugStream} />
          ) : view === "library" ? (
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
          ) : view === "intelligence" ? (
            <div className="p-8 h-full">
              <AgentIntelligencePanel
                memory={globalMemory}
                agentMemory={agentMemory}
                memoryHistory={memoryHistory}
                activeAgentId={currentlySpeaking}
                personas={activePersonas}
              />
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
                            <option value="spark">Spark — Creative Ideation</option>
                            <option value="venture">Venture — Business Valuation</option>
                            <option value="reality">Reality — Operational Risks</option>
                          </select>
                          <span className="material-symbols-outlined absolute right-8 bottom-6 text-slate-300 pointer-events-none">expand_more</span>
                        </div>

                        <div className="space-y-4">
                          <div className="flex items-center justify-between ml-2">
                            <label className="text-[11px] font-bold text-[#006948] uppercase tracking-[0.2em]">Panel Aggressiveness</label>
                            <span className="text-[10px] font-black text-slate-400 bg-slate-100 px-2 py-0.5 rounded-md uppercase">{aggressiveness <= 3 ? "Supportive" : aggressiveness >= 8 ? "Hostile" : "Balanced"} ({aggressiveness}/10)</span>
                          </div>
                          <input 
                            type="range" 
                            min="1" max="10" 
                            value={aggressiveness} 
                            onChange={(e) => setAggressiveness(parseInt(e.target.value))} 
                            className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-[#006948]"
                          />
                          <div className="flex justify-between text-[10px] font-bold text-slate-400 uppercase tracking-widest px-2 mt-2">
                            <span>Friendly</span>
                            <span>Adversarial</span>
                          </div>
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
                            disabled={!sessionId || !manualText || isConnecting}
                            className="flex-1 py-7 bg-[#006948] text-white font-extrabold text-2xl rounded-full shadow-2xl shadow-emerald-900/20 hover:scale-[1.02] active:scale-[0.98] transition-all flex items-center justify-center gap-4 uppercase tracking-tighter disabled:opacity-50 disabled:cursor-not-allowed"
                         >
                           {isConnecting ? (
                             <>
                               <span className="inline-block w-5 h-5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                               Connecting…
                             </>
                           ) : (
                             <>
                               Start Debate
                               <span className="material-symbols-outlined text-2xl">rocket_launch</span>
                             </>
                           )}
                         </button>
                       </div>
                    </div>

                    {/* Connection error banner */}
                    {connectionError && (
                      <div className="w-full max-w-4xl mt-6 bg-rose-50 border-2 border-rose-300 rounded-2xl p-6 flex items-start gap-4 animate-in fade-in slide-in-from-top-2">
                        <span className="material-symbols-outlined text-rose-500 text-3xl shrink-0">error</span>
                        <div className="flex-1 space-y-2">
                          <p className="text-sm font-black text-rose-700 uppercase tracking-widest">Connection Failed</p>
                          <p className="text-sm text-rose-600 font-medium leading-relaxed">{connectionError}</p>
                        </div>
                        <button
                          onClick={() => setConnectionError(null)}
                          className="text-rose-400 hover:text-rose-600 transition-colors shrink-0"
                        >
                          <span className="material-symbols-outlined">close</span>
                        </button>
                      </div>
                    )}

                    {/* Last status log entry */}
                    {logs.length > 0 && !connectionError && (
                      <div className="w-full max-w-4xl mt-4 text-center">
                        <p className="text-xs text-slate-400 font-mono">{logs[logs.length - 1]}</p>
                      </div>
                    )}
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
                  <div className="h-full flex px-12 pb-12 pt-6 overflow-hidden gap-6 animate-in fade-in duration-700">
                    {/* Agent Cards - Left Column */}
                    <div className="flex-[0.7] overflow-y-auto pr-6 custom-scrollbar pb-12">
                      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                         {Object.entries(panelState).map(([id, agent]) => (
                            <AgentCard key={id} id={id} name={agent.name} role={agent.role} status={agent.status} text={agent.text} avatarUrl={agent.avatarUrl} isChallenged={challengingAgentId === id} thinkingSignals={agent.thinkingSignals} />
                         ))}
                      </div>
                    </div>

                    {/* Live Feed - Middle Column */}
                    <div className="flex-[1.2] flex flex-col h-full bg-white border border-slate-100 rounded-[3rem] shadow-[0_20px_50px_rgba(0,0,0,0.04)] overflow-hidden">
                       <LiveFeed 
                          turns={conversation} 
                          agents={Object.values(panelState)} 
                          onJumpIn={handleInterrupt} 
                          isRecording={isRecording}
                          awaitingUserInput={awaitingUserInput}
                          isInterrupting={isInterrupting}
                          userInput={manualText}
                          onUserInputChange={(val) => setManualText(val)}
                          onSendAnswer={submitAnswer}
                          onSendInterrupt={submitInterrupt}
                          onCancelInterrupt={() => setIsInterrupting(false)}
                          currentQuestion={currentQuestion}
                          isStreaming={isStreaming}
                          activeAgent={activeAgent}
                          onSetAwaitingUserInput={setAwaitingUserInput}
                          onSkip={submitSkip}
                        />
                    </div>

                    {/* Agent Thoughts - Right Column */}
                    <div className="flex-[0.6]">
                      <AgentThoughtsPanel 
                        agentMemory={agentMemory}
                        agentsConfig={Object.keys(panelState).reduce((acc, id) => {
                          acc[id] = { name: panelState[id].name, role: panelState[id].role };
                          return acc;
                        }, {} as Record<string, { name: string; role: string }>)}
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
                onClick={() => {
                  cancelAllTurns();
                  endConversation();
                }} 
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
