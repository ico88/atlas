import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";
import CommandPalette from "@/components/CommandPalette";
import { I18nProvider } from "@/lib/i18n";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "ALMA",
  description: "ALMA — the human interface to ATLAS, a local-first AI platform",
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
          <AuthProvider>
            <div className="layout">
              <Sidebar />
              <main className="main">{children}</main>
            </div>
            <CommandPalette />
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
