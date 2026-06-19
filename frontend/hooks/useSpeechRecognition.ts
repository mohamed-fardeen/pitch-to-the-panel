"use client";

import { useState, useEffect, useRef } from "react";

/**
 * A robust hook for browser SpeechRecognition.
 * Requires a secure context (localhost, 127.0.0.1, or HTTPS).
 */
export function useSpeechRecognition() {
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      // Check for secure context - modern browsers block mic on insecure origins
      const isSecure = window.location.hostname === "localhost" || 
                       window.location.hostname === "127.0.0.1" || 
                       window.location.protocol === "https:";
                       
      if (!isSecure) {
        console.warn("Speech recognition/Microphone requires a secure context (HTTPS or localhost). Current: ", window.location.origin);
      }

      // Check for SpeechRecognition implementation
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      
      if (!SpeechRecognition) {
        console.error("SpeechRecognition is NOT supported in this browser. Please use Chrome or Edge.");
        return;
      }

      try {
        recognitionRef.current = new SpeechRecognition();
        recognitionRef.current.continuous = true;
        recognitionRef.current.interimResults = true;

        recognitionRef.current.onstart = () => {
          console.log("Speech recognition session started successfully");
          setIsRecording(true);
        };

        recognitionRef.current.onresult = (event: any) => {
          let totalTranscript = "";
          for (let i = 0; i < event.results.length; i++) {
            totalTranscript += event.results[i][0].transcript + " ";
          }
          console.log("Cumulative transcript update:", totalTranscript);
          setTranscript(totalTranscript.trim());
        };

        recognitionRef.current.onerror = (event: any) => {
          console.error("Speech recognition event error:", event.error, event);
          
          if (event.error === "not-allowed") {
            alert("Microphone permission was DENIED. Click the lock icon in your browser's address bar to reset permissions for this site.");
          } else if (event.error === "network") {
            alert("Speech recognition network error. Please check your internet connection.");
          }
          
          setIsRecording(false);
        };
        
        recognitionRef.current.onend = () => {
          console.log("Speech recognition session ended");
          setIsRecording(false);
        };
      } catch (e) {
        console.error("Failed to initialize SpeechRecognition:", e);
      }
    }
    
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
    };
  }, []);

  const startRecording = async () => {
    if (!recognitionRef.current) {
      alert("Your browser does not support Speech Recognition. Please use Chrome or Edge on a secure origin (localhost or HTTPS).");
      return;
    }

    if (isRecording) {
      console.log("Already recording, ignoring start request.");
      return;
    }

    try {
      console.log("Attempting to trigger browser permission prompt...");
      // Forcing a permission prompt via the MediaDevices API
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(track => track.stop());

      console.log("Permission granted. Initializing recognition...");
      setTranscript("");
      try {
        recognitionRef.current.start();
      } catch (startErr: any) {
        // InvalidStateError: recognition is already started (e.g. auto-restarted
        // by the browser after a transient error). Treat as a no-op.
        if (startErr?.name === "InvalidStateError") {
          console.warn("Recognition already started; ignoring duplicate start.");
        } else {
          throw startErr;
        }
      }
    } catch (err: any) {
      console.error("Microphone startup failure:", err);

      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        alert("Microphone access blocked. Click the LOCK ICON next to the URL in your address bar and set Microphone to ALLOW.");
      } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        alert("No microphone found on your device.");
      } else {
        alert(`Microphone Error: ${err.message || "Unknown error"}`);
      }

      setIsRecording(false);
    }
  };

  const stopRecording = () => {
    if (!recognitionRef.current) return;
    try {
      // abort() is safer than stop() when the recognition hasn't been
      // fully started yet (e.g. if a previous start() was rejected or
      // never finished initializing).
      if (typeof (recognitionRef.current as any).abort === "function") {
        (recognitionRef.current as any).abort();
      } else {
        recognitionRef.current.stop();
      }
      console.log("Recognition stopped manually.");
    } catch (e: any) {
      if (e?.name === "InvalidStateError") {
        console.warn("Recognition not in a startable state; ignoring stop.");
      } else {
        console.error("Error stopping recognition:", e);
      }
    }
    setIsRecording(false);
  };

  return { isRecording, transcript, startRecording, stopRecording };
}
