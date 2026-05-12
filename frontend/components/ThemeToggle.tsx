"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { MoonStar, SunMedium } from "lucide-react";

export default function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  const isDark = resolvedTheme === "dark";

  return (
    <button onClick={() => setTheme(isDark ? "light" : "dark")}
      className="cursor-pointer inline-flex items-center gap-2 rounded-xl border border-[var(--border)]
                 bg-[var(--surface)] px-3 py-2 text-xs font-medium
                 text-[var(--foreground)] transition active:scale-95"
    >
      {isDark ? <SunMedium size={14} /> : <MoonStar size={14} />}
      {isDark ? "Light mode" : "Dark mode"}
    </button>
  );
}
