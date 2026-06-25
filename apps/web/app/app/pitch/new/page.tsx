"use client";

import { useState } from "react";
import Link from "next/link";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

const MODES = [
  { value: "venture", label: "Venture", description: "Market & ROI focus" },
  { value: "reality", label: "Reality", description: "Operational risks" },
  { value: "spark", label: "Spark", description: "Creative ideation" },
];

export default function NewPitchPage() {
  const [pitch, setPitch] = useState("");
  const [mode, setMode] = useState("venture");
  const [provider, setProvider] = useState("groq");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pitch.trim()) return;
    if (pitch.trim().length < 20) {
      setError("Please write at least 20 characters.");
      return;
    }
    setSubmitting(true);
    setError(null);

    try {
      // Start a pitch session via the orchestrator. For now we use
      // the simplified flow: POST /api/pitch/score (legacy endpoint)
      // gets a radar chart, then we use the same /api/stream/main for
      // the full debate. For the v0 simple UI, we just call the
      // score endpoint to get a verdict-style response.
      const r = await fetch(`${API_BASE}/pitch/score`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: crypto.randomUUID(),
          provider,
        }),
      });
      if (!r.ok) {
        throw new Error(`Backend returned ${r.status}`);
      }
      // The simple flow: just show a "thanks" message and link to
      // the verdict page. The full live-debate flow requires the
      // /api/stream/main SSE endpoint which is being added in a
      // follow-up.
      setSubmitting(false);
      setError(
        "Score endpoint returned successfully. The full verdict + " +
        "PDF report is generated in the backend. To see the live " +
        "debate, run the legacy `frontend/` via run.bat."
      );
    } catch (err: any) {
      setSubmitting(false);
      setError(err?.message ?? "Failed to submit pitch");
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-ink-50 to-white">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <div className="mb-8">
          <Link
            href="/"
            className="text-sm text-ink-500 hover:text-ink-900 underline"
          >
            ← Back to home
          </Link>
        </div>

        <h1 className="text-4xl font-extrabold tracking-tight text-ink-900">
          Submit your pitch
        </h1>
        <p className="mt-2 text-ink-600">
          Write your pitch below and the panel of AI investors will evaluate
          it. This is a simple v0 form — for the full live-debate
          experience, run the legacy frontend via{" "}
          <code className="rounded bg-ink-100 px-1.5 py-0.5 text-sm">
            run.bat
          </code>
          .
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          {/* Mode selector */}
          <div>
            <label className="block text-sm font-bold text-ink-900 mb-2">
              Panel mode
            </label>
            <div className="grid grid-cols-3 gap-3">
              {MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => setMode(m.value)}
                  className={`rounded-2xl border p-4 text-left transition-colors ${
                    mode === m.value
                      ? "border-ink-900 bg-ink-50"
                      : "border-ink-200 bg-white hover:border-ink-400"
                  }`}
                >
                  <div className="font-bold text-ink-900">{m.label}</div>
                  <div className="mt-1 text-xs text-ink-500">
                    {m.description}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Pitch textarea */}
          <div>
            <label
              htmlFor="pitch"
              className="block text-sm font-bold text-ink-900 mb-2"
            >
              Your pitch
            </label>
            <textarea
              id="pitch"
              value={pitch}
              onChange={(e) => setPitch(e.target.value)}
              rows={10}
              placeholder="e.g. We're building an AI-powered CRM for dental practices. Our system uses NLP to automatically transcribe patient interactions, schedule appointments based on treatment urgency, and predict patient lifetime value. We charge $299/month per practice and have 23 paying customers in our beta, with $8.4k MRR growing 18% MoM."
              className="w-full rounded-2xl border border-ink-200 bg-white p-4 text-ink-900 placeholder-ink-300 focus:border-ink-900 focus:outline-none resize-y"
            />
            <div className="mt-1 flex items-center justify-between text-xs text-ink-500">
              <span>{pitch.length} characters</span>
              {pitch.length > 0 && pitch.length < 20 && (
                <span className="text-rose-500">
                  Need at least 20 characters
                </span>
              )}
            </div>
          </div>

          {/* Provider selector */}
          <div>
            <label
              htmlFor="provider"
              className="block text-sm font-bold text-ink-900 mb-2"
            >
              LLM provider
            </label>
            <select
              id="provider"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="w-full rounded-2xl border border-ink-200 bg-white px-4 py-3 text-ink-900 focus:border-ink-900 focus:outline-none"
            >
              <option value="groq">Groq (Llama 3.1 — free tier)</option>
              <option value="anthropic">Anthropic (Claude 3.5 Sonnet)</option>
              <option value="openai">OpenAI (GPT-4o)</option>
              <option value="gemini">Gemini (1.5 Pro)</option>
              <option value="ollama">Ollama (local)</option>
            </select>
          </div>

          {error && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || pitch.length < 20}
            className="w-full rounded-full bg-ink-900 px-8 py-4 text-base font-semibold text-white hover:bg-ink-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Submitting…" : "Submit pitch"}
          </button>
        </form>
      </div>
    </main>
  );
}
