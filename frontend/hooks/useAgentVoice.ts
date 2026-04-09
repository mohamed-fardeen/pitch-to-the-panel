"use client";

import { useEffect, useState, useRef } from "react";

import { AgentRole } from "../types/v2_types";
export type { AgentRole };

interface VoiceConfig {
  pitch: number;
  rate: number;
  genderPref?: "male" | "female";
}

const AGENT_VOICE_CONFIGS: Record<string, VoiceConfig> = {
  vc: { pitch: 0.8, rate: 1.05, genderPref: "male" },
  enthusiastic: { pitch: 1.2, rate: 1.05, genderPref: "female" },
  hostile: { pitch: 0.7, rate: 1.0, genderPref: "male" },
  expert: { pitch: 1.0, rate: 1.0, genderPref: "male" },
  competitor: { pitch: 0.9, rate: 1.0, genderPref: "male" },
  beginner: { pitch: 1.1, rate: 0.95, genderPref: "male" },
  judge: { pitch: 0.85, rate: 1.0, genderPref: "male" },
  host: { pitch: 1.0, rate: 1.0, genderPref: "male" },
  observer: { pitch: 0.9, rate: 1.0 },
  pitcher: { pitch: 1.0, rate: 1.0 },
  mediator: { pitch: 0.95, rate: 1.0 },
  critic: { pitch: 0.75, rate: 1.0, genderPref: "male" },
  
  // v4 Personas
  suresh: { pitch: 0.7, rate: 1.0, genderPref: "male" },
  aisha: { pitch: 1.05, rate: 1.05, genderPref: "female" },
  kiran: { pitch: 1.1, rate: 0.95, genderPref: "male" },
  meera: { pitch: 0.95, rate: 1.0, genderPref: "female" },
  ananya: { pitch: 1.1, rate: 1.0, genderPref: "female" },
  rahul: { pitch: 0.9, rate: 1.0, genderPref: "male" },
  priya: { pitch: 1.2, rate: 1.05, genderPref: "female" },
  marcus: { pitch: 0.8, rate: 1.0, genderPref: "male" },
  sophia: { pitch: 1.15, rate: 1.05, genderPref: "female" },
  elara: { pitch: 1.0, rate: 1.0, genderPref: "female" },
  tariq: { pitch: 0.75, rate: 1.0, genderPref: "male" },
  lena: { pitch: 1.1, rate: 1.05, genderPref: "female" },
  victor: { pitch: 0.85, rate: 1.0, genderPref: "male" },
  interviewer: { pitch: 0.9, rate: 1.0, genderPref: "male" }
};

// Very safe chunk length to avoid Chrome's 200-char/15-second "silent restart" bug
const MAX_CHUNK = 80;

