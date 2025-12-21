import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Dogzilla Control",
  description: "Remote control web UI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`
          ${geistSans.variable} ${geistMono.variable}
          min-h-screen
          bg-slate-50 text-slate-900         /* LIGHT */
          dark:bg-[#0c0520] dark:text-white /* DARK  */
          antialiased
        `}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
