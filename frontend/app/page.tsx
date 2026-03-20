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
  const [radarChart, setRadarChart] = useState<string | null>(null);
  
  const [manualText, setManualText] = useState("");
  const [pushbackText, setPushbackText] = useState("");
  const [isPushbacking, setIsPushbacking] = useState(false);

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
      setStage("conversation");
      updateAgentState(data.agent_id, "", "streaming");
      addLog(`${data.name} is asking a question...`);
    });

    eventSource.addEventListener("agent_token", (e: any) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent_id, data.token, "streaming");
    });

    eventSource.addEventListener("agent_question_done", (e: any) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent_id, "", "done");
      // Split by --- to only read the NEW question if it was appended
      enqueueSpeech(data.agent_id, data.question);
    });

    eventSource.addEventListener("waiting_for_answer", (e: any) => {
      const data = JSON.parse(e.data);
      setTimeout(() => {
        setWaitingForAnswer(true);
        setCurrentQuestion(data.question);
        setManualText("");
        addLog(`Waiting for your answer to ${data.agent_name}...`);
      }, 1000);
    });

    eventSource.addEventListener("pitcher_answer_received", (e: any) => {
       const data = JSON.parse(e.data);
       setWaitingForAnswer(false);
       addLog("Answer received by panel.");
    });

    eventSource.addEventListener("agent_reaction_start", (e: any) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent_id, "\n\nReaction: ", "streaming");
    });

    eventSource.addEventListener("agent_reaction_done", (e: any) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent_id, "", "done");
      enqueueSpeech(data.agent_id, data.reaction);
    });

    eventSource.addEventListener("interrupt_start", (e: any) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent_id, `\n\n[INTERRUPT]: ${data.question}`, "done");
      enqueueSpeech(data.agent_id, data.question);
      addLog(`${data.name} jumped in!`);
    });

    eventSource.addEventListener("conversation_complete", (e: any) => {
      addLog("Conversation complete. Final verdict incoming...");
    });

    eventSource.addEventListener("verdict_complete", (e: any) => {
      const data = JSON.parse(e.data);
      setVerdictData(data.verdict);
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

  const submitAnswer = async () => {
    if (!manualText) return;
    const ans = manualText;
    setWaitingForAnswer(false);
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
        setIsPushbacking(false);
        eventSource.close();
        enqueueSpeech("judge", "I have considered your point. " + fullPushbackResponse);
    });
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

          <PanelGrid panelState={panelState} onChallenge={() => {}} factChecks={{}} />
          
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
                <input 
                  type="text"
                  value={pitcherId}
                  onChange={(e) => setPitcherId(e.target.value)}
                  placeholder="Your Name (Optional)"
                  className="bg-gray-800 p-3 rounded-lg w-full text-sm text-amber-500 mb-4 border border-gray-700 outline-none"
                />
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

            {waitingForAnswer && (
              <div className="bg-gray-900 p-8 rounded-2xl border border-cyan-500/50 max-w-2xl w-full shadow-2xl animate-in fade-in zoom-in-95">
                 <h3 className="text-cyan-400 font-bold mb-4 uppercase text-xs tracking-widest">Question for you:</h3>
                 <p className="text-xl text-white font-semibold mb-6 italic">"{currentQuestion}"</p>
                 <textarea 
                    value={manualText}
                    onChange={(e) => setManualText(e.target.value)}
                    className="w-full bg-gray-800 p-4 rounded-xl text-white text-sm mb-4 border border-gray-700 outline-none h-24"
                    placeholder="Type or speak your answer..."
                 />
                 <div className="flex gap-4">
                    <button onClick={isRecording ? stopRecording : startRecording} className="bg-gray-700 text-white px-6 py-2 rounded-full font-bold">
                       {isRecording ? "Stop" : "Mic"}
                    </button>
                    <button onClick={submitAnswer} className="flex-1 bg-cyan-600 text-white px-8 py-2 rounded-full font-bold">
                       Submit Answer
                    </button>
                 </div>
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
            <VerdictCard verdict={verdictData} />
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
