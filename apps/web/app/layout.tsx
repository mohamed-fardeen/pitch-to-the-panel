import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "PanelMind — Adversarial feedback from synthetic VCs",
    template: "%s | PanelMind",
  },
  description:
    "PanelMind runs your startup pitch through a panel of AI personas — a VC, a designer, an operator, an expert, and a beginner. Get a structured verdict, a PDF report, and a re-pitch loop. Open source, MIT licensed.",
  keywords: [
    "startup pitch",
    "pitch feedback",
    "AI panel",
    "VC feedback",
    "multi-agent",
    "open source",
    "pitch evaluation",
  ],
  authors: [{ name: "PanelMind contributors" }],
  creator: "PanelMind",
  publisher: "PanelMind",
  metadataBase: new URL(
    process.env.NEXTAUTH_URL ?? "https://panelmind.dev"
  ),
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "/",
    title: "PanelMind — Adversarial feedback from synthetic VCs",
    description:
      "Get a panel of AI investors to critique your pitch — for free, before you ever talk to a real one.",
    siteName: "PanelMind",
  },
  twitter: {
    card: "summary_large_image",
    title: "PanelMind — Adversarial feedback from synthetic VCs",
    description:
      "Get a panel of AI investors to critique your pitch — for free.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0f172a" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className="min-h-screen bg-white text-ink-900">{children}</body>
    </html>
  );
}
