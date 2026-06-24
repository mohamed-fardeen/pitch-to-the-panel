import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

interface PublicVerdict {
  session_id: string;
  is_public: boolean;
  mode: string;
  created_at: string;
  pitch_excerpt: string;
  verdict: {
    strongest: string;
    weakness: string;
    fix: string;
    recommendation: string;
    investment_score: number | null;
    verdict_text: string;
  };
  confidence_score: number;
  investment_signal: string;
}

const SIGNAL_STYLES: Record<string, { bg: string; text: string; ring: string }> = {
  STRONG: {
    bg: "bg-emerald-50",
    text: "text-emerald-700",
    ring: "ring-emerald-200",
  },
  MEDIUM: {
    bg: "bg-amber-50",
    text: "text-amber-700",
    ring: "ring-amber-200",
  },
  WEAK: {
    bg: "bg-rose-50",
    text: "text-rose-700",
    ring: "ring-rose-200",
  },
  ABORTED: {
    bg: "bg-slate-50",
    text: "text-slate-700",
    ring: "ring-slate-200",
  },
};

async function fetchVerdict(sessionId: string): Promise<PublicVerdict | null> {
  try {
    const res = await fetch(`${API_BASE}/v/${sessionId}/public`, {
      cache: "no-store",
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Verdict fetch failed: ${res.status}`);
    return (await res.json()) as PublicVerdict;
  } catch (err) {
    console.error("fetchVerdict failed:", err);
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ verdictId: string }>;
}): Promise<Metadata> {
  const { verdictId } = await params;
  const verdict = await fetchVerdict(verdictId);
  if (!verdict) {
    return {
      title: "Verdict not found — PanelMind",
      description: "This pitch verdict could not be found or is private.",
    };
  }
  const title = `PanelMind Verdict: ${verdict.investment_signal} (${verdict.confidence_score}/100)`;
  const description =
    verdict.verdict.strongest ||
    verdict.verdict.verdict_text ||
    "PanelMind multi-agent pitch evaluation";
  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "article",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export default async function PublicVerdictPage({
  params,
}: {
  params: Promise<{ verdictId: string }>;
}) {
  const { verdictId } = await params;
  const verdict = await fetchVerdict(verdictId);

  if (!verdict) {
    notFound();
  }

  const signalStyle = SIGNAL_STYLES[verdict.investment_signal] ?? SIGNAL_STYLES.MEDIUM;
  const date = verdict.created_at
    ? new Date(verdict.created_at).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  return (
    <main className="min-h-screen bg-gradient-to-b from-ink-50 to-white">
      {/* Header */}
      <header className="border-b border-ink-100 bg-white/80 backdrop-blur sticky top-0 z-30">
        <div className="mx-auto max-w-4xl px-6 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 font-bold">
            <span
              className="grid h-8 w-8 place-items-center rounded-lg bg-ink-900 text-white"
              aria-hidden
            >
              ◆
            </span>
            <span className="text-lg">PanelMind</span>
          </Link>
          <Link
            href="/"
            className="text-sm font-medium text-ink-600 hover:text-ink-900"
          >
            Run your own →
          </Link>
        </div>
      </header>

      {/* Verdict content */}
      <article className="mx-auto max-w-3xl px-6 py-16 sm:py-24">
        {/* Signal header */}
        <div className="text-center mb-12">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-ink-500">
            {date && (
              <>
                {date}
                {" · "}
              </>
            )}
            {verdict.mode} mode
          </p>
          <div
            className={`inline-flex items-center gap-2 mt-4 px-6 py-3 rounded-2xl ring-1 ${signalStyle.bg} ${signalStyle.text} ${signalStyle.ring}`}
          >
            <span className="text-3xl font-black">{verdict.confidence_score}</span>
            <span className="text-sm font-medium opacity-80">/ 100 confidence</span>
            <span className="text-xs font-bold uppercase tracking-wider ml-2 opacity-70">
              {verdict.investment_signal}
            </span>
          </div>
          <h1 className="mt-6 text-4xl font-extrabold tracking-tight text-ink-900 sm:text-5xl">
            {verdict.verdict.strongest || "PanelMind verdict"}
          </h1>
          {verdict.verdict.recommendation && (
            <p className="mt-4 text-lg text-ink-600 italic">
              Recommendation: {verdict.verdict.recommendation}
            </p>
          )}
        </div>

        {/* Three-column verdict grid */}
        <div className="grid gap-6 sm:grid-cols-3 mb-12">
          <div className="rounded-2xl border border-emerald-100 bg-emerald-50/50 p-6">
            <div className="text-xs font-bold uppercase tracking-wider text-emerald-700 mb-2">
              Strongest
            </div>
            <p className="text-sm text-ink-700 leading-relaxed">
              {verdict.verdict.strongest || "—"}
            </p>
          </div>
          <div className="rounded-2xl border border-rose-100 bg-rose-50/50 p-6">
            <div className="text-xs font-bold uppercase tracking-wider text-rose-700 mb-2">
              Weakness
            </div>
            <p className="text-sm text-ink-700 leading-relaxed">
              {verdict.verdict.weakness || "—"}
            </p>
          </div>
          <div className="rounded-2xl border border-indigo-100 bg-indigo-50/50 p-6">
            <div className="text-xs font-bold uppercase tracking-wider text-indigo-700 mb-2">
              Recommended Fix
            </div>
            <p className="text-sm text-ink-700 leading-relaxed">
              {verdict.verdict.fix || "—"}
            </p>
          </div>
        </div>

        {/* Pitch excerpt */}
        {verdict.pitch_excerpt && (
          <div className="rounded-2xl border border-ink-100 bg-white p-8 mb-12">
            <div className="text-xs font-bold uppercase tracking-wider text-ink-500 mb-3">
              The Pitch
            </div>
            <p className="text-base text-ink-700 leading-relaxed italic">
              &ldquo;{verdict.pitch_excerpt}&rdquo;
            </p>
          </div>
        )}

        {/* Full verdict text if present */}
        {verdict.verdict.verdict_text && (
          <div className="rounded-2xl border border-ink-100 bg-white p-8 mb-12">
            <div className="text-xs font-bold uppercase tracking-wider text-ink-500 mb-3">
              Full Verdict
            </div>
            <p className="text-base text-ink-700 leading-relaxed whitespace-pre-line">
              {verdict.verdict.verdict_text}
            </p>
          </div>
        )}

        {/* Investment score bar */}
        {verdict.verdict.investment_score !== null && (
          <div className="rounded-2xl border border-ink-100 bg-white p-8 mb-12">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-bold uppercase tracking-wider text-ink-500">
                Investment Score
              </div>
              <div className="text-2xl font-black text-ink-900">
                {verdict.verdict.investment_score.toFixed(1)}
                <span className="text-base text-ink-400 font-medium"> / 10</span>
              </div>
            </div>
            <div className="h-2 bg-ink-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-ink-900 rounded-full transition-all"
                style={{
                  width: `${Math.min(100, verdict.verdict.investment_score * 10)}%`,
                }}
              />
            </div>
          </div>
        )}

        {/* CTA */}
        <div className="rounded-3xl bg-ink-950 text-white p-10 text-center">
          <h2 className="text-2xl font-extrabold mb-3">
            Want this kind of feedback on your pitch?
          </h2>
          <p className="text-ink-300 mb-6 max-w-md mx-auto">
            Run your pitch through a panel of AI investors, designers, and
            operators. Free, open source, and no signup required.
          </p>
          <Link
            href="/signin?callbackUrl=/app/pitch/new"
            className="inline-block rounded-full bg-white px-8 py-4 text-base font-semibold text-ink-900 hover:bg-ink-100 transition-colors"
          >
            Start your own session →
          </Link>
          <p className="mt-6 text-xs text-ink-500">
            Verdict ID:{" "}
            <code className="font-mono">{verdict.session_id}</code>
          </p>
        </div>
      </article>
    </main>
  );
}