import "./globals.css";
import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { WorkspaceProvider } from "@/components/WorkspaceProvider";

export const metadata: Metadata = {
  title: "Financial Overview",
  description: "Search UK companies, pull their filed accounts, and review them with Claude",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* Both workspaces keep their state here, so moving between Companies and
            Industries loses nothing and runs keep polling in the background. */}
        <WorkspaceProvider>
          <TopBar />
          {children}
        </WorkspaceProvider>
      </body>
    </html>
  );
}
