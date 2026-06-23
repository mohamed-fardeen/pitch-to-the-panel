"use client";

import { signOut } from "next-auth/react";
import Link from "next/link";

export default function SignOutPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-ink-50 to-white flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <Link href="/" className="flex items-center gap-2 justify-center mb-12">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-ink-900 text-white text-xl">
            ◆
          </span>
          <span className="text-xl font-bold text-ink-900">PanelMind</span>
        </Link>

        <div className="bg-white rounded-3xl border border-ink-100 shadow-xl p-10 text-center">
          <h1 className="text-3xl font-extrabold text-ink-900 tracking-tight">
            Sign out
          </h1>
          <p className="mt-3 text-ink-500">
            Are you sure you want to sign out?
          </p>

          <button
            type="button"
            onClick={() => signOut({ callbackUrl: "/" })}
            className="mt-8 w-full rounded-2xl bg-ink-900 py-4 text-base font-semibold text-white hover:bg-ink-700 transition-colors"
          >
            Yes, sign me out
          </button>

          <Link
            href="/"
            className="mt-3 inline-block text-sm text-ink-400 hover:text-ink-900 underline"
          >
            Cancel — go back
          </Link>
        </div>
      </div>
    </div>
  );
}
