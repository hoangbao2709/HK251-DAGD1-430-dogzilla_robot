import type { Metadata } from "next";
import Script from "next/script";
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

const stripExtensionAttributes = `
(() => {
  const strip = () => {
    document.querySelectorAll("*").forEach((node) => {
      for (const attr of Array.from(node.attributes)) {
        if (
          attr.name === "bis_skin_checked" ||
          attr.name === "bis_register" ||
          attr.name.startsWith("__processed_")
        ) {
          node.removeAttribute(attr.name);
        }
      }
    });
  };

  strip();

  new MutationObserver(strip).observe(document.documentElement, {
    attributes: true,
    childList: true,
    subtree: true,
  });
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <Script
        id="strip-extension-hydration-attrs"
        strategy="beforeInteractive"
        dangerouslySetInnerHTML={{ __html: stripExtensionAttributes }}
      />
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
