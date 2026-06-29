import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Corenexia — God View",
  description: "Infinite Dynamic Orchestrator — live admin view",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-900 text-slate-100">{children}</body>
    </html>
  );
}
