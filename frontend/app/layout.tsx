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
  title: "RobotControl",
  description: "Remote control web UI",
  icons: {
    icon: "/logo_hongtrang.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        className={`
          ${geistSans.variable} ${geistMono.variable}
          min-h-screen
          bg-[var(--background)] text-[var(--foreground)]
          antialiased
        `}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