export function useAgentVoice() {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [isSupported, setIsSupported] = useState(false);
  const cancelledRef = useRef(false);
  const resumeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      setIsSupported(true);
      const loadVoices = () => {
        const availableVoices = window.speechSynthesis.getVoices();
        if (availableVoices.length > 0) {
          setVoices(availableVoices);
        }
      };
      loadVoices();
      if (window.speechSynthesis.onvoiceschanged !== undefined) {
        window.speechSynthesis.onvoiceschanged = loadVoices;
      }

      // Chrome Bug Fix: Long speeches can hang or restart. Calling resume() periodically keeps it alive.
      resumeTimerRef.current = setInterval(() => {
        if (window.speechSynthesis.speaking) {
          window.speechSynthesis.resume();
        }
      }, 5000);

      return () => {
        window.speechSynthesis.cancel();
        if (resumeTimerRef.current) clearInterval(resumeTimerRef.current);
      };
    }
    
    return () => {
      window.speechSynthesis.cancel();
      if (resumeTimerRef.current) clearInterval(resumeTimerRef.current);
    };
  }, []);

  const getBestVoice = (role: AgentRole): SpeechSynthesisVoice | null => {
    if (voices.length === 0) return null;
    const config = AGENT_VOICE_CONFIGS[role] || { pitch: 1.0, rate: 1.0, genderPref: "male" };
    const pool = voices.filter(v => v.lang.startsWith("en") || v.lang.startsWith("EN"));
    if (pool.length === 0) return voices[0];

    const maleKeywords = ["male", "david", "mark", "guy", "ryan", "george", "adam", "arthur", "james"];
    const femaleKeywords = ["female", "zira", "susan", "hazel", "alice", "lisa", "jenny", "jane", "mary"];
    const males = pool.filter(v => maleKeywords.some(k => v.name.toLowerCase().includes(k)));
    const females = pool.filter(v => femaleKeywords.some(k => v.name.toLowerCase().includes(k)));

    if (config.genderPref === "male" && males.length > 0) {
      const allMaleRoles = Object.keys(AGENT_VOICE_CONFIGS).filter(k => AGENT_VOICE_CONFIGS[k].genderPref === "male");
      const index = allMaleRoles.indexOf(role);
      return males[Math.max(0, index) % males.length];
    } else if (config.genderPref === "female" && females.length > 0) {
      const allFemaleRoles = Object.keys(AGENT_VOICE_CONFIGS).filter(k => AGENT_VOICE_CONFIGS[k].genderPref === "female");
      const index = allFemaleRoles.indexOf(role);
      return females[Math.max(0, index) % females.length];
    }

    // Hash-based absolute fallback if gender-specific pool is empty
    const hash = role.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
    return pool[hash % pool.length] || voices[0];
  };

  const getNameOffset = (name: string): { pitch: number, rate: number } => {
    // Generate a unique but deterministic offset for each name
    const hash = name.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
    const pitchOffset = ((hash % 20) - 10) / 100; // ±0.1
    const rateOffset = ((hash % 14) - 7) / 100;   // ±0.07
    return { pitch: pitchOffset, rate: rateOffset };
  };

  const splitIntoChunks = (text: string): string[] => {
    if (!text) return [];

    // 1. CLEAN TEXT: Remove line breaks, merge sentences, trim whitespace
    const clean = text
      .replace(/[\n\r]+/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim();

    // 2. CHUNK BY SENTENCE: Split using re.split r'[.!?]' (equivalent)
    const sentences = clean.split(/(?<=[.!?])\s+/).filter(s => s.trim().length > 0);

    // 3. GROUP INTO CHUNKS: 1-2 sentences for smooth flow
    const chunks: string[] = [];
    for (let i = 0; i < sentences.length; i += 2) {
      const chunk = sentences.slice(i, i + 2).join(" ");
      // 3. ADD MINIMUM LENGTH FILTER: Skip very short chunks (<15 chars)
      if (chunk.trim().length >= 15) {
        chunks.push(chunk.trim());
      } else if (i + 2 >= sentences.length && chunks.length > 0) {
        // Append last tiny bit to previous chunk instead of skipping
        chunks[chunks.length - 1] += " " + chunk.trim();
      } else if (chunk.trim().length > 0) {
          chunks.push(chunk.trim());
      }
    }

    return chunks;
  };

  const [isSpeaking, setIsSpeaking] = useState(false);

  const speak = (role: AgentRole, text: string, onEnd?: () => void) => {
    if (!isSupported || !text) {
      if (onEnd) onEnd();
      return;
    }

    // Cancel any in-progress speech first
    window.speechSynthesis.cancel();

    const config = AGENT_VOICE_CONFIGS[role] || { pitch: 1, rate: 1 };
    const chunks = splitIntoChunks(text);

    if (chunks.length === 0) {
      if (onEnd) onEnd();
      return;
    }

    console.log(`[Voice] ${role}: Speaking ${chunks.length} chunks...`);
    cancelledRef.current = false;
    setIsSpeaking(true);
    const voice = getBestVoice(role);
    let chunkIndex = 0;

    const speakNextChunk = () => {
      if (cancelledRef.current || chunkIndex >= chunks.length) {
        setIsSpeaking(false);
        if (onEnd) onEnd();
        return;
      }

      const chunk = chunks[chunkIndex];
      chunkIndex++;

      const utterance = new SpeechSynthesisUtterance(chunk);
      if (voice) utterance.voice = voice;
      
      const offsets = getNameOffset(role);
      utterance.pitch = Math.max(0.5, Math.min(2, config.pitch + offsets.pitch));
      utterance.rate = Math.max(0.5, Math.min(2, config.rate + offsets.rate));
      utterance.volume = 1.0;

      let fired = false;
      utterance.onend = () => {
        if (fired) return;
        fired = true;
        // Minimal delay between chunks for natural flow
        setTimeout(speakNextChunk, 5);
      };

      utterance.onerror = (e) => {
        if (fired) return;
        fired = true;
        if (e.error !== "interrupted" && e.error !== "canceled") {
          console.error(`[Voice] Error: ${e.error}`);
        }
        speakNextChunk();
      };

      window.speechSynthesis.speak(utterance);
    };

    speakNextChunk();
  };

  const stopSpeaking = () => {
    if (isSupported) {
      cancelledRef.current = true;
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
  };

  return { speak, stopSpeaking, isSpeaking, isSupported };
}
