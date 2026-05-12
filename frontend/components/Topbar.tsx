"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { Search } from "lucide-react";
import { useTheme } from "next-themes";

type SearchItem = {
  label: string;
  href: string;
  description: string;
  keywords: string[];
};

export default function Topbar() {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(false);
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => setMounted(true), []);
  const isDark = mounted && resolvedTheme === "dark";

  const searchItems: SearchItem[] = [
    {
      label: "Dashboard",
      href: "/dashboard",
      description: "Connection manager and robot cards",
      keywords: ["dashboard", "connection", "robot", "status"],
    },
    {
      label: "Manual Control",
      href: "/control",
      description: "Joystick, speed, LiDAR, posture",
      keywords: ["control", "manual", "speed", "lidar", "posture", "behavior"],
    },
    {
      label: "Autonomous Control",
      href: "/autonomous",
      description: "QR, SLAM, saved points, voice commands",
      keywords: ["autonomous", "qr", "slam", "points", "voice", "navigation"],
    },
    {
      label: "Analytics",
      href: "/analytics",
      description: "Health, events, and usage overview",
      keywords: ["analytics", "events", "health", "battery", "log"],
    },
    {
      label: "LiDAR view",
      href: "/autonomous",
      description: "Open the LiDAR / SLAM panel",
      keywords: ["lidar", "map", "slam", "scan"],
    },
    {
      label: "QR detections",
      href: "/autonomous",
      description: "Open the QR detection panel",
      keywords: ["qr", "camera", "top-down", "detections"],
    },
    {
      label: "Saved points",
      href: "/autonomous",
      description: "Open waypoint management",
      keywords: ["points", "waypoint", "save", "goto"],
    },
  ];

  const normalizedQuery = query.trim().toLowerCase();
  const filteredItems = normalizedQuery
    ? searchItems.filter((item) =>
        [item.label, item.description, ...item.keywords].some((value) =>
          value.toLowerCase().includes(normalizedQuery)
        )
      )
    : searchItems.slice(0, 4);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const detect = () => {
      const ua =
        typeof navigator !== "undefined" ? navigator.userAgent || "" : "";
      const uaMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobi/i.test(
        ua
      );

      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const sizeMobile = vw <= 1024 && vh <= 820;

      setIsMobile(uaMobile || sizeMobile);
    };

    detect();
    window.addEventListener("resize", detect);
    window.addEventListener("orientationchange", detect);
    return () => {
      window.removeEventListener("resize", detect);
      window.removeEventListener("orientationchange", detect);
    };
  }, []);

  function logout() {
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("username");
    }
    setUsername(null);
    setTimeout(() => router.push("/login"), 200);
  }

  function goLogin() {
    router.push("/login");
  }

  const handleNavigate = (href: string) => {
    setQuery("");
    setFocused(false);
    router.push(href);
    inputRef.current?.blur();
  };

  if (isMobile) return null;

  return (
    <header
      className={`flex items-center justify-between px-6 py-4 border-b border-[var(--border)] ${
        isDark
          ? "bg-[linear-gradient(90deg,rgba(22,6,38,0.96),rgba(12,5,32,0.92))] shadow-[0_1px_0_rgba(255,255,255,0.03)]"
          : "bg-[linear-gradient(90deg,rgba(255,255,255,0.96),rgba(245,242,255,0.94))] shadow-[0_1px_0_rgba(124,77,255,0.03)]"
      }`}
    >
      <div className="relative flex-1 max-w-xl">
        <div
          className={`flex items-center gap-2 rounded-full border px-4 py-2 text-sm text-[var(--foreground)]/85 focus-within:shadow-[0_0_0_3px_rgba(124,77,255,0.08)] ${
            isDark
              ? "bg-[var(--surface-elev)] border-[rgba(255,255,255,0.08)] focus-within:border-[#7c4dff]/35"
              : "bg-[var(--surface)] border-[var(--border)] focus-within:border-[#7c4dff]/35"
          }`}
        >
          <Search size={16} className="shrink-0 text-[#8c63ff]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => {
              window.setTimeout(() => setFocused(false), 120);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                if (filteredItems[0]) handleNavigate(filteredItems[0].href);
              }
              if (e.key === "Escape") {
                setQuery("");
                setFocused(false);
                inputRef.current?.blur();
              }
            }}
            placeholder="Search pages or robot features..."
            className="w-full bg-transparent text-sm placeholder:text-[var(--muted-2)] outline-none"
          />
        </div>

        {focused && filteredItems.length > 0 ? (
          <div
            className={`absolute left-0 right-0 top-[calc(100%+8px)] z-50 overflow-hidden rounded-2xl border border-[var(--border)] shadow-2xl ${
              isDark ? "bg-[var(--surface-elev)] shadow-black/20" : "bg-[var(--surface)] shadow-black/10"
            }`}
          >
            <div className="px-4 py-2 text-[10px] uppercase tracking-[0.22em] text-[var(--muted-2)]">
              Quick search
            </div>
            <div className="max-h-72 overflow-y-auto">
              {filteredItems.map((item) => (
                <button key={`${item.label}-${item.href}`}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleNavigate(item.href);
                  }}
                  className="cursor-pointer flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-[var(--surface-2)]"
                >
                  <div className="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full bg-cyan-400" />
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-[var(--foreground)]">{item.label}</div>
                    <div className="mt-0.5 text-xs text-[var(--muted-2)]">{item.description}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-4 text-sm text-[var(--foreground)]/80">
        {!username && (
          <button
            onClick={goLogin}
            className="
              px-4 py-2 rounded-lg text-sm
              bg-gradient-to-r from-[#FD749B]/20 to-[#7C4DFF]/20 hover:from-[#FD749B]/25 hover:to-[#00C2FF]/20
              border border-violet-400/30
              text-[var(--foreground)] transition-all duration-200
              hover:scale-105 active:scale-95
              cursor-pointer
            "
          >
            Login
          </button>
        )}

        {username && (
          <>
            <span className="font-medium">{username}</span>

            <div className="h-8 w-8 rounded-full bg-[var(--surface)] border border-[var(--border)] overflow-hidden">
              <Image
                src="/logo_hongtrang.png"
                alt="RobotControl Logo"
                width={32}
                height={32}
                className="h-full w-full object-cover"
              />
            </div>

            <button
              onClick={logout}
              className="
                px-3 py-1 rounded-lg text-xs
                bg-[var(--surface)] hover:bg-red-500/20
                border border-[var(--border)]
                text-[var(--foreground)] transition-all duration-200
                hover:scale-105 active:scale-95
                shadow-sm hover:shadow-red-500/20
                cursor-pointer
              "
            >
              Logout
            </button>
          </>
        )}
      </div>
    </header>
  );
}
