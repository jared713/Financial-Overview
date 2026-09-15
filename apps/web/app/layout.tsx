import "./globals.css";
import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";

export const metadata: Metadata = {
  title: "Financial Overview",
  description: "Search UK companies, pull their filed accounts, and review them with Claude",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <TopBar />
        {children}
      </body>
    </html>
  );
}
