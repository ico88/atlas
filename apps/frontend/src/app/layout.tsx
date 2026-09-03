import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";
import CommandPalette from "@/components/CommandPalette";
import { I18nProvider } from "@/lib/i18n";
import "./globals.css";

export const metadata: Metadata = {
  title: "ATLAS Control Plane",
  description: "Adaptive Task & LLM Array System — local-first AI orchestration",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <I18nProvider>
          <div className="layout">
            <Sidebar />
            <main className="main">{children}</main>
          </div>
          <CommandPalette />
        </I18nProvider>
      </body>
    </html>
  );
}
