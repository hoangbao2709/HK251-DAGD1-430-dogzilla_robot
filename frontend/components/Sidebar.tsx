"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
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

  const [collapsed, setCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const detect = () => {
      // 1) Dựa vào user agent xem có phải mobile device không
      const ua =
        typeof navigator !== "undefined" ? navigator.userAgent || "" : "";
      const uaMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobi/i.test(
        ua
      );

      // 2) Dựa thêm vào kích thước viewport (phòng trường hợp devtools / tablet)
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const sizeMobile = vw <= 1024 && vh <= 820; // phone / small tablet

      const mobile = uaMobile || sizeMobile;

      setIsMobile(mobile);

      if (mobile) {
        // Điện thoại: luôn thu gọn, không cho mở
        setCollapsed(true);
      } else {
        // Desktop: mặc định mở
        setCollapsed(false);
      }
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

  const goLogin = () => {
    router.push("/login");
  };
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  return (
    <aside
      className={`
        bg-[#160626] border-r border-white/10 flex flex-col justify-between
        transition-all duration-300 z-50
        h-screen
        ${collapsed ? "w-16" : "w-64"}
      `}
    >
      <div className="flex flex-col items-center pt-4 pb-4 relative">
        {/* Nút toggle: CHỈ desktop, mobile thì ẩn hoàn toàn */}
        {!isMobile && (
          <button
            onClick={() => setCollapsed((prev) => !prev)}
            className="
              absolute -right-4 top-8
              w-9 h-9 sm:w-10 sm:h-10
              rounded-full
              bg-[#1f0d33]
              border border-white/20
              flex items-center justify-center
              text-white/80
              hover:text-white
              hover:bg-purple-600/80
              hover:border-purple-300/70
              transition-all duration-300
              shadow-md hover:shadow-purple-500/40
              hover:scale-110 active:scale-95
              cursor-pointer
            "
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronRight size={24} strokeWidth={2.6} />
            ) : (
              <ChevronLeft size={24} strokeWidth={2.8} />
            )}
          </button>
        )}

        {/* Logo */}
        <div className="flex flex-col items-center">
          <Image
            src="/logo_hongtrang.png"
            alt="RobotControl Logo"
            width={collapsed ? 40 : 56}
            height={collapsed ? 40 : 56}
            className="rounded-full mb-2 transition-all duration-300"
          />
          {!collapsed && (
            <h1 className="text-pink-400 font-bold text-lg tracking-wide text-center">
              RobotControl
            </h1>
          )}
        </div>
      </div>

      {/* Menu */}
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
                    ? "bg-gradient-to-r from-pink-500 to-purple-600 text-white shadow-md"
                    : "text-white/70 hover:bg-white/5 hover:text-white"
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

      {/* --- Bottom actions --- */}
      <div className="p-2 sm:p-3 border-t border-white/10 space-y-2">
        {/* LOGIN: chỉ khi chưa đăng nhập */}
        {!isLoggedIn && (
          <button
            onClick={goLogin}
            className={`
              flex items-center gap-3 text-xs sm:text-sm
              px-3 py-2 w-full rounded-xl
              bg-gradient-to-r from-pink-500 to-purple-600
              text-white shadow-md shadow-pink-500/40
              hover:brightness-110 active:scale-95 transition-all
              ${collapsed ? "justify-center" : ""}
            `}
          >
            <LogIn size={18} />
            {!collapsed && <span>Login</span>}
          </button>
        )}

        {/* LOGOUT: chỉ khi đã đăng nhập */}
        {isLoggedIn && (
          <button
            onClick={logout}
            className={`
              flex items-center gap-3 text-xs sm:text-sm
              text-white/70 hover:text-white
              hover:bg-red-500/20
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
