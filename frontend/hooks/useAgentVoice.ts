"use client";

import { useEffect, useState, useRef } from "react";

export type AgentRole = "vc" | "enthusiastic" | "hostile" | "expert" | "competitor" | "beginner" | "judge";

interface VoiceConfig {
  pitch: number;
  rate: number;
  genderPref?: "male" | "female";
}

const AGENT_VOICE_CONFIGS: Record<AgentRole, VoiceConfig> = {
  vc: { pitch: 0.8, rate: 0.95, genderPref: "male" },
  enthusiastic: { pitch: 1.2, rate: 1.15, genderPref: "female" },
  hostile: { pitch: 0.7, rate: 0.9, genderPref: "male" },
  expert: { pitch: 1.0, rate: 1.0, genderPref: "female" },
  competitor: { pitch: 0.9, rate: 1.05, genderPref: "female" },
  beginner: { pitch: 1.1, rate: 1.0, genderPref: "male" },
  judge: { pitch: 0.85, rate: 0.95, genderPref: "male" }
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
  }, []);

  const getBestVoice = (role: AgentRole): SpeechSynthesisVoice | null => {
    if (voices.length === 0) return null;
    const config = AGENT_VOICE_CONFIGS[role];
    const pool = voices.filter(v => v.lang.startsWith("en") || v.lang.startsWith("EN"));
    if (pool.length === 0) return voices[0];

    const maleKeywords = ["male", "david", "mark", "guy", "ryan", "george", "adam", "arthur", "james"];
    const femaleKeywords = ["female", "zira", "susan", "hazel", "alice", "lisa", "jenny", "jane", "mary"];
    const males = pool.filter(v => maleKeywords.some(k => v.name.toLowerCase().includes(k)));
    const females = pool.filter(v => femaleKeywords.some(k => v.name.toLowerCase().includes(k)));

    if (config.genderPref === "male" && males.length > 0) {
      const maleRoles = Object.keys(AGENT_VOICE_CONFIGS).filter(k => AGENT_VOICE_CONFIGS[k as AgentRole].genderPref === "male");
      return males[maleRoles.indexOf(role) % males.length];
    } else if (config.genderPref === "female" && females.length > 0) {
      const femaleRoles = Object.keys(AGENT_VOICE_CONFIGS).filter(k => AGENT_VOICE_CONFIGS[k as AgentRole].genderPref === "female");
      return females[femaleRoles.indexOf(role) % females.length];
    }
    const hash = role.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
    return pool[hash % pool.length];
  };

  const splitIntoChunks = (text: string): string[] => {
    // Clean markdown and formatting
    const clean = text
      .replace(/[*#>`_~\[\]]/g, "")
      .replace(/\n+/g, ". ")
      .replace(/\s{2,}/g, " ")
      .replace(/\.{2,}/g, ".")
      .trim();

    // Level 1: Strong boundaries
    const sentences = clean.split(/(?<=[.?!;:])\s+/).filter(s => s.trim().length > 0);

    // Level 2: Commas / Dashes / Conjunctions for long sentences
    const fragments: string[] = [];
    for (const sentence of sentences) {
      if (sentence.length <= MAX_CHUNK) {
        fragments.push(sentence);
      } else {
        const parts = sentence.split(/(?<=[,;])\s+|(?:\s+and\s+)|(?:\s+but\s+)|(?:\s*—\s*)/i).filter(s => s.trim().length > 0);
        fragments.push(...parts);
      }
    }

    // Level 3: Hard-split at word boundaries as last resort
    const safeFragments: string[] = [];
    for (const frag of fragments) {
      if (frag.length <= MAX_CHUNK) {
        safeFragments.push(frag);
      } else {
        let remaining = frag;
        while (remaining.length > MAX_CHUNK) {
          let splitAt = remaining.lastIndexOf(" ", MAX_CHUNK);
          if (splitAt <= 0) splitAt = MAX_CHUNK;
          safeFragments.push(remaining.substring(0, splitAt).trim());
          remaining = remaining.substring(splitAt).trim();
        }
        if (remaining.trim()) safeFragments.push(remaining.trim());
      }
    }

    // Regroup into chunks that are close to but not over MAX_CHUNK
    const chunks: string[] = [];
    let current = "";
    for (const frag of safeFragments) {
      if (current.length + frag.length + 1 > MAX_CHUNK && current.length > 0) {
        chunks.push(current.trim());
        current = frag;
      } else {
        current += (current ? " " : "") + frag;
      }
    }
    if (current.trim()) chunks.push(current.trim());

    return chunks;
  };

  const speak = (role: AgentRole, text: string, onEnd?: () => void) => {
    if (!isSupported || !text) {
      if (onEnd) onEnd();
      return;
    }

    const config = AGENT_VOICE_CONFIGS[role] || { pitch: 1, rate: 1 };
    const chunks = splitIntoChunks(text);

    if (chunks.length === 0) {
      if (onEnd) onEnd();
      return;
    }

    console.log(`[Voice] ${role}: Speaking ${chunks.length} chunks...`);
    cancelledRef.current = false;
    const voice = getBestVoice(role);
    let chunkIndex = 0;

    const speakNextChunk = () => {
      if (cancelledRef.current || chunkIndex >= chunks.length) {
        if (onEnd) onEnd();
        return;
      }

      const chunk = chunks[chunkIndex];
      chunkIndex++;

      const utterance = new SpeechSynthesisUtterance(chunk);
      if (voice) utterance.voice = voice;
      utterance.pitch = config.pitch;
      utterance.rate = config.rate;
      utterance.volume = 1.0;

      let fired = false;
      utterance.onend = () => {
        if (fired) return;
        fired = true;
        // Small delay between chunks for extra safety and naturalness
        setTimeout(speakNextChunk, 20);
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
    }
  };

  return { speak, stopSpeaking, isSupported };
}
