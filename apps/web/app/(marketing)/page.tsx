import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PanelMind — Adversarial feedback from synthetic VCs",
  description:
    "Run your pitch through a panel of AI personas (VC, designer, operator, expert, beginner). Get a structured verdict and a revision loop. Open source, MIT licensed.",
};

const personas = [
  {
    name: "Arjun (VC)",
    role: "Venture Capitalist",
    emoji: "💰",
    focus: "ROI · market size · moat",
    quote: "Where's the 10x?",
  },
  {
    name: "Priya (Designer)",
    role: "Design Strategist",
    emoji: "🎨",
    focus: "UX · engagement · delight",
    quote: "Users will bounce at step 3.",
  },
  {
    name: "Ravi (Operator)",
    role: "Operations Manager",
    emoji: "⚙️",
    focus: "Execution · risk · scale",
    quote: "This breaks at 1000 customers.",
  },
  {
    name: "Expert",
    role: "Technical Consultant",
    emoji: "🔬",
    focus: "Feasibility · fact-checks",
    quote: "That claim is wrong.",
  },
  {
    name: "Kiran (Beginner)",
    role: "Curious Consumer",
    emoji: "🤔",
    focus: "Clarity · purpose · 'why?'",
    quote: "I don't get it. Explain simpler.",
  },
] as const;

const features = [
  {
    title: "Multi-agent debate",
    body: "Five distinct AI personas argue from their worldview — they reference each other, disagree explicitly, and push the conversation forward.",
  },
  {
    title: "Three evaluation modes",
    body: "Spark (creative ideation), Venture (market and ROI), Reality (operational risks). Pick the lens that matches where you are.",
  },
  {
    title: "HITL summary approval",
    body: "Your raw pitch is refined by the LLM, then you confirm or edit before the panel starts. No surprises.",
  },
  {
    title: "Adversarial revision loop",
    body: "Get a verdict, then ask the panel to re-evaluate a stronger version. The delta is the value.",
  },
  {
    title: "PDF report export",
    body: "A shareable, professionally designed pitch evaluation. Forward to your co-founder, mentor, or investor.",
  },
  {
    title: "Multi-provider LLM",
    body: "Anthropic, OpenAI, Gemini, Groq, or local Ollama. Bring your own key, your data never leaves your control.",
  },
] as const;

const modes = [
  {
    name: "Spark",
    blurb: "Wild ideas welcome",
    description:
      "Encourage bold, unrealistic, high-risk ideas. Even if ideas sound impossible — explore them.",
    accent: "from-amber-400 to-orange-500",
  },
  {
    name: "Venture",
    blurb: "Market & ROI focus",
    description:
      "Challenge market size, moats, unit economics. Demand traction data. Be professional, direct, and skeptical.",
    accent: "from-emerald-400 to-emerald-600",
  },
  {
    name: "Reality",
    blurb: "Operational risks",
    description:
      "Uncover hidden operational blockers and technical debt risks. Assume it will break at scale.",
    accent: "from-sky-400 to-blue-600",
  },
] as const;

const codeSnippet = `# Start a pitch session (any HTTP client)
curl -X POST http://localhost:8000/api/pitches \\
  -H "Content-Type: application/json" \\
  -d '{
    "pitch": "We're building an AI-powered CRM for dentists.",
    "mode": "venture"
  }'

# Stream the panel's reactions in real-time
# (Server-Sent Events)
GET /api/pitches/{id}/stream`;

