"use client";

import ThemeToggle from "@/components/ThemeToggle";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown } from "lucide-react";
type HeaderControlProps = {
  mode: "remote" | "fpv";
  onToggle: () => void;
  lidarUrl?: string | null;
  connected: boolean;

  // lỗi truyền từ bên ngoài (vd: connect error "Failed to fetch")
  errorExternal?: string | null;

  // flag robot_connected từ ngoài nếu có
  robotConnectedFlag?: boolean | null;

  // log lệnh gửi đi
  commandLog?: string[];
};

type SystemTelemetry = {
  cpu_percent: number | null;
  ram: string | null;
  disk: string | null;
  ip: string | null;
  time: string | null;
};

type Telemetry = {
  robot_connected: boolean;
  turn_speed_range?: [number, number];
  step_default?: number;
  z_range?: [number, number];
  z_current?: number;
  pitch_range?: [number, number];
  pitch_current?: number;
  battery?: number | null;
  fw?: string | null;
  fps?: number | null;
  system?: SystemTelemetry | null;
};

type LidarPose = {
  x: number;
  y: number;
  theta?: number;
  connected: string;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
const robotId = "robot-a";
const CONTROL_PREFIX = "/control/api/robots";


async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white/5 border border-white/10 p-3">
      <div className="text-[10px] uppercase opacity-60">{label}</div>
      <div className="text-sm mt-1">{value}</div>
    </div>
  );
}

function buildLidarPoseUrl(lidarUrl: string) {
  if (!lidarUrl) return "";
  if (lidarUrl.endsWith("/pose") || lidarUrl.endsWith("/pose/")) {
    return lidarUrl;
  }

  try {
    const u = new URL(lidarUrl);
    if (u.pathname.endsWith("/pose") || u.pathname.endsWith("/pose/")) {
      return u.toString();
    }
    if (!u.pathname.endsWith("/")) {
      u.pathname += "/";
    }
    u.pathname += "pose";
    return u.toString();
  } catch {
    return `${lidarUrl.replace(/\/$/, "")}/pose`;
  }
}

