"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import ThemeToggle from "@/components/ThemeToggle";
import {
  Link2,
  Gamepad2,
  Bot,
  BarChart3,
  LogOut,
  ChevronLeft,
  ChevronRight,
  LogIn,
} from "lucide-react";

const menu = [
  { href: "/dashboard", label: "Connection", icon: Link2 },
  { href: "/control", label: "Manual Control", icon: Gamepad2 },
  { href: "/autonomous", label: "Autonomous Control", icon: Bot },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

export default function Sidebar() {
  const path = usePathname();
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";

  useEffect(() => {
    if (typeof window === "undefined") return;

    const detect = () => {
      const ua =
        typeof navigator !== "undefined" ? navigator.userAgent || "" : "";
      const uaMobile =
        /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobi/i.test(
          ua
        );

      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const sizeMobile = vw <= 1024 && vh <= 820;

      const mobile = uaMobile || sizeMobile;
      setIsMobile(mobile);
      setCollapsed(mobile ? true : false);
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
    setIsLoggedIn(false);
    router.push("/login");
  }

  const goLogin = () => router.push("/login");

  return (
    <aside
      className={`
        ${isDark
          ? "bg-[linear-gradient(180deg,rgba(22,6,38,0.98),rgba(12,5,32,0.96))]"
          : "bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(245,242,255,0.96))]"
        }
        border-r border-[var(--border)] flex flex-col justify-between
        transition-all duration-300 z-50 h-screen
        shadow-[8px_0_30px_rgba(124,77,255,0.04)]
        ${collapsed ? "w-16" : "w-64"}
      `}
    >
      <div className="flex flex-col items-center pt-4 pb-4 relative">
        {!isMobile && (
          <button
            onClick={() => setCollapsed((prev) => !prev)}
            className="
              absolute -right-4 top-8
              w-9 h-9 sm:w-10 sm:h-10
              rounded-full
              bg-[var(--surface-elev)]
              border border-[var(--border)]
              flex items-center justify-center
              text-[var(--foreground)]/80
              hover:text-[var(--foreground)]
              hover:bg-[var(--surface-2)]
              transition-all duration-300
              shadow-md hover:shadow-black/10
              hover:scale-110 active:scale-95
              cursor-pointer
            "
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRight size={24} strokeWidth={2.6} /> : <ChevronLeft size={24} strokeWidth={2.8} />}
          </button>
        )}

        <div className="flex flex-col items-center">
          <Image
            src="/logo_hongtrang.png"
            alt="RobotControl Logo"
            width={collapsed ? 40 : 56}
            height={collapsed ? 40 : 56}
            className="rounded-full mb-2 transition-all duration-300"
          />
          {!collapsed && (
            <h1
              className={`whitespace-nowrap font-extrabold text-lg tracking-wide text-center leading-none ${
                isDark
                  ? "text-pink-300 drop-shadow-[0_1px_0_rgba(0,0,0,0.35)]"
                  : "text-[var(--accent)] drop-shadow-[0_1px_0_rgba(255,255,255,0.85)]"
              }`}
            >
              RobotControl
            </h1>
          )}
        </div>
      </div>

      <nav className="flex-1 w-full mt-1 space-y-1 px-2 sm:px-3">
        {menu.map((item) => {
          const Icon = item.icon;
          const active = path.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`
                flex items-center gap-3 rounded-xl px-3 py-3 text-xs sm:text-sm font-medium
                transition-all
                ${
                  active
                    ? "bg-gradient-to-r from-[#FD749B] to-[#7C4DFF] text-white shadow-md shadow-pink-500/20 ring-1 ring-pink-300/40"
                    : isDark
                    ? "text-white/72 hover:bg-white/5 hover:text-white"
                    : "text-[var(--foreground)]/72 hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                }
                ${collapsed ? "justify-center" : ""}
              `}
            >
              <Icon size={18} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="p-2 sm:p-3 border-t border-[var(--border)] space-y-2">
        <div className="flex items-center justify-between gap-2 px-2">
          {!collapsed && (
            <span className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted-2)]">
              Theme
            </span>
          )}
          <ThemeToggle />
        </div>

        {!isLoggedIn && (
          <button
            onClick={goLogin}
            className={`
              flex items-center gap-3 text-xs sm:text-sm
              px-3 py-2 w-full rounded-xl
              bg-gradient-to-r from-[#FD749B] via-[#8c63ff] to-[#00b8ff]
              text-white shadow-md shadow-pink-500/25
              hover:brightness-110 active:scale-95 transition-all
              ${collapsed ? "justify-center" : ""}
            `}
          >
            <LogIn size={18} />
            {!collapsed && <span>Login</span>}
          </button>
        )}

        {isLoggedIn && (
          <button
            onClick={logout}
            className={`
              flex items-center gap-3 text-xs sm:text-sm
              text-[var(--foreground)]/70 hover:text-[var(--foreground)]
              hover:bg-red-500/10
              px-3 py-2 rounded-xl w-full
              transition-all
              ${collapsed ? "justify-center" : ""}
            `}
          >
            <LogOut size={18} />
            {!collapsed && <span>Log Out</span>}
          </button>
        )}
      </div>
    </aside>
  );
}
