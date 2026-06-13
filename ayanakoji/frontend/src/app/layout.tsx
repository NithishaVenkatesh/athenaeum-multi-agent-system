import type { Metadata } from "next";
import { Geist, Geist_Mono, Fraunces } from "next/font/google";
import "./globals.css";
import { ColosseumBackdrop } from "@/components/colosseum-backdrop";
import { PersonaProvider } from "@/components/persona-provider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Serif display face — gives the academy/atelier wordmark and headings character.
const fraunces = Fraunces({
  variable: "--font-display",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Athenaeum",
  description: "A learning workspace where every course is a conversation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} h-full antialiased`}
    >
      <body className="bg-paper flex min-h-full flex-col">
        <ColosseumBackdrop />
        <PersonaProvider>{children}</PersonaProvider>
      </body>
    </html>
  );
}
