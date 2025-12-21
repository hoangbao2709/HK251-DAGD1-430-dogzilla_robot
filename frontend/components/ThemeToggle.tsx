"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  const isDark = theme === "dark";

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="px-3 py-2 rounded-xl border border-slate-300 dark:border-white/20
                 bg-white/80 dark:bg-white/10 text-xs font-medium
                 text-slate-900 dark:text-white
                 transition active:scale-95"
    >
      {isDark ? "☀ Light mode" : "🌙 Dark mode"}
    </button>
  );
}
