import type { Metadata } from "next";
import "./globals.css";
import "leaflet/dist/leaflet.css";
import { WorkspaceHeader } from "@/components/workspace-header";

export const metadata: Metadata = {
  title: "Ryde Tribunal",
  description: "Evidence-led review of rider and driver disputes.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 antialiased"><WorkspaceHeader /><div id="workspace-content">{children}</div></body>
    </html>
  );
}
