"use client";
import React, { useCallback, useEffect, useState } from "react";
import RemoteView from "@/components/control/RemoteView";
import FPVView from "@/components/control/FPVView";
import HeaderControl from "@/components/header_control";

import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import { useRouter } from "next/navigation";
import { ChevronLeft } from "lucide-react";

async function robotStop() {
  try {
    await fetch("/api/robots/robot-a/command/move/stop", { method: "POST" });
  } catch {}
}
async function getFpv() {
  return { stream_url: "/placeholder.svg?height=360&width=640", fps: 30 };
}

export default function ManualControlPage() {
  const [mode, setMode] = useState<"remote" | "fpv">("remote");
  const [fpv, setFpv] = useState<{ stream_url?: string; fps?: number }>({});
  const [isMobile, setIsMobile] = useState(false);
  const router = useRouter();

  // detect mobile để đổi layout
  useEffect(() => {
    if (typeof window === "undefined") return;

    const update = () => {
      setIsMobile(window.innerWidth < 1024); // dưới ~tablet ngang coi như mobile
    };

    update();
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
    };
  }, []);

  useEffect(() => {
    if (mode === "fpv") {
      robotStop();
      getFpv().then(setFpv).catch(() => {});
    }
  }, [mode]);

  const toggleMode = useCallback(
    () => setMode((m) => (m === "remote" ? "fpv" : "remote")),
    []
  );

  const goToConnection = useCallback(() => {
    router.push("/dashboard");
  }, [router]);

  /* ----------------- MOBILE: full tràn viền, không Sidebar/Topbar ----------------- */
  if (isMobile) {
    return (
      <div className="relative min-h-screen w-full bg-[#0c0520] text-white">
        {/* Nút quay lại Connection (floating) */}
        <button
          onClick={goToConnection}
          className="
            fixed left-3 top-3 z-50
            flex items-center gap-1
            px-3 py-1.5 rounded-full
            text-[11px] font-medium
            bg-gradient-to-r from-pink-500 to-purple-600
            text-white shadow-lg shadow-pink-500/40
            active:scale-95
          "
        >
          <ChevronLeft size={16} />
        </button>

        {mode === "remote" ? (
          <RemoteView
            onEmergencyStop={robotStop}
            mode={mode}
            toggleMode={toggleMode}
          />
        ) : (
          <section className="min-h-screen w-full bg-[#0c0520] text-white">
            <div className="mx-auto max-w-5xl px-2 py-3 space-y-3 pt-12">
              {/* chừa khoảng trên cho nút back */}
              <HeaderControl mode={mode} onToggle={toggleMode} connected={true} />
              <FPVView fps={fpv.fps ?? 30} />
            </div>
          </section>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#1A0F28] text-white">
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex flex-col flex-1">
          <Topbar />
          <section className="flex-1 w-full bg-[#0c0520] text-white p-6">
            <div className="mt-6">
              {mode === "remote" ? (
                <RemoteView
                  onEmergencyStop={robotStop}
                  mode={mode}
                  toggleMode={toggleMode}
                />
              ) : (
                <div className="space-y-4">
                  <HeaderControl mode={mode} onToggle={toggleMode} connected={true} />
                  <FPVView fps={fpv.fps ?? 30} />
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
