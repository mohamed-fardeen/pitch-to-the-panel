import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pitch to the Panel",
  description: "Pitch your startup to an AI panel and get instant feedback.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased bg-gray-900 text-white min-h-screen font-sans">
        {children}
      </body>
    </html>
  );
}
