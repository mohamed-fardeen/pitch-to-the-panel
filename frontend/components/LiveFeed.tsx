"use client";

import React, { useEffect, useRef } from "react";

interface LiveFeedProps {
  logs: string[];
}

export function LiveFeed({ logs }: LiveFeedProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="bg-gray-900 border border-gray-700/50 rounded-2xl p-6 h-64 overflow-y-auto shadow-inner">
      <h3 className="text-gray-400 font-semibold mb-4 tracking-wider uppercase text-xs">Live Feed</h3>
      <div className="space-y-2">
        {logs.map((log, idx) => (
          <div key={idx} className="text-sm font-mono text-gray-300">
            <span className="text-blue-400 mr-2">{">"}</span>
            {log}
          </div>
        ))}
        {logs.length === 0 && (
          <div className="text-gray-600 italic text-sm">Awaiting system events...</div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
