"use client";

import { ThemeProvider } from "next-themes";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"     // <html class="dark">
      defaultTheme="light"
      enableSystem
    >
      {children}
    </ThemeProvider>
  );
}
