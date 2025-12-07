"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";

export default function Topbar() {
  const router = useRouter();
  const [username, setUsername] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(false);

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
    setTimeout(() => {
      router.push("/login");
    }, 200);
  }

  function goLogin() {
    router.push("/login");
  }

  if (isMobile){
    return null;
  } 

  return (
    <header className="flex items-center justify-between px-6 py-4 bg-[#1A0F28] border-b border-white/10">
      <input
        placeholder="Search..."
        className="rounded-full bg-white/10 px-4 py-2 text-sm placeholder:text-white/60 focus:outline-none flex-1 max-w-md"
      />

      <div className="flex items-center gap-4 text-sm text-white/80">
        {!username && (
          <button
            onClick={goLogin}
            className="
              px-4 py-2 rounded-lg text-sm
              bg-violet-600/40 hover:bg-violet-600/60
              border border-violet-400/40
              text-white transition-all duration-200
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

            <div className="h-8 w-8 rounded-full bg-white/20 border border-white/10 overflow-hidden">
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
                bg-white/10 hover:bg-red-500/40
                border border-white/10
                text-white transition-all duration-200
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
