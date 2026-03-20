"use client";

import React, { useState, useEffect, useRef } from "react";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useAgentVoice, AgentRole } from "../hooks/useAgentVoice";
import { PanelGrid, PanelState } from "../components/PanelGrid";
import { LiveFeed } from "../components/LiveFeed";
import { VerdictCard } from "../components/VerdictCard";
import { ModelSelector, Provider } from "../components/ModelSelector";

const API_BASE = "http://localhost:8000/api";

export default function Home() {
  const { isRecording, transcript, startRecording, stopRecording } = useSpeechRecognition();
  const { speak, stopSpeaking } = useAgentVoice();
  
  const [provider, setProvider] = useState<Provider>("anthropic");
  const [stage, setStage] = useState<"idle" | "pitching" | "hitl_summary" | "round1" | "hitl_steer" | "interruption" | "answering" | "round2" | "verdict">("idle");
  const [panelState, setPanelState] = useState<PanelState>({});
  const [logs, setLogs] = useState<string[]>([]);
  
  const [interruptionQuestion, setInterruptionQuestion] = useState<{ agent: string, question: string } | null>(null);
  const [verdictData, setVerdictData] = useState<string | null>(null);
  const [domainData, setDomainData] = useState<any>(null);
  const [hitlData, setHitlData] = useState<any>(null);
  const [sessionId, setSessionId] = useState("");
  const [pitcherId, setPitcherId] = useState("");
  const [radarChart, setRadarChart] = useState<string | null>(null);
  
  const [factChecks, setFactChecks] = useState<Record<string, string>>({});
  const [sketchImage, setSketchImage] = useState<string | null>(null);
  const [isGenerating3D, setIsGenerating3D] = useState(false);
  const [model3D, setModel3D] = useState<string | null>(null);

  const [steerData, setSteerData] = useState({ choice: "proceed", clarification: "", target_agent: "" });
  const [pushbackText, setPushbackText] = useState("");
  const [isPushbacking, setIsPushbacking] = useState(false);
  
  const [savedPitch, setSavedPitch] = useState("");
  const [savedAnswer, setSavedAnswer] = useState("");
  const [manualText, setManualText] = useState("");

  const audioQueueRef = useRef<{role: AgentRole, text: string}[]>([]);
  const isPlayingRef = useRef(false);

  const playNextInQueue = () => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return;
    isPlayingRef.current = true;
    const next = audioQueueRef.current.shift();
    if (next) {
      speak(next.role, next.text, () => {
        setTimeout(() => {
          isPlayingRef.current = false;
          playNextInQueue();
        }, 100); // Brief natural pause between agents
      });
    }
  };

  const enqueueSpeech = (role: AgentRole, text: string) => {
    audioQueueRef.current.push({ role, text });
    playNextInQueue();
  };

  const interruptSpeech = (role: AgentRole, text: string) => {
    stopSpeaking();
    audioQueueRef.current = [];
    audioQueueRef.current.push({ role, text });
    isPlayingRef.current = false;
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
    addLog("Ready. Speak or type your pitch...");
  };

  const finishPitch = async () => {
    stopRecording();
    setStage("round1");
    setSavedPitch(manualText);
    addLog(`Pitch complete. Captured ${manualText.split(" ").length} words.`);
    addLog("Panel evaluating pitch (Round 1)...");

    try {
      const url = new URL(`${API_BASE}/stream/round1`);
      url.searchParams.append("session_id", sessionId || Math.random().toString(36).substring(2, 10));
      url.searchParams.append("pitch", manualText || "I am pitching a new AI product.");
      url.searchParams.append("provider", provider);

      const eventSource = new window.EventSource(url.toString());

      eventSource.addEventListener("hitl_summary_approval", (e: any) => {
         const data = JSON.parse(e.data);
         setHitlData(data);
         setStage("hitl_summary");
         addLog("Waiting for Pitch Summary Approval...");
      });

      eventSource.addEventListener("competitor_research_complete", (e: any) => {
         const data = JSON.parse(e.data);
         addLog(data.status);
      });

      eventSource.addEventListener("returning_pitcher", (e: any) => {
         const data = JSON.parse(e.data);
         addLog(`[System] Returning Pitcher Detected: ${data.pitch_count} past sessions.`);
      });

      eventSource.addEventListener("domain_classified", (e: any) => {
         const data = JSON.parse(e.data);
         setDomainData(data);
         addLog(`Domain Classified: ${data.sub_domain} (${data.business_model.toUpperCase()})`);
      });

      const r1SpokenAgents = new Set<string>();

      eventSource.addEventListener("message", (e) => {
        const data = JSON.parse(e.data);
        updateAgentState(data.agent, data.chunk, data.state);
        if (data.state === "done" && !r1SpokenAgents.has(data.agent)) {
          r1SpokenAgents.add(data.agent);
          addLog(`[${data.agent}] finished generating.`);
          // Use a short delay to let the final updateAgentState flush first
          setTimeout(() => {
            setPanelState(prev => {
              const finalResponseText = prev[data.agent]?.text || "";
              if (finalResponseText) {
                enqueueSpeech(data.agent as AgentRole, finalResponseText);
              }
              return prev;
            });
          }, 50);
        }
      });

      eventSource.addEventListener("error", (e: any) => {
        if (e.data) {
          try {
            const data = JSON.parse(e.data);
            updateAgentState(data.agent, `\n\n[System Error: ${data.error}]`, "error");
            addLog(`Error for ${data.agent}: ${data.error}`);
          } catch(err) {}
        } else {
          console.error("SSE Error", e);
          addLog("SSE Connection Error. Is the backend running and API keys set?");
          eventSource.close();
        }
      });

      let handledSteer = false;

      const interval = setInterval(() => {
        let isTextDone = false;
        let currentStates: PanelState = {};
        
        setPanelState(current => {
          const agentKeys = Object.keys(current);
          isTextDone = agentKeys.length === 6 && agentKeys.every(k => current[k].status === "done" || current[k].status === "error");
          currentStates = current;
          return current;
        });
          
        if (isTextDone && !handledSteer) {
          // Wait for the audio queue to fully drain before showing steer panel
          const audioEmpty = audioQueueRef.current.length === 0 && !isPlayingRef.current;
          if (audioEmpty) {
            handledSteer = true;
            clearInterval(interval);
            eventSource.close();
            setStage("hitl_steer");
            addLog("Please choose how to steer the debate.");

            // Trigger Radar Chart generation in background
            addLog("Scoring Agent is evaluating the pitch...");
            const agentsTextMap = {} as Record<string, string>;
            Object.keys(currentStates).forEach(k => { agentsTextMap[k] = currentStates[k].text; });
            fetch(`${API_BASE}/pitch/score`, {
               method: "POST", headers: { "Content-Type": "application/json" },
               body: JSON.stringify({ pitch: manualText || "PITCH", round1_responses: agentsTextMap, provider })
            }).then(r => r.json())
              .then(data => { if (data.image) setRadarChart(data.image); });
          }
        }
      }, 500);
      
    } catch (error) {
      addLog("Failed to reach API.");
    }
  };

  const answerQuestion = () => {
    setStage("answering");
    setManualText("");
    addLog("Ready for answer...");
    stopSpeaking(); // stop asking the question if user clicks early
  };

  const finishAnswer = () => {
    stopRecording();
    setSavedAnswer(manualText);
    setStage("round2");
    addLog("Submitting answer to panel (Round 2)...");
    
    setPanelState(prev => {
      const next: PanelState = {};
      Object.keys(prev).forEach(k => {
        next[k] = { text: prev[k].text + "\n\n---\n\n", status: "idle" };
      });
      return next;
    });

    const r1 = Object.keys(panelState).reduce((acc, k) => {
      acc[k] = panelState[k].text;
      return acc;
    }, {} as Record<string, string>);

    const url = new URL(`${API_BASE}/stream/round2`);
    url.searchParams.append("pitch", savedPitch || "PITCH");
    url.searchParams.append("answer", manualText || "ANSWER");
    url.searchParams.append("round1_responses", JSON.stringify(r1));
    url.searchParams.append("provider", provider);

    const eventSource = new window.EventSource(url.toString());

    const r2SpokenAgents = new Set<string>();

    eventSource.addEventListener("message", (e) => {
      const data = JSON.parse(e.data);
      updateAgentState(data.agent, data.chunk, data.state);
      
      if (data.state === "done" && !r2SpokenAgents.has(data.agent)) {
         r2SpokenAgents.add(data.agent);
         setTimeout(() => {
           setPanelState(prev => {
              const fullText = prev[data.agent]?.text || "";
              const newText = fullText.split("---\n\n")[1] || "";
              if (newText) {
                 enqueueSpeech(data.agent as AgentRole, newText);
              }
              return prev;
           });
         }, 50);
      }
    });

    const interval = setInterval(async () => {
      let isDone = false;
      let currentStates: PanelState = {};
      
      setPanelState(current => {
        const agents = ["vc", "enthusiastic", "hostile", "expert", "competitor", "beginner"];
        isDone = agents.every(a => current[a]?.status === "done" || current[a]?.status === "error");
        currentStates = current;
        return current;
      });
      
      if (isDone) {
        if (audioQueueRef.current.length === 0 && !isPlayingRef.current) {
           clearInterval(interval);
           eventSource.close();
           generateVerdict(currentStates, r1);
        }
      }
    }, 500);
  };

  const fetchQuestion = (currentStates: PanelState) => {
      const agentsTextMap = {} as Record<string, string>;
      Object.keys(currentStates).forEach(k => { agentsTextMap[k] = currentStates[k].text; });
      fetch(`${API_BASE}/question`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pitch: savedPitch || "PITCH", round1_responses: agentsTextMap, provider, session_id: sessionId })
      })
      .then(r => r.json())
      .then(data => {
         // Wait for audio queue to be empty
         const checkQueue = setInterval(() => {
            if (audioQueueRef.current.length === 0 && !isPlayingRef.current) {
                clearInterval(checkQueue);
                setStage("interruption");
                setInterruptionQuestion({ agent: data.selected_agent, question: data.question });
                addLog(`[${data.selected_agent}] wants to challenge you.`);
                interruptSpeech(data.selected_agent as AgentRole, data.question);
            }
         }, 500);
      })
      .catch(() => {
          setStage("interruption");
          setInterruptionQuestion({ agent: "vc", question: "Can you explain monetization?" });
      });
  };

  const submitSteer = async () => {
      setStage("round1"); // Transitionary state before fetching ends
      addLog("Sending steer choice...");
      try {
        await fetch(`${API_BASE}/pitch/steer`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, choice: steerData.choice, clarification: steerData.clarification, target_agent_id: steerData.target_agent })
        });
      } catch (e) {}
      fetchQuestion(panelState);
  };

  const approveSummary = async () => {
    if (!hitlData) return;
    setStage("round1");
    addLog("Pitch summary approved. Proceeding to panel...");
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
    } catch(e) {
      addLog("Failed to send approval.");
    }
  };

  const generateVerdict = async (currentStates: PanelState, r1: Record<string, string>) => {
    setStage("verdict");
    addLog("Judge is summarizing the verdict...");
    
    const r2 = Object.keys(currentStates).reduce((acc, k) => {
      acc[k] = currentStates[k].text.split("---\n\n")[1] || "";
      return acc;
    }, {} as Record<string, string>);

    try {
        const res = await fetch(`${API_BASE}/verdict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            pitch: savedPitch,
            answer: savedAnswer,
            round1_responses: r1,
            round2_responses: r2,
            provider
        })
        });
        
        const data = await res.json();
        addLog("Verdict generated.");
        setVerdictData(data.verdict);
        
        stopSpeaking();
        audioQueueRef.current = [];
        enqueueSpeech("judge", data.verdict);
    } catch (e) {
        setVerdictData("Your strongest point: The problem space resonates.\nYour biggest weakness: API Connection Error.\nBefore your next pitch: Check your backend server is running.");
    }
  };

  const submitPushback = async () => {
    if (!pushbackText) return;
    setIsPushbacking(true);
    addLog("Sending pushback to Judge...");
    
    // gather responses
    const r1 = Object.keys(panelState).reduce((acc, k) => { acc[k] = panelState[k].text.split("---\n\n")[0] || ""; return acc; }, {} as Record<string, string>);
    const r2 = Object.keys(panelState).reduce((acc, k) => { acc[k] = panelState[k].text.split("---\n\n")[1] || ""; return acc; }, {} as Record<string, string>);
    
    try {
        const res = await fetch(`${API_BASE}/pitch/pushback`, {
           method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify({ session_id: sessionId, pushback: pushbackText, pitch: savedPitch, answer: savedAnswer, round1_responses: r1, round2_responses: r2, provider })
        });
        const data = await res.json();
        setVerdictData(data.verdict);
        setPushbackText("");
        addLog("Judge adjusted the verdict based on your pushback.");
        stopSpeaking();
        enqueueSpeech("judge", data.verdict);
    } catch (e) {}
    setIsPushbacking(false);
  };

  const handleChallenge = async (agentId: string, claim: string) => {
     addLog(`Fact-checking [${agentId}]'s claim...`);
     try {
        const res = await fetch(`${API_BASE}/pitch/challenge`, {
           method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify({ session_id: sessionId, agent_id: agentId, agent_claim: claim, challenge_text: "Verify this claim strictly.", provider })
        });
        const data = await res.json();
        setFactChecks(prev => ({ ...prev, [agentId]: data.fact_check_result }));
        addLog(`Fact-check complete for ${agentId}.`);
     } catch (e) {
        addLog("Fact-check failed.");
     }
  };

  const downloadReport = async () => {
    addLog("Generating PDF report...");
    const r1 = Object.keys(panelState).reduce((acc, k) => { acc[k] = panelState[k].text.split("---\n\n")[0] || ""; return acc; }, {} as Record<string, string>);
    const r2 = Object.keys(panelState).reduce((acc, k) => { acc[k] = panelState[k].text.split("---\n\n")[1] || ""; return acc; }, {} as Record<string, string>);
    
    const res = await fetch(`${API_BASE}/pitch/report`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pitch: savedPitch, round1_responses: r1, round2_responses: r2, verdict: verdictData, radar_chart_b64: radarChart })
    });
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "Pitch_Report.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    addLog("PDF downloaded successfully!");
  };

  const submitSketch = async (url: string) => {
    if (!url) return;
    setIsGenerating3D(true);
    addLog("Meshy is generating your 3D model (this takes ~60s)...");
    try {
        const res = await fetch(`${API_BASE}/pitch/generate-3d`, {
           method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify({ image_url: url })
        });
        const data = await res.json();
        if (data.model_url) {
            setModel3D(data.model_url);
            setSketchImage(data.thumbnail_url);
            addLog("3D Model Generated successfully!");
        } else {
            addLog("Failed to generate 3D model: " + (data.error || "Unknown error"));
        }
    } catch (e) {
        addLog("3D Generation error.");
    }
    setIsGenerating3D(false);
  };

  return (
    <main className="min-h-screen flex flex-col items-center bg-gray-950 p-6 relative">
      <header className="w-full max-w-7xl flex justify-between items-center mb-8 bg-gray-900/40 p-4 rounded-2xl border border-gray-800">
        <div>
          <h1 className="text-4xl font-black bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-cyan-500">
            Pitch to the Panel
          </h1>
          <p className="text-gray-400 text-sm mt-1 font-medium tracking-wide">Get real, adversarial reactions to your startup idea in 90 seconds.</p>
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
                    <span className="text-indigo-400 font-bold">{domainData.sub_domain} <span className="text-gray-500 font-normal">({domainData.business_model.toUpperCase()})</span></span>
                 ) : (
                    <span className="text-gray-600 italic text-sm">{stage === "idle" || stage === "pitching" ? "Waiting for pitch..." : "Classifying..."}</span>
                 )}
             </div>
             {domainData && <span className="text-xs font-mono bg-gray-800 text-gray-500 px-3 py-1 rounded-md border border-gray-700">{domainData.panel_mode.toUpperCase()}</span>}
          </div>

          <PanelGrid panelState={panelState} onChallenge={handleChallenge} factChecks={factChecks} />
          
          <div className="flex justify-center mt-4 pb-8">
            {stage === "idle" && (
              <button 
                onClick={startPitch}
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-10 py-4 rounded-full font-bold text-lg shadow-[0_0_30px_rgba(16,185,129,0.3)] hover:shadow-[0_0_40px_rgba(16,185,129,0.5)] transition-all flex items-center gap-3 transform hover:-translate-y-1"
              >
                <div className="w-3 h-3 bg-white rounded-full animate-pulse"></div> 
                Start Pitching (60s)
              </button>
            )}
            
            {stage === "pitching" && (
              <div className="text-center w-full max-w-md animate-in slide-in-from-bottom">
                <p className="text-emerald-400 font-bold mb-3 tracking-widest uppercase flex items-center justify-center gap-2">
                    {isRecording && <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block animate-ping"></span>}
                    {isRecording ? "Listening..." : "Type or Speak"}
                </p>
                <input 
                  type="text"
                  value={pitcherId}
                  onChange={(e) => setPitcherId(e.target.value)}
                  placeholder="Your Name or ID (for returning memory)"
                  className="bg-gray-800 p-3 rounded-lg text-left w-full text-sm text-amber-500 font-bold border border-gray-700 shadow-inner mb-4 focus:border-amber-500 focus:outline-none"
                />
                <textarea 
                  value={manualText}
                  onChange={(e) => setManualText(e.target.value)}
                  className="bg-gray-800 p-5 rounded-xl text-left h-36 w-full text-sm text-gray-300 border border-gray-700 shadow-inner resize-none focus:border-emerald-500 focus:outline-none placeholder-gray-500"
                  placeholder="Speak or type the problem you are solving..."
                />
                <div className="flex gap-4 mt-6">
                  <button 
                    onClick={isRecording ? stopRecording : startRecording}
                    className={`px-6 py-3 rounded-full font-bold text-white transition-all shadow-md ${isRecording ? 'bg-rose-600 hover:bg-rose-500' : 'bg-gray-700 hover:bg-gray-600'}`}
                  >
                    {isRecording ? "Stop Mic" : "Start Mic"}
                  </button>
                  <button 
                    onClick={finishPitch}
                    className="flex-1 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 px-8 py-3 rounded-full font-bold text-white transition-all shadow-md"
                  >
                    Submit Pitch
                  </button>
                </div>
              </div>
            )}
            
            {stage === "hitl_summary" && hitlData && (
               <div className="bg-gray-800 p-6 rounded-2xl border border-gray-700 shadow-xl w-full max-w-2xl text-left animate-in fade-in zoom-in-95 mx-auto mt-4">
                 <h2 className="text-lg uppercase tracking-widest font-black text-amber-500 mb-2">Review Pitch Summary</h2>
                 <p className="text-sm text-gray-400 mb-4">{hitlData.message}</p>
                 
                 <div className="flex justify-between items-center bg-gray-900 border border-gray-800 rounded-xl p-3 mb-4">
                    <span className="text-gray-300 text-sm font-semibold tracking-wide">Domain Identified:</span>
                    <span className="text-indigo-400 font-bold text-sm bg-gray-800 px-2 py-1 rounded">{hitlData.domain?.sub_domain}</span>
                 </div>

                 <textarea 
                   value={hitlData.summary}
                   onChange={(e) => setHitlData({ ...hitlData, summary: e.target.value })}
                   className="w-full bg-gray-900 text-gray-200 text-sm border border-gray-700 rounded-xl p-4 h-32 mb-4 focus:border-amber-500 focus:outline-none shadow-inner resize-none"
                 />
                 <button onClick={approveSummary} className="w-full bg-gradient-to-r from-amber-600 to-orange-500 hover:from-amber-500 hover:to-orange-400 text-white px-6 py-3 rounded-full font-bold transition-all shadow-md">
                   Update & Proceed to Panel
                 </button>
               </div>
            )}

            {stage === "hitl_steer" && (
               <div className="bg-gray-800 p-6 rounded-2xl border border-gray-700 shadow-xl w-full max-w-2xl text-left animate-in fade-in zoom-in-95 mx-auto mt-4">
                 <h2 className="text-lg uppercase tracking-widest font-black text-amber-500 mb-2">Steer The Debate</h2>
                 <p className="text-sm text-gray-400 mb-4">Round 1 complete. Before they ask a question, choose how you want to proceed:</p>
                 
                 <div className="flex flex-col gap-3 mb-4">
                    <label className="flex items-center gap-3 bg-gray-900 p-3 rounded-xl border border-gray-700 cursor-pointer hover:bg-gray-800">
                       <input type="radio" name="steer" checked={steerData.choice === "proceed"} onChange={() => setSteerData({...steerData, choice: "proceed"})} className="text-emerald-500 w-5 h-5 focus:ring-emerald-500 focus:ring-offset-gray-900" />
                       <span className="text-gray-200 font-semibold">Proceed Normally</span>
                    </label>
                    <label className="flex flex-col gap-2 bg-gray-900 p-3 rounded-xl border border-gray-700 cursor-pointer hover:bg-gray-800">
                       <div className="flex items-center gap-3">
                           <input type="radio" name="steer" checked={steerData.choice === "clarify"} onChange={() => setSteerData({...steerData, choice: "clarify"})} className="text-emerald-500 w-5 h-5 focus:ring-emerald-500 focus:ring-offset-gray-900" />
                           <span className="text-gray-200 font-semibold">Clarify Misunderstanding First</span>
                       </div>
                       {steerData.choice === "clarify" && (
                           <input type="text" value={steerData.clarification} onChange={(e) => setSteerData({...steerData, clarification: e.target.value})} placeholder="e.g. Actually my margin is 50%, not 20%..." className="bg-gray-800 text-sm text-white p-2 border border-gray-600 rounded mt-2 outline-none w-full" />
                       )}
                    </label>
                    <label className="flex flex-col gap-2 bg-gray-900 p-3 rounded-xl border border-gray-700 cursor-pointer hover:bg-gray-800">
                       <div className="flex items-center gap-3">
                           <input type="radio" name="steer" checked={steerData.choice === "address"} onChange={() => setSteerData({...steerData, choice: "address"})} className="text-emerald-500 w-5 h-5 focus:ring-emerald-500 focus:ring-offset-gray-900" />
                           <span className="text-gray-200 font-semibold">Address Specific Agent</span>
                       </div>
                       {steerData.choice === "address" && (
                           <div className="flex gap-2 w-full mt-2">
                               <select value={steerData.target_agent} onChange={(e) => setSteerData({...steerData, target_agent: e.target.value})} className="bg-gray-800 text-sm py-2 px-3 focus:outline-none border border-gray-600 rounded text-white">
                                  <option value="">Select Agent</option>
                                  <option value="vc">VC</option><option value="expert">Expert</option><option value="competitor">Competitor</option><option value="hostile">Hostile</option><option value="beginner">Beginner</option>
                               </select>
                               <input type="text" value={steerData.clarification} onChange={(e) => setSteerData({...steerData, clarification: e.target.value})} placeholder="Why..." className="flex-1 bg-gray-800 text-sm text-white p-2 border border-gray-600 rounded outline-none w-full" />
                           </div>
                       )}
                    </label>
                 </div>
                 
                 <button onClick={submitSteer} className="w-full bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white px-6 py-3 rounded-full font-bold transition-all shadow-md mt-2">
                   Confirm Steering
                 </button>
               </div>
            )}

            {stage === "interruption" && interruptionQuestion && (
              <div className="bg-gradient-to-br from-rose-950/80 to-slate-900 border border-rose-800/50 p-8 rounded-2xl max-w-2xl w-full text-center animate-in zoom-in-95 flex flex-col items-center shadow-2xl">
                <div className="uppercase tracking-[0.2em] text-rose-400 font-extrabold text-xs mb-6">Hardest Question</div>
                <blockquote className="text-2xl font-semibold text-rose-50 italic mb-8 leading-snug">
                  "{interruptionQuestion.question}"
                </blockquote>
                <p className="text-rose-200/50 text-sm mb-6 font-medium">You have 20 seconds to answer.</p>
                <button 
                  onClick={answerQuestion}
                  className="bg-rose-600 hover:bg-rose-500 px-8 py-4 text-lg rounded-full font-bold shadow-[0_0_20px_rgba(225,29,72,0.4)] transition-all transform hover:scale-105"
                >
                  Answer Out Loud or Type
                </button>
              </div>
            )}
            
            {stage === "answering" && (
              <div className="text-center w-full max-w-md animate-in slide-in-from-bottom">
                <p className="text-cyan-400 font-bold mb-3 tracking-widest uppercase flex items-center justify-center gap-2">
                   {isRecording && <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping inline-block"></span>}
                   {isRecording ? "Listening..." : "Type or Speak"}
                </p>
                <textarea 
                  value={manualText}
                  onChange={(e) => setManualText(e.target.value)}
                  className="bg-gray-800 p-5 rounded-xl text-left h-36 w-full text-sm text-gray-300 border border-cyan-500/30 shadow-inner resize-none focus:border-cyan-500 focus:outline-none placeholder-gray-500"
                  placeholder="Speak or type your answer..."
                />
                <div className="flex gap-4 mt-6">
                  <button 
                    onClick={isRecording ? stopRecording : startRecording}
                    className={`px-6 py-3 rounded-full font-bold text-white transition-all shadow-md ${isRecording ? 'bg-rose-600 hover:bg-rose-500' : 'bg-gray-700 hover:bg-gray-600'}`}
                  >
                    {isRecording ? "Stop Mic" : "Start Mic"}
                  </button>
                  <button 
                    onClick={finishAnswer}
                    className="flex-1 bg-cyan-600 hover:bg-cyan-500 px-8 py-3 rounded-full font-bold text-white transition-all shadow-[0_0_15px_rgba(8,145,178,0.5)]"
                  >
                    Submit Answer
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="w-full lg:w-1/3 flex flex-col space-y-6">
          <LiveFeed logs={logs} />
          
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-700/50 shadow-inner mt-4">
             <h3 className="text-gray-400 font-bold mb-6 tracking-wider uppercase text-xs">Room Temperature</h3>
             <div className="h-4 bg-gray-800 rounded-full overflow-hidden relative">
                <div className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-gray-500 z-10"></div>
                <div 
                  className="h-full bg-gradient-to-r from-rose-500 via-amber-400 to-emerald-500 transition-all duration-1000 w-full opacity-80" 
                  style={{ transformOrigin: 'center' }}
                ></div>
             </div>
             <div className="flex justify-between text-xs font-bold text-gray-500 uppercase tracking-wider mt-3">
               <span className="text-rose-500/80">Hostile</span>
               <span>Neutral</span>
               <span className="text-emerald-500/80">Excited</span>
             </div>
          </div>

          {radarChart && (
             <div className="bg-gray-900 rounded-2xl p-6 border border-gray-700/50 shadow-inner mt-4 flex flex-col items-center animate-in fade-in duration-500">
                 <h3 className="text-gray-400 font-bold mb-4 tracking-wider uppercase text-xs w-full text-left">Pitch Score Radar</h3>
                 <img src={`data:image/png;base64,${radarChart}`} alt="Radar Chart" className="w-full max-w-xs rounded-xl shadow-lg border border-gray-800" />
             </div>
          )}

          {domainData && (domainData.panel_mode === "design" || domainData.panel_mode === "physical_product") && (
             <div className="bg-gray-900 rounded-2xl p-6 border border-gray-700/50 shadow-xl mt-4 flex flex-col animate-in slide-in-from-right-4 duration-500">
                <h3 className="text-pink-500 font-black mb-1 tracking-widest uppercase text-xs">Sketch-to-3D Prototyping</h3>
                <p className="text-gray-500 text-[10px] mb-4">Our AI detected a design-focused pitch. Have a sketch URL? We'll model it.</p>
                
                {!model3D ? (
                    <div className="flex flex-col gap-2">
                        <input 
                          type="text" 
                          placeholder="Paste Sketch Image URL..." 
                          className="bg-gray-800 text-xs border border-gray-700 rounded-lg p-2 text-gray-300 focus:outline-none focus:border-pink-500"
                          onKeyDown={(e) => { if(e.key === 'Enter') submitSketch(e.currentTarget.value); }}
                        />
                        <button 
                          disabled={isGenerating3D}
                          onClick={() => {
                            const val = (document.querySelector('input[placeholder="Paste Sketch Image URL..."]') as HTMLInputElement)?.value;
                            if(val) submitSketch(val);
                          }}
                          className={`text-[10px] font-bold py-2 rounded-lg transition-all ${isGenerating3D ? 'bg-gray-700 text-gray-500' : 'bg-pink-600 hover:bg-pink-500 text-white'}`}
                        >
                          {isGenerating3D ? "Generating 3D (60s)..." : "Generate 3D Prototype"}
                        </button>
                    </div>
                ) : (
                    <div className="flex flex-col items-center gap-3">
                         {sketchImage && <img src={sketchImage} className="w-32 h-32 object-cover rounded-xl border border-gray-700 shadow-md" />}
                         <a 
                           href={model3D} 
                           target="_blank" 
                           rel="noreferrer"
                           className="bg-pink-600 hover:bg-pink-500 text-white text-[10px] font-bold px-4 py-2 rounded-lg flex items-center gap-2"
                         >
                           View GLB 3D Model
                         </a>
                    </div>
                )}
             </div>
          )}
        </div>
      </div>

      {verdictData && (
         <div className="w-full max-w-7xl flex flex-col gap-6 items-center mt-6">
            <VerdictCard verdict={verdictData} />
            <div className="bg-gray-900 p-6 rounded-2xl border border-gray-800 shadow-xl w-full max-w-2xl text-left">
              <h2 className="text-lg uppercase tracking-widest font-black text-rose-500 mb-2">Pushback on Verdict</h2>
              <p className="text-sm text-gray-400 mb-4">Disagree with the judge? Enter your pushback below and they will reconsider.</p>
              <textarea 
                  value={pushbackText}
                  onChange={(e) => setPushbackText(e.target.value)}
                  className="w-full bg-gray-800 text-gray-200 text-sm border border-gray-700 rounded-xl p-4 h-24 mb-4 focus:border-rose-500 focus:outline-none shadow-inner resize-none flex-grow block"
                  placeholder="e.g. You misunderstood my target market..."
              />
              <button disabled={isPushbacking} onClick={submitPushback} className={`w-full ${isPushbacking ? 'bg-gray-600' : 'bg-rose-600 hover:bg-rose-500'} text-white px-6 py-3 rounded-full font-bold transition-all shadow-md mt-2`}>
                {isPushbacking ? 'Judge is recalculating...' : 'Submit Pushback'}
              </button>
            </div>
            
            <button onClick={downloadReport} className="w-full max-w-2xl bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-4 rounded-2xl font-bold transition-all shadow-lg flex justify-center items-center gap-2">
                Download Executive Summary (PDF)
            </button>
         </div>
      )}
    </main>
  );
}
