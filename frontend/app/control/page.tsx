"use client";

import React, { useCallback, useEffect, useState } from "react";
import RemoteView from "@/components/control/RemoteView";
import FPVView from "@/components/control/FPVView";
import HeaderControl from "@/components/header_control";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import { useRouter } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { getRobotSession } from "./../lib/robotSession";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

async function robotStop(robotId: string) {
  try {
    await fetch(`${API_BASE}/control/api/robots/${robotId}/command/move/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        vx: 0,
        vy: 0,
        vz: 0,
        rx: 0,
        ry: 0,
        rz: 0,
      }),
    });
  } catch {}
}

async function getFpv(robotId: string) {
  try {
    const res = await fetch(`${API_BASE}/control/api/robots/${robotId}/fpv/`, {
      cache: "no-store",
    });

    const data = await res.json().catch(() => ({}));
    return {
      stream_url: data.stream_url || "/placeholder.svg?height=360&width=640",
      fps: data.fps || 30,
    };
  } catch {
    return { stream_url: "/placeholder.svg?height=360&width=640", fps: 30 };
  }
}

export default function ManualControlPage() {
  const [mode, setMode] = useState<"remote" | "fpv">("remote");
  const [fpv, setFpv] = useState<{ stream_url?: string; fps?: number }>({});
  const [isMobile, setIsMobile] = useState(false);
  const [robotIp, setRobotIp] = useState("");
  const [robotId, setRobotId] = useState("robot-a");
  const router = useRouter();

  useEffect(() => {
    const session = getRobotSession();

    if (!session.ip) {
      router.push("/dashboard");
      return;
    }

    setRobotIp(session.ip);
    setRobotId(session.robotId || "robot-a");
  }, [router]);

  useEffect(() => {
    if (!robotIp) return;

    async function connectRobot() {
      try {
        await fetch(`${API_BASE}/control/api/robots/${robotId}/connect/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ addr: robotIp }),
        });
      } catch (error) {
        console.error("Auto connect failed:", error);
      }
    }

    connectRobot();
  }, [robotIp, robotId]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const update = () => {
      setIsMobile(window.innerWidth < 1024);
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
      robotStop(robotId);
      getFpv(robotId).then(setFpv).catch(() => {});
    }
  }, [mode, robotId]);

  const toggleMode = useCallback(
    () => setMode((m) => (m === "remote" ? "fpv" : "remote")),
    []
  );

  const goToConnection = useCallback(() => {
    router.push("/dashboard");
  }, [router]);

  if (isMobile) {
    return (
      <div className="relative min-h-screen w-full bg-slate-50 text-slate-900 dark:bg-[#0c0520] dark:text-white">
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

        <div className="px-3 pt-12 text-xs text-white/60">
          Robot: {robotId} | IP: {robotIp || "No robot selected"}
        </div>

        {mode === "remote" ? (
          <RemoteView
            onEmergencyStop={() => robotStop(robotId)}
            mode={mode}
            toggleMode={toggleMode}
          />
        ) : (
          <section className="min-h-screen w-full bg-slate-50 text-slate-900 dark:bg-[#0c0520] dark:text-white pt-12">
            <div className="mx-auto max-w-5xl px-2 py-3 space-y-3">
              <HeaderControl
                mode={mode}
                onToggle={toggleMode}
                connected={true}
              />
              <FPVView fps={fpv.fps ?? 30} />
            </div>
          </section>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 dark:bg-[#1A0F28] dark:text-white">
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex flex-col flex-1">
          <Topbar />
          <section className="flex-1 w-full bg-slate-50 text-slate-900 dark:bg-[#0c0520] dark:text-white p-6">
            <div className="mb-3 text-xs text-white/60">
              Robot: {robotId} | IP: {robotIp || "No robot selected"}
            </div>

            {mode === "remote" ? (
              <RemoteView
                onEmergencyStop={() => robotStop(robotId)}
                mode={mode}
                toggleMode={toggleMode}
              />
            ) : (
              <div className="space-y-4">
                <HeaderControl
                  mode={mode}
                  onToggle={toggleMode}
                  connected={true}
                />
                <FPVView fps={fpv.fps ?? 30} />
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}