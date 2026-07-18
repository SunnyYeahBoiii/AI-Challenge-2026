import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FrameSeeker - AI Video Search",
  description: "AI-powered video frame search for AI Challenge 2026",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
