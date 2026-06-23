"use client";

import { signIn } from "next-auth/react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

function SignInForm() {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") ?? "/app/pitch/new";
  const error = searchParams.get("error");

  // Detect which providers are configured (via the public auth endpoint
  // would require a server fetch; for now, infer from presence of buttons).
  const [submitting, setSubmitting] = useState<string | null>(null);

  const handleProvider = async (provider: "google" | "github") => {
    setSubmitting(provider);
    try {
      await signIn(provider, { callbackUrl });
    } catch (err) {
      console.error("Sign-in failed:", err);
      setSubmitting(null);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-ink-50 to-white flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <Link href="/" className="flex items-center gap-2 justify-center mb-12">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-ink-900 text-white text-xl">
            ◆
          </span>
          <span className="text-xl font-bold text-ink-900">PanelMind</span>
        </Link>

        <div className="bg-white rounded-3xl border border-ink-100 shadow-xl p-10">
          <h1 className="text-3xl font-extrabold text-ink-900 tracking-tight text-center">
            Sign in
          </h1>
          <p className="mt-3 text-ink-500 text-center">
            Continue to your pitch panel.
          </p>

          {error && (
            <div className="mt-6 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
              <strong>Sign-in error:</strong> {error}
              <p className="mt-1 text-xs">
                Try again, or contact support if the problem persists.
              </p>
            </div>
          )}

          <div className="mt-8 space-y-3">
            <button
              type="button"
              onClick={() => handleProvider("google")}
              disabled={submitting !== null}
              className="w-full flex items-center justify-center gap-3 rounded-2xl border border-ink-200 bg-white py-4 text-base font-semibold text-ink-900 hover:bg-ink-50 transition-colors disabled:opacity-50"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" aria-hidden>
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              {submitting === "google" ? "Redirecting…" : "Continue with Google"}
            </button>

            <button
              type="button"
              onClick={() => handleProvider("github")}
              disabled={submitting !== null}
              className="w-full flex items-center justify-center gap-3 rounded-2xl border border-ink-200 bg-white py-4 text-base font-semibold text-ink-900 hover:bg-ink-50 transition-colors disabled:opacity-50"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
              </svg>
              {submitting === "github" ? "Redirecting…" : "Continue with GitHub"}
            </button>
          </div>

          <p className="mt-8 text-center text-xs text-ink-400">
            By signing in, you agree to our{" "}
            <a href="/conduct" className="underline hover:text-ink-600">
              Code of Conduct
            </a>
            .
          </p>
        </div>

        <p className="mt-8 text-center text-sm text-ink-500">
          <Link href="/" className="hover:text-ink-900 underline">
            ← Back to home
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-ink-400">Loading…</p>
      </div>
    }>
      <SignInForm />
    </Suspense>
  );
}