export default function Home() {
  return (
    <main className="min-h-screen">
      {/* ─── Header / Nav ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-ink-100 bg-white/80 backdrop-blur">
        <div className="container-prose flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-2 font-bold">
            <span
              className="grid h-8 w-8 place-items-center rounded-lg bg-ink-900 text-white"
              aria-hidden
            >
              ◆
            </span>
            <span className="text-lg">PanelMind</span>
          </Link>
          <nav className="hidden gap-8 md:flex">
            <Link
              href="#features"
              className="text-sm text-ink-600 hover:text-ink-900"
            >
              Features
            </Link>
            <Link
              href="#modes"
              className="text-sm text-ink-600 hover:text-ink-900"
            >
              Modes
            </Link>
            <Link
              href="https://github.com/your-org/panelmind"
              className="text-sm text-ink-600 hover:text-ink-900"
            >
              GitHub
            </Link>
            <Link
              href="/docs"
              className="text-sm text-ink-600 hover:text-ink-900"
            >
              Docs
            </Link>
          </nav>
          <Link
            href="/app/pitch/new"
            className="rounded-full bg-ink-900 px-4 py-2 text-sm font-medium text-white hover:bg-ink-700"
          >
            Try PanelMind →
          </Link>
        </div>
      </header>

      {/* ─── Hero ─────────────────────────────────────────────────────── */}
      <section className="border-b border-ink-100 py-24 sm:py-32">
        <div className="container-prose text-center">
          <p className="mb-4 text-sm font-semibold uppercase tracking-widest text-brand-700">
            Open source · MIT licensed
          </p>
          <h1 className="mx-auto max-w-4xl text-balance text-5xl font-extrabold leading-[1.05] tracking-tight text-ink-900 sm:text-7xl">
            Adversarial feedback from synthetic VCs.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-balance text-lg text-ink-600 sm:text-xl">
            PanelMind runs your startup pitch through a panel of AI personas —
            a sharp VC, a UX designer, an operator, a domain expert, and a
            curious beginner. Each one critiques it from their perspective.
          </p>
          <p className="mt-2 text-balance text-lg text-ink-600 sm:text-xl">
            The same idea as YC office hours. Available at 2 AM. In twelve
            languages. For free.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/app/pitch/new"
              className="rounded-full bg-ink-900 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-ink-900/20 hover:bg-ink-800"
            >
              Start a pitch session →
            </Link>
            <Link
              href="https://github.com/your-org/panelmind"
              className="rounded-full border border-ink-200 bg-white px-8 py-4 text-base font-semibold text-ink-900 hover:border-ink-300"
            >
              View on GitHub
            </Link>
          </div>
          <p className="mt-6 text-sm text-ink-500">
            No credit card. No signup. Bring your own API key.
          </p>
        </div>
      </section>

      {/* ─── Code snippet ─────────────────────────────────────────────── */}
      <section className="border-b border-ink-100 bg-ink-50 py-16">
        <div className="container-prose">
          <div className="mx-auto max-w-3xl overflow-hidden rounded-2xl border border-ink-200 bg-ink-950 shadow-2xl">
            <div className="flex items-center gap-2 border-b border-ink-800 bg-ink-900 px-4 py-3">
              <span className="h-3 w-3 rounded-full bg-rose-500" />
              <span className="h-3 w-3 rounded-full bg-amber-500" />
              <span className="h-3 w-3 rounded-full bg-emerald-500" />
              <span className="ml-3 text-xs text-ink-400">
                curl · POST /api/pitches
              </span>
            </div>
            <pre className="overflow-x-auto p-6 text-sm leading-relaxed text-ink-100">
              <code>{codeSnippet}</code>
            </pre>
          </div>
        </div>
      </section>

      {/* ─── Personas ─────────────────────────────────────────────────── */}
      <section className="border-b border-ink-100 py-24">
        <div className="container-prose">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-4xl font-bold tracking-tight text-ink-900 sm:text-5xl">
              The panel
            </h2>
            <p className="mt-4 text-lg text-ink-600">
              Five personas, five worldviews. They reference each other by name,
              disagree explicitly, and push the discussion forward. The most
              useful feedback comes from where they collide.
            </p>
          </div>
          <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
            {personas.map((p) => (
              <div
                key={p.name}
                className="rounded-2xl border border-ink-100 bg-white p-6 transition-shadow hover:shadow-lg"
              >
                <div className="text-3xl" aria-hidden>
                  {p.emoji}
                </div>
                <h3 className="mt-4 font-bold text-ink-900">{p.name}</h3>
                <p className="mt-1 text-sm text-ink-500">{p.role}</p>
                <p className="mt-3 text-xs font-medium uppercase tracking-wider text-brand-700">
                  {p.focus}
                </p>
                <blockquote className="mt-4 border-l-2 border-ink-200 pl-3 text-sm italic text-ink-600">
                  &ldquo;{p.quote}&rdquo;
                </blockquote>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Modes ────────────────────────────────────────────────────── */}
      <section id="modes" className="border-b border-ink-100 bg-ink-50 py-24">
        <div className="container-prose">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-4xl font-bold tracking-tight text-ink-900 sm:text-5xl">
              Three evaluation modes
            </h2>
            <p className="mt-4 text-lg text-ink-600">
              Pick the lens that matches where you are. The same panel, the
              same architecture — different priorities.
            </p>
          </div>
          <div className="mt-16 grid gap-8 lg:grid-cols-3">
            {modes.map((m) => (
              <div
                key={m.name}
                className="overflow-hidden rounded-2xl border border-ink-200 bg-white shadow-sm"
              >
                <div
                  className={`h-2 bg-gradient-to-r ${m.accent}`}
                  aria-hidden
                />
                <div className="p-8">
                  <p className="text-xs font-bold uppercase tracking-widest text-ink-500">
                    {m.blurb}
                  </p>
                  <h3 className="mt-2 text-2xl font-bold text-ink-900">
                    {m.name}
                  </h3>
                  <p className="mt-4 text-ink-600">{m.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Features grid ────────────────────────────────────────────── */}
      <section id="features" className="border-b border-ink-100 py-24">
        <div className="container-prose">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-4xl font-bold tracking-tight text-ink-900 sm:text-5xl">
              What you get
            </h2>
          </div>
          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <div key={f.title}>
                <h3 className="text-lg font-bold text-ink-900">{f.title}</h3>
                <p className="mt-2 text-ink-600">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Open source CTA ──────────────────────────────────────────── */}
      <section className="bg-ink-950 py-24 text-white">
        <div className="container-prose text-center">
          <h2 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Open source, MIT licensed.
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-ink-300">
            Self-host on your own server. Extend with your own personas. Ship
            your own vertical. We just ask for attribution.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <Link
              href="https://github.com/your-org/panelmind"
              className="rounded-full bg-white px-8 py-4 text-base font-semibold text-ink-900 hover:bg-ink-100"
            >
              Star on GitHub
            </Link>
            <Link
              href="/docs/self-hosting"
              className="rounded-full border border-ink-700 bg-ink-900 px-8 py-4 text-base font-semibold text-white hover:border-ink-600"
            >
              Self-host guide
            </Link>
          </div>
          <p className="mt-8 text-sm text-ink-400">
            <code className="rounded bg-ink-800 px-2 py-1">
              git clone https://github.com/your-org/panelmind.git && docker compose up
            </code>
          </p>
        </div>
      </section>

      {/* ─── Footer ───────────────────────────────────────────────────── */}
      <footer className="border-t border-ink-100 py-12">
        <div className="container-prose flex flex-wrap items-center justify-between gap-4 text-sm text-ink-500">
          <div className="flex items-center gap-2">
            <span
              className="grid h-6 w-6 place-items-center rounded bg-ink-900 text-xs text-white"
              aria-hidden
            >
              ◆
            </span>
            <span>PanelMind · MIT licensed</span>
          </div>
          <nav className="flex gap-6">
            <Link href="/docs" className="hover:text-ink-900">
              Docs
            </Link>
            <Link
              href="https://github.com/your-org/panelmind"
              className="hover:text-ink-900"
            >
              GitHub
            </Link>
            <Link href="/security" className="hover:text-ink-900">
              Security
            </Link>
            <Link href="/conduct" className="hover:text-ink-900">
              Code of Conduct
            </Link>
          </nav>
        </div>
      </footer>
    </main>
  );
}
