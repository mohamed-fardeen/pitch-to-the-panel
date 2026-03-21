"use client";

import React, { useState, useEffect, useRef } from "react";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useAgentVoice, AgentRole } from "../hooks/useAgentVoice";
import { PanelGrid, PanelState } from "../components/PanelGrid";
import { LiveFeed } from "../components/LiveFeed";
import { VerdictCard } from "../components/VerdictCard";
import { ModelSelector, Provider } from "../components/ModelSelector";

const API_BASE = "http://localhost:8000/api";

interface ConversationTurn {
  type: "question" | "answer" | "reaction" | "interrupt_q" | "interrupt_a";
  agent_id?: string;
  agent_name?: string;
  content: string;
}

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

  const audioQueueRef = useRef<{role: AgentRole, text: string}[]>([]);
  const isPlayingRef = useRef(false);
  const challengingAgentIdRef = useRef<string | null>(null);
  const flowLockRef = useRef(false);

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

  const addLog = (msg: string) => setLogs((prev) => [...prev, msg]);

  useEffect(() => {
    if (transcript) setManualText(transcript);
  }, [transcript]);

  const updateAgentState = (agent: string, chunk: string, status: "idle" | "streaming" | "done" | "error") => {
    setPanelState((prev) => {
      const existing = prev[agent] || { text: "", status: "idle" };
      return {
        ...prev,
        [agent]: {
          text: chunk === "" ? existing.text : existing.text + chunk,
          status
        }
      };
    });
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
    setStage("conversation");
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
    });

    eventSource.addEventListener("domain_classified", (e: any) => {
      const data = JSON.parse(e.data);
      setDomainData(data);
      if (data.active_panel) {
        const initialState: PanelState = {};
        data.active_panel.forEach((id: string) => {
          initialState[id] = { text: "", status: "idle" };
        });
        setPanelState(initialState);
      }
      addLog(`Domain: ${data.sub_domain}`);
    });

    eventSource.addEventListener("agent_question_start", (e: any) => {
      const data = JSON.parse(e.data);
      const checkAndStart = () => {
        if (window.speechSynthesis.speaking || challengingAgentIdRef.current || needsSkipApprovalRef.current || flowLockRef.current) {
            setTimeout(checkAndStart, 500);
        } else {
            setStage("conversation");
            setCurrentAgentId(data.agent_id);
            updateAgentState(data.agent_id, "", "streaming");
            addLog(`${data.name} is asking a question...`);
            
            // Auto-scroll to the new agent
            const agentEl = document.getElementById(`agent-${data.agent_id}`);
            if (agentEl) agentEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      };
      checkAndStart();
    });

    eventSource.addEventListener("agent_token", (e: any) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent_id, data.token, "streaming");
    });

    eventSource.addEventListener("agent_question_done", (e: any) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent_id, "", "done");
      enqueueSpeech(data.agent_id, data.question);
      
      // LOCK Flow Instantly to prevent next agent from starting
      flowLockRef.current = true;
      
      const checkAndSetSkip = () => {
        if (window.speechSynthesis.speaking || audioQueueRef.current.length > 0) {
            setTimeout(checkAndSetSkip, 500);
        } else {
           setNeedsSkipApproval(true);
           needsSkipApprovalRef.current = true;
           setChallengingAgentId(data.agent_id);
           setChallengingAgentClaim(data.question);
        }
      };
      checkAndSetSkip();
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
      // Wait for speech to finish before asking for input
      const checkAndTrigger = () => {
        if (window.speechSynthesis.speaking || challengingAgentIdRef.current) {
          setTimeout(checkAndTrigger, 500);
        } else {
          triggerWaitingForAnswer(data);
        }
      };
      checkAndTrigger();
    });

    eventSource.addEventListener("pitcher_answer_received", (e: any) => {
       const data = JSON.parse(e.data);
       setWaitingForAnswer(false);
       addLog("Answer received by panel.");
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
        setRetryCounts(prev => ({
          ...prev,
          [currentAgentId]: currentCount + 1
        }));

        setPanelState(prev => {
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
    } catch(e) {
      addLog("Failed to send rebuttal.");
    } finally {
      setIsRebutting(false);
    }
  };

  const submitAnswer = async () => {
    if (!manualText) return;

    if (challengingAgentId) {
      submitRebuttal();
      return;
    }

    if (isWeakAnswer(manualText) && !weakAnswerDetected) {
      setWeakAnswerDetected(true);
      await getCoachHints();
      return;
    }

    const ans = manualText;
    setWaitingForAnswer(false);
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
    <main className="min-h-screen flex flex-col items-center bg-gray-950 p-6 relative">
      <header className="w-full max-w-7xl flex justify-between items-center mb-8 bg-gray-900/40 p-4 rounded-2xl border border-gray-800">
        <div>
          <h1 className="text-4xl font-black bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-cyan-500">
            Pitch to the Panel
          </h1>
          <p className="text-gray-400 text-sm mt-1 font-medium tracking-wide">Hybrid Sequential Debate System (v1)</p>
        </div>
        <ModelSelector 
          currentProvider={provider} 
          onChange={setProvider} 
          disabled={stage !== "idle"} 
        />
      </header>

      <div className="w-full max-w-7xl flex-grow flex flex-col lg:flex-row gap-8">
        <div className="w-full lg:w-2/3 flex flex-col space-y-6">
          <div className="flex justify-between items-center bg-gray-900 border border-gray-800 rounded-xl p-4 shadow-md">
             <div className="flex items-center gap-3">
                 <div className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"></div>
                 <span className="text-gray-300 text-sm font-semibold tracking-wide flex-shrink-0">Domain:</span>
                 {domainData ? (
                    <span className="text-indigo-400 font-bold">{domainData.sub_domain}</span>
                 ) : (
                    <span className="text-gray-600 italic text-sm">Waiting for pitch...</span>
                 )}
             </div>
          </div>

          <PanelGrid 
            panelState={panelState} 
            onChallenge={handleChallenge} 
            factChecks={factChecks} 
            challengingAgentId={challengingAgentId}
          />
          
          <div className="flex justify-center mt-4 pb-8">
            {stage === "idle" && (
              <button 
                onClick={startPitch}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-10 py-4 rounded-full font-bold text-lg shadow-[0_0_30px_rgba(16,185,129,0.3)] transition-all transform hover:-translate-y-1"
              >
                Start New Pitch
              </button>
            )}
            
            {stage === "pitching" && (
              <div className="text-center w-full max-w-md animate-in slide-in-from-bottom">
                <div className="flex gap-4 mb-4">
                  <input 
                    type="text"
                    value={pitcherId}
                    onChange={(e) => setPitcherId(e.target.value)}
                    placeholder="Your Name (Optional)"
                    className="bg-gray-800 p-3 rounded-lg w-1/2 text-sm text-amber-500 border border-gray-700 outline-none"
                  />
                  <select 
                    value={difficulty}
                    onChange={(e) => setDifficulty(e.target.value)}
                    className="bg-gray-800 p-3 rounded-lg w-1/2 text-sm text-gray-300 border border-gray-700 outline-none"
                  >
                    <option value="gentle">Gentle Panel</option>
                    <option value="standard">Standard Panel</option>
                    <option value="brutal">Brutally Honest</option>
                  </select>
                </div>
                <textarea 
                  value={manualText}
                  onChange={(e) => setManualText(e.target.value)}
                  className="bg-gray-800 p-5 rounded-xl h-36 w-full text-sm text-gray-300 border border-gray-700 resize-none outline-none"
                  placeholder="Describe your startup idea..."
                />
                <div className="flex gap-4 mt-6">
                  <button onClick={isRecording ? stopRecording : startRecording} className="px-6 py-3 rounded-full font-bold text-white bg-gray-700">
                    {isRecording ? "Stop" : "Speak"}
                  </button>
                  <button onClick={finishPitch} className="flex-1 bg-emerald-600 px-8 py-3 rounded-full font-bold text-white">
                    Start Debate
                  </button>
                </div>
              </div>
            )}
            
            {stage === "hitl_summary" && hitlData && (
               <div className="bg-gray-800 p-6 rounded-2xl border border-gray-700 shadow-xl w-full max-w-2xl text-left">
                 <h2 className="text-lg font-black text-amber-500 mb-2">Is this your pitch?</h2>
                 <textarea 
                   value={hitlData.summary}
                   onChange={(e) => setHitlData({ ...hitlData, summary: e.target.value })}
                   className="w-full bg-gray-900 text-gray-200 text-sm border border-gray-700 rounded-xl p-4 h-32 mb-4 outline-none"
                 />
                 <button onClick={approveSummary} className="w-full bg-amber-600 text-white px-6 py-3 rounded-full font-bold">
                   Confirm Summary & Start Panel
                 </button>
               </div>
            )}

            {needsSkipApproval && !challengingAgentId && (
              <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-6 animate-in fade-in">
                  <div className="bg-gray-900 border border-gray-700/50 p-8 rounded-3xl max-w-lg w-full shadow-[0_20px_50px_rgba(0,0,0,0.5)] flex flex-col items-center text-center">
                      <div className="w-16 h-16 bg-amber-500/20 rounded-full flex items-center justify-center mb-6">
                        <span className="text-3xl font-bold text-amber-500">?</span>
                      </div>
                      <h3 className="text-2xl font-black text-white mb-2">Interact or Skip?</h3>
                      <p className="text-gray-400 text-sm mb-8 leading-relaxed">
                        The panelist has finished speaking. Would you like to interact (mic/coach), or skip to the next turn?
                      </p>
                      
                      <div className="w-full flex gap-4">
                        <button 
                          onClick={handleSkip}
                          className="flex-1 bg-gray-800 hover:bg-gray-700 text-gray-300 py-4 rounded-2xl font-bold border border-gray-700 transition-all text-sm"
                        >
                          Skip →
                        </button>
                        <button 
                          onClick={handleChallengeAction}
                          className="flex-1 bg-rose-600 hover:bg-rose-500 text-white py-4 rounded-2xl font-bold flex items-center justify-center gap-2 transition-all shadow-lg hover:shadow-rose-600/20 text-sm"
                        >
                          🗨 Interact
                        </button>
                      </div>
                  </div>
              </div>
            )}

            {challengingAgentId && (
              <div className="bg-rose-900/30 border border-rose-500/50 p-6 rounded-2xl max-w-2xl w-full shadow-2xl animate-in fade-in slide-in-from-top-4 mb-4">
                  <div className="flex justify-between items-center mb-4">
                     <h3 className="text-rose-400 font-bold uppercase text-xs tracking-widest flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
                        Interactive Challenge Mode: {challengingAgentId}
                     </h3>
                     <button onClick={endChallengeMode} className="text-gray-400 hover:text-white text-[10px] uppercase font-bold border border-gray-700 px-3 py-1 rounded-full transition-all">
                        End Challenge
                     </button>
                  </div>
                  <p className="text-lg text-white font-medium mb-6 italic border-l-2 border-rose-500 pl-4 py-1">
                    "{challengingAgentClaim}"
                  </p>
                  
                  <textarea 
                     value={manualText}
                     onChange={(e) => setManualText(e.target.value)}
                     className="w-full bg-gray-800/50 p-4 rounded-xl text-white text-sm mb-4 border border-rose-500/20 outline-none h-24 focus:border-rose-500/50 transition-all shadow-inner"
                     placeholder="Speak your rebuttal into the mic..."
                  />

                  <div className="flex gap-4">
                     <button 
                       disabled={isRebutting}
                       onClick={isRecording ? stopRecording : startRecording} 
                       className="bg-gray-700 text-white px-6 py-2 rounded-full font-bold disabled:opacity-50 shadow-lg"
                     >
                        {isRecording ? "Stop" : "Mic"}
                     </button>
                     
                     <button 
                       onClick={getCoachHints} 
                       disabled={coachLoading}
                       className="bg-gray-800 text-amber-400 px-6 py-2 rounded-full font-bold border border-gray-700 hover:bg-gray-700 transition-colors disabled:opacity-50"
                     >
                        {coachLoading ? "..." : "💡 Help"}
                     </button>

                     <div className="flex-grow"></div>
                     <button 
                       onClick={submitRebuttal} 
                       disabled={isRebutting || !manualText}
                       className="bg-rose-600 text-white px-8 py-2 rounded-full font-bold hover:bg-rose-500 transition-colors disabled:opacity-50 shadow-[0_0_15px_rgba(225,29,72,0.4)]"
                     >
                        {isRebutting ? "..." : "Reply →"}
                     </button>
                  </div>

                  {coachHints && (
                    <div className="mt-4 p-4 bg-gray-900/80 rounded-xl text-gray-300 text-sm border border-amber-500/30 animate-in fade-in zoom-in-95">
                      <p className="font-bold text-amber-400 mb-2 flex items-center gap-2 uppercase tracking-tighter text-[10px]">
                        💡 Coach's Review
                      </p>
                      <ul className="space-y-1 list-disc list-inside italic opacity-80 leading-relaxed">
                        {coachHints.split('\n').filter(l => l.trim().length > 5).map((hint, i) => (
                          <li key={i}>{hint.replace(/^-?\s*Think about:\s*/i, '').trim()}</li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
            )}

          </div>
        </div>

        <div className="w-full lg:w-1/3 flex flex-col space-y-6">
          <LiveFeed logs={logs} />
          {radarChart && (
             <div className="bg-gray-900 rounded-2xl p-6 border border-gray-700/50 flex flex-col items-center">
                 <h3 className="text-gray-400 font-bold mb-4 tracking-wider uppercase text-xs w-full text-left">Pitch Score</h3>
                 <img src={`data:image/png;base64,${radarChart}`} alt="Radar" className="w-full max-w-xs" />
             </div>
          )}
        </div>
      </div>

      {verdictData && (
         <div className="w-full max-w-7xl flex flex-col gap-6 items-center mt-6">
            {showVerdictModal && <VerdictCard verdict={verdictData} sessionId={sessionId} onClose={() => setShowVerdictModal(false)} />}
            {!showVerdictModal && (
              <div className="w-full max-w-2xl flex justify-end">
                 <button onClick={() => setShowVerdictModal(true)} className="text-sm text-cyan-400 bg-gray-800 px-4 py-2 rounded shadow hover:bg-gray-700">View Verdict</button>
              </div>
            )}
            <div className="bg-gray-900 p-6 rounded-2xl border border-gray-800 shadow-xl w-full max-w-2xl">
              <h2 className="text-lg font-black text-rose-500 mb-2">Negotiate Verdict</h2>
              <textarea 
                  value={pushbackText}
                  onChange={(e) => setPushbackText(e.target.value)}
                  className="w-full bg-gray-800 text-gray-200 text-sm border border-gray-700 rounded-xl p-4 h-24 mb-4 outline-none"
                  placeholder="Why should the judge reconsider?"
              />
              <button disabled={isPushbacking} onClick={submitPushback} className="w-full bg-rose-600 text-white px-6 py-3 rounded-full font-bold">
                {isPushbacking ? 'Negotiating...' : 'Submit Pushback'}
              </button>
            </div>
         </div>
      )}
    </main>
  );
}
