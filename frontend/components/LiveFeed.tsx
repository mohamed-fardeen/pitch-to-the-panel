"use client";

import React, { useEffect, useRef } from "react";
import { ConversationTurn } from "../types/v2_types";

interface LiveFeedProps {
  turns: ConversationTurn[];
  agents: any[];
  onJumpIn?: () => void;
  isRecording?: boolean;
  awaitingUserInput?: boolean;
  isInterrupting?: boolean;
  userInput?: string;
  onUserInputChange?: (val: string) => void;
  onSendAnswer?: () => void;
  onSendInterrupt?: () => void;
  onCancelInterrupt?: () => void;
  currentQuestion?: string;
  isStreaming?: boolean;
  activeAgent?: { id: string, name: string } | null;
  onSetAwaitingUserInput?: (val: boolean) => void;
}

export function LiveFeed({ 
  turns, 
  agents, 
  onJumpIn, 
  isRecording,
  awaitingUserInput,
  isInterrupting,
  userInput,
  onUserInputChange,
  onSendAnswer,
  onSendInterrupt,
  onCancelInterrupt,
  currentQuestion,
  isStreaming,
  activeAgent: streamAgent,
  onSetAwaitingUserInput
}: LiveFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const getAgentData = (name: string) => {
    // panelState values carry `name` (display) and `role`. Match on `name`
    // (also tolerate the case where a backend turn uses `agent_id` as the
    // display identifier).
    if (!name) return undefined;
    return agents.find(a => a.name === name || (a as any).id === name);
  };

  // Find the currently speaking agent to show their streaming text.
  // Match by agent NAME (the only stable identifier on panelState values)
  // rather than agent_id (which is undefined on these objects).
  const activeAgent = agents.find(a => a.status === "speaking" && a.text);

  // The most recent turn's agent name — used to suppress the streaming
  // bubble when it's a duplicate of the last conversation turn.
  const lastTurn = turns.length > 0 ? turns[turns.length - 1] : null;
  const lastTurnAgentName = lastTurn?.agent_name?.toLowerCase().trim() || "";
  const activeAgentName = activeAgent?.name?.toLowerCase().trim() || "";
  // Show the streaming bubble only if it represents NEW content (i.e. the
  // last conversation turn is not from the same agent).
  const showStreamingBubble = !!activeAgent && activeAgentName !== lastTurnAgentName;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns, activeAgent?.text]);

  return (
    <div className="flex flex-col h-full bg-white/80 backdrop-blur-sm rounded-[3rem] border border-slate-100 shadow-xl overflow-hidden relative font-headline">
      {/* Glossy Header Area */}
      <div className="p-8 border-b border-slate-100/60 bg-white/40 backdrop-blur-md flex justify-between items-center z-10">
        <div className="flex items-center gap-3">
           <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
           <h2 className="text-xl font-bold text-slate-800 tracking-tight">Live Transcript</h2>
        </div>
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest bg-slate-50 border border-slate-100/50 px-4 py-2 rounded-full">Real-Time Synthesis</span>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-10 space-y-8 custom-scrollbar scroll-smooth pb-32">
        {turns.length === 0 && !showStreamingBubble ? (
          <div className="h-full flex flex-col items-center justify-center space-y-8 opacity-60 text-center">
            <div className="w-24 h-24 bg-emerald-50 rounded-full flex items-center justify-center border border-emerald-100/50">
               <span className="material-symbols-outlined text-4xl text-emerald-300">history_edu</span>
            </div>
            <div className="space-y-3">
              <h3 className="text-xl font-bold text-slate-400 uppercase tracking-widest px-2">Session Active</h3>
              <p className="text-sm font-medium text-slate-300 max-w-[240px] mx-auto leading-relaxed">The panel is ready. Start your pitch to begin the synthesis.</p>
            </div>
          </div>
        ) : (
          <>
            {turns.map((turn, i) => {
              const agent = getAgentData(turn.agent_name || "");
              const isPitcher = turn.agent_name === "Pitcher" || turn.agent_name === "Alex Chen" || turn.agent_name === "Pitcher (Interrupt)";

              // If the streaming bubble is going to render for this exact
              // same agent, skip the conversation bubble to avoid the
              // duplicate rendering that was visible in earlier sessions.
              if (
                i === turns.length - 1 &&
                showStreamingBubble &&
                activeAgent &&
                turn.agent_name?.toLowerCase().trim() === activeAgent.name?.toLowerCase().trim()
              ) {
                return null;
              }

              return (
                <div key={i} className={`flex flex-col gap-2 transition-all duration-700`}>
                  <div className="flex items-center gap-3 ml-1">
                    <div className={`w-2 h-2 rounded-full ${isPitcher ? 'bg-emerald-500' : 'bg-slate-300'}`} style={{ backgroundColor: agent?.color }}></div>
                    <span className={`text-[10px] font-bold uppercase tracking-[0.2em] ${isPitcher ? 'text-emerald-600' : 'text-slate-400'}`}>
                      {turn.agent_name || "Specialist"}
                    </span>
                  </div>
                  
                  <div 
                    className={`p-8 rounded-[2rem] border-l-4 shadow-sm transition-all ${
                      isPitcher 
                        ? "bg-slate-50/50 border-emerald-500/20 text-slate-500 italic font-medium" 
                        : "bg-slate-50 border-slate-200/50 text-slate-700"
                    }`}
                    style={!isPitcher ? { borderLeftColor: agent?.color || '#e2e8f0' } : {}}
                  >
                    <p className="text-base leading-relaxed opacity-90">
                      {turn.content}
                    </p>
                  </div>
                </div>
              );
            })}

            {/* Active Streaming Bubble */}
            {showStreamingBubble && activeAgent && (
              <div className="flex flex-col gap-2 transition-all duration-300">
                <div className="flex items-center gap-3 ml-1">
                  <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" style={{ backgroundColor: activeAgent.color }}></div>
                  <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-600">
                    {activeAgent.name} <span className="opacity-50 lowercase font-medium italic">(streaming)</span>
                  </span>
                </div>
                <div 
                  className="p-8 rounded-[2rem] border-l-4 shadow-sm transition-all bg-emerald-50/30 border-emerald-200 text-slate-800"
                  style={{ borderLeftColor: activeAgent.color || '#10b981' }}
                >
                  <p className="text-base leading-relaxed">
                    {activeAgent.text}
                    <span className="inline-block w-1 h-4 bg-emerald-500 ml-1 animate-pulse align-middle" />
                  </p>
                </div>
              </div>
            )}
          </>
        )}
      </div>

       {/* Floating Action Container - 1. ANSWER INPUT (HITL) */}
      <div className="absolute bottom-8 left-0 right-0 px-10 pointer-events-none flex justify-center z-20">
        {awaitingUserInput && (
          <div className="pointer-events-auto w-full max-w-2xl bg-white/95 backdrop-blur-xl rounded-[2.5rem] p-4 shadow-2xl border border-emerald-500/20 flex flex-col gap-3 animate-in slide-in-from-bottom-5">
            {currentQuestion && (
              <div className="px-4 py-2 bg-emerald-50/50 rounded-2xl border border-emerald-100/30">
                <p className="text-[10px] font-bold text-emerald-600 uppercase tracking-widest mb-1">💬 Answer as Founder:</p>
                <p className="text-sm font-medium text-slate-700 leading-relaxed italic">"{currentQuestion}"</p>
              </div>
            )}
            <div className="flex gap-4">
              <input
                value={userInput}
                onChange={(e) => onUserInputChange?.(e.target.value)}
                placeholder="Type your strategic response..."
                className="flex-1 bg-slate-50 border-none rounded-2xl py-5 px-8 text-slate-800 placeholder:text-slate-300 focus:bg-white focus:ring-2 focus:ring-emerald-500/10 transition-all outline-none text-base font-medium"
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), onSendAnswer?.())}
              />
              <button 
                onClick={onSendAnswer}
                disabled={!userInput?.trim()}
                className="w-16 h-16 rounded-full bg-[#006948] hover:bg-[#005a3e] text-white flex items-center justify-center shadow-xl shadow-emerald-900/20 disabled:opacity-30 disabled:grayscale transition-all active:scale-95"
              >
                <span className="material-symbols-outlined text-2xl">send</span>
              </button>
            </div>
          </div>
        )}

        {/* 2. JUMP IN BUTTON (Always available unless already interrupting) */}
        {!isInterrupting && !awaitingUserInput && (
          <div className="flex gap-4 pointer-events-auto items-center">
            {onJumpIn && (
              <button 
                onClick={onJumpIn}
                className={`flex items-center gap-4 py-5 px-10 rounded-full bg-[#006948] hover:bg-[#005a3e] text-white font-bold uppercase tracking-widest shadow-2xl shadow-emerald-950/20 hover:scale-[1.05] active:scale-[0.95] transition-all ring-4 ring-emerald-500/10 ${isRecording ? 'bg-rose-500 hover:bg-rose-600 ring-rose-500/20' : ''}`}
              >
                <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                  {isRecording ? 'stop_circle' : 'bolt'}
                </span>
                <span className="text-sm">{isRecording ? 'Stop Recording' : 'JUMP IN'}</span>
              </button>
            )}
            
            <button 
              onClick={() => {
                onUserInputChange?.("");
                onSetAwaitingUserInput?.(true);
              }} 
              className="w-16 h-16 rounded-full bg-white border border-slate-200 text-slate-400 hover:text-emerald-600 hover:border-emerald-200 transition-all flex items-center justify-center shadow-lg group"
              title="Manual Response"
            >
              <span className="material-symbols-outlined text-2xl group-hover:scale-110 transition-transform">edit_note</span>
            </button>
          </div>
        )}

        {/* Show Jump In Button even if awaitingUserInput is true (separate flow) */}
        {!isInterrupting && awaitingUserInput && (
          <div className="pointer-events-auto fixed bottom-24 right-16">
            <button 
              onClick={onJumpIn}
              className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 hover:text-emerald-600 border border-slate-200 shadow-lg flex items-center justify-center hover:scale-110 transition-all"
              title="Interrupt Discussion"
            >
              <span className="material-symbols-outlined text-xl">bolt</span>
            </button>
          </div>
        )}
      </div>

      {/* 3. INTERRUPT PANEL (Modal Overlay) */}
      {isInterrupting && (
        <div className="absolute inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-end justify-center p-10 animate-in fade-in">
          <div className="w-full max-w-2xl bg-white rounded-[3rem] p-8 shadow-2xl space-y-6 animate-in slide-in-from-bottom-10 pointer-events-auto">
            <div className="flex justify-between items-center px-2">
              <h3 className="text-sm font-bold text-[#006948] uppercase tracking-[0.2em]">Interrupt Panel</h3>
              <button onClick={onCancelInterrupt} className="text-slate-400 hover:text-slate-600">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="space-y-4">
               <textarea 
                  value={userInput}
                  onChange={(e) => onUserInputChange?.(e.target.value)}
                  placeholder="Inject your thoughts into the discussion..."
                  className="w-full h-32 bg-slate-50 rounded-[2rem] p-8 text-slate-800 placeholder:text-slate-300 outline-none focus:ring-2 focus:ring-emerald-500/10 resize-none font-medium"
                  autoFocus
               />
               <button 
                  onClick={onSendInterrupt}
                  disabled={!userInput?.trim()}
                  className="w-full py-6 bg-[#006948] hover:bg-[#005a3e] text-white rounded-full font-bold uppercase tracking-widest shadow-xl shadow-emerald-900/10 disabled:opacity-30 transition-all active:scale-95"
               >
                  Send Interruption
               </button>
            </div>
          </div>
        </div>
      )}

      {/* Typing Indicator */}
      {isStreaming && streamAgent && !activeAgent && (
         <div className="absolute bottom-4 left-10 flex items-center gap-2 py-4 opacity-40">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse" />
            <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse delay-75" />
            <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse delay-150" />
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest ml-1">{streamAgent.name} is thinking...</span>
         </div>
      )}
    </div>
  );
}