export default function HeaderControl({
  mode,
  onToggle,
  lidarUrl,
  connected,
  errorExternal,
  robotConnectedFlag,
  commandLog,
}: HeaderControlProps) {
  const isFPV = mode === "fpv";

  const [robotName, setRobotName] = useState<string>("Robot A");
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorStatus, setErrorStatus] = useState<string | null>(null);
  const [locationText, setLocationText] = useState<string>("-");
  const [collapsed, setCollapsed] = useState(false);
  // NEW: chế độ hiển thị: debug (status + log) / info (metrics)
  const [viewMode, setViewMode] = useState<"debug" | "info">("debug");

  // -------- Poll /status/ trên backend --------
  useEffect(() => {
    let isMounted = true;

    async function fetchStatus() {
      try {
        const data = await api<any>(`${CONTROL_PREFIX}/${robotId}/status/`);
        if (!isMounted) return;

        setRobotName(data.name || "Robot A");

        const t: Telemetry =
          data.telemetry ?? {
            robot_connected: data.robot_connected ?? false,
            turn_speed_range: data.turn_speed_range,
            step_default: data.step_default,
            z_range: data.z_range,
            z_current: data.z_current,
            pitch_range: data.pitch_range,
            pitch_current: data.pitch_current,
            battery: data.battery,
            fw: data.fw,
            fps: data.fps,
            system: data.system ?? null,
          };

        setTelemetry(t);
        setErrorStatus(null);
        setLoading(false);
      } catch (e: any) {
        console.error("Fetch status error", e);
        if (!isMounted) return;
        setErrorStatus(e?.message || "Cannot fetch robot status");
        setLoading(false);
      }
    }

    fetchStatus();
    const id = setInterval(fetchStatus, 2000);
    return () => {
      isMounted = false;
      clearInterval(id);
    };
  }, []);

  // -------- Poll Lidar pose --------
  useEffect(() => {
    if (!lidarUrl) {
      setLocationText("-");
      return;
    }

    const poseUrl = buildLidarPoseUrl(lidarUrl);
    let stop = false;

    async function fetchPose() {
      try {
        const res = await fetch(poseUrl, { cache: "no-store" });
        if (!res.ok) throw new Error(`Pose HTTP ${res.status}`);
        const raw = await res.json();
        if (stop) return;

        const p: LidarPose = raw;
        if (typeof p?.x === "number" && typeof p?.y === "number") {
          const x = p.x.toFixed(2);
          const y = p.y.toFixed(2);
          const thetaText =
            typeof p.theta === "number" ? `, θ: ${p.theta.toFixed(2)} rad` : "";
          setLocationText(`x: ${x} m, y: ${y} m${thetaText}`);
        } else {
          setLocationText("-");
        }
      } catch {
        if (!stop) setLocationText("-");
      }
    }

    fetchPose();
    const id = setInterval(fetchPose, 1000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [lidarUrl]);

  const sys: SystemTelemetry | null = telemetry?.system ?? null;

  const cpuText =
    sys?.cpu_percent != null ? `${sys.cpu_percent}%` : loading ? "…" : "-";
  const ramText = sys?.ram ?? (loading ? "…" : "-");
  const diskText = sys?.disk ?? (loading ? "…" : "-");
  const ipText = sys?.ip ?? (loading ? "…" : "-");
  const batteryValue =
    telemetry?.battery != null ? `${telemetry.battery}%` : loading ? "…" : "-";

  // gộp lỗi: lỗi status + lỗi connect từ ngoài
  const mergedError = errorExternal || errorStatus;

  return (
    <div className=" mb-5">
      {/* HEADER TRÊN CÙNG */}
      <header className="flex items-center justify-between ">
        <h1
          className={`gradient-title select-none transition-all duration-300 ${isFPV ? "opacity-100" : "opacity-90"
            }`}
        >
          {isFPV ? "FPV CONTROL MODE" : "REMOTE CONTROL MODE"}
        </h1>

        <div className="flex items-center gap-3">
          <Link
            href="/control"
            className="
              px-3 py-1 rounded-xl
              bg-pink-500/20 
              hover:bg-pink-500/30 
              text-pink-300 text-sm
              transition-all
              hover:scale-[1.03]
              active:scale-95
            "
          >
            Disconnect
          </Link>

          <ThemeToggle />

          <span className="text-sm opacity-70">Remote</span>
          <button
            onClick={onToggle}
            className={`w-11 h-7 rounded-full border border-violet-400/50 p-1 grid items-center transition-all duration-300 ${isFPV ? "bg-violet-500/40" : "bg-transparent"
              }`}
            aria-label="Toggle FPV mode"
          >
            <div
              className={`w-5 h-5 rounded-full border border-violet-300/60 bg-white/10 transition-transform duration-300 ${isFPV ? "translate-x-4" : ""
                }`}
            />
          </button>
          <span className="text-sm">FPV</span>
        </div>
      </header>

        {/* ROBOT CARD */}
        <div className="relative col-span-2 p-4 rounded-2xl bg-white/5 border border-white/10 ">
          {/* hàng trên: tên robot + trạng thái connect + nút Debug/Info */}
          <div className="flex flex-wrap items-center gap-4 mb-2">
            <div className="text-lg font-semibold">🤖 {robotName}</div>

            <span
              className={
                connected
                  ? "text-xs font-medium text-emerald-400"
                  : "text-xs font-medium text-rose-400"
              }
            >
              {connected ? "Connected" : "Not connected"}
            </span>

            {sys?.time && (
              <div className="text-xs opacity-60">Time: {sys.time}</div>
            )}

            {/* toggle Debug / Info */}
            <div className="ml-auto flex items-center gap-2">
              <span className="text-[11px] opacity-60">View:</span>
              <button
                onClick={() => setViewMode("debug")}
                className={`px-2 py-1 rounded-lg text-[11px] border transition-all ${
                  viewMode === "debug"
                    ? "bg-pink-500/40 border-pink-300 text-pink-50"
                    : "bg-white/5 border-white/20 text-white/70"
                }`}
              >
                Debug
              </button>
              <button
                onClick={() => setViewMode("info")}
                className={`px-2 py-1 rounded-lg text-[11px] border transition-all ${
                  viewMode === "info"
                    ? "bg-sky-500/40 border-sky-300 text-sky-50"
                    : "bg-white/5 border-white/20 text-white/70"
                }`}
              >
                Info
              </button>
            </div>
          </div>

          {/* NỘI DUNG: animate collapse/expand */}
          <div
            className={`mt-2 overflow-hidden transition-all duration-300 ${
              collapsed ? "max-h-0 opacity-0" : "max-h-72 opacity-100"
            }`}
          >
            {viewMode === "debug" ? (
              // ===== DEBUG VIEW: status + command log =====
              <div className="flex gap-4 h-40">
                {/* STATUS TEXT */}
                <div className="space-y-1 text-xs leading-relaxed w-56">
                  {mergedError && (
                    <div>
                      <span className="font-semibold text-rose-300">
                        Status error:{" "}
                      </span>
                      <span className="text-rose-200">{mergedError}</span>
                    </div>
                  )}

                  <div>
                    <span className="font-semibold opacity-80">
                      Robot connected flag:{" "}
                    </span>
                    <span className="text-amber-200">
                      {String(
                        robotConnectedFlag ??
                          telemetry?.robot_connected ??
                          false
                      )}
                    </span>
                  </div>

                  {lidarUrl && (
                    <div className="truncate">
                      <span className="font-semibold opacity-80">
                        Lidar URL:{" "}
                      </span>
                      <span className="text-sky-300">{lidarUrl}</span>
                    </div>
                  )}

                  <div>
                    <span className="font-semibold opacity-80">
                      Location:{" "}
                    </span>
                    <span>{locationText}</span>
                  </div>
                </div>

                {/* COMMAND LOG FULL WIDTH */}
                <div className="flex flex-col w-full mx-2">
                  <div className="rounded-xl bg-black/40 border border-white/10 px-3 py-2 text-[11px] font-mono overflow-y-auto flex-1">
                    {commandLog && commandLog.length > 0 ? (
                      commandLog.map((line, idx) => (
                        <div key={idx} className="whitespace-pre-wrap">
                          {line}
                        </div>
                      ))
                    ) : (
                      <span className="opacity-50">
                        No command log yet. 
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              // ===== INFO VIEW: metrics =====
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm h-40 items-start content-start">
                <Metric label="Location" value={locationText} />
                <Metric label="CPU" value={cpuText} />
                <Metric label="RAM" value={ramText} />
                <Metric label="SDC" value={diskText} />
                <Metric label="IPA" value={ipText} />
                <Metric label="Battery" value={batteryValue} />
              </div>
            )}
          </div>

          {/* NÚT COLLAPSE Ở GÓC PHẢI DƯỚI */}
          <button
            onClick={() => setCollapsed((v) => !v)}
            className="absolute -bottom-3 cursor-pointer right-6 w-7  h-7 rounded-full text-black hover:text-white border border-white/20 bg-gray-400 flex items-center justify-center shadow-md hover:bg-white/10 transition-all"
            aria-label="Toggle details"
          >
            <ChevronDown
              size={16}
              className={`transition-transform duration-300 ${
                collapsed ? "" : "rotate-180"
              }`}
            />
          </button>
        </div>
    </div>
  );
}
