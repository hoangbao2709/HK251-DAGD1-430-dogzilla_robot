"use client";

import ThemeToggle from "@/components/ThemeToggle";
import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

type HeaderControlProps = {
  mode: "remote" | "fpv";
  onToggle: () => void;
  lidarUrl?: string | null;
  lidarActive?: boolean;
  connected: boolean;
  errorExternal?: string | null;
  robotConnectedFlag?: boolean | null;
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
  battery?: number | null;
  fps?: number | null;
  system?: SystemTelemetry | null;
};

type LidarPose = {
  x: number;
  y: number;
  theta?: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
const robotId = "robot-a";
const CONTROL_PREFIX = "/control/api/robots";

async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] dark:bg-[rgba(255,255,255,0.04)] dark:border-white/10">
      <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--muted-2)] dark:text-white/45">
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-[var(--foreground)] dark:text-white">
        {value}
      </div>
    </div>
  );
}

export default function HeaderControl({
  mode,
  onToggle,
  lidarUrl,
  lidarActive = false,
  connected,
  errorExternal,
  robotConnectedFlag,
  commandLog,
}: HeaderControlProps) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const isFPV = mode === "fpv";
  const isDark = mounted && resolvedTheme === "dark";

  const [robotName, setRobotName] = useState("Robot A");
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorStatus, setErrorStatus] = useState<string | null>(null);
  const [locationText, setLocationText] = useState("-");
  const [collapsed, setCollapsed] = useState(false);
  const [viewMode, setViewMode] = useState<"debug" | "info">("debug");

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    let isMounted = true;
    async function fetchStatus() {
      try {
        const data = await api<any>(`${CONTROL_PREFIX}/${robotId}/status/`);
        if (!isMounted) return;
        setRobotName(data.name || "Robot A");
        setTelemetry(
          data.telemetry ?? {
            robot_connected: data.robot_connected ?? false,
            battery: data.battery,
            fps: data.fps,
            system: data.system ?? null,
          }
        );
        setErrorStatus(null);
      } catch (e: any) {
        if (!isMounted) return;
        setErrorStatus(e?.message || "Cannot fetch robot status");
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchStatus();
    const id = setInterval(fetchStatus, 2000);
    return () => {
      isMounted = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!lidarActive) {
      setLocationText("-");
      return;
    }

    let stop = false;

    async function fetchPose() {
      try {
        const raw = await api<any>(`${CONTROL_PREFIX}/${robotId}/slam/state/`);
        if (stop) return;
        const p: LidarPose = raw?.data ?? raw ?? {};
        if (typeof p?.x === "number" && typeof p?.y === "number") {
          const thetaText =
            typeof p.theta === "number" ? `, θ: ${p.theta.toFixed(2)} rad` : "";
          setLocationText(`x: ${p.x.toFixed(2)} m, y: ${p.y.toFixed(2)} m${thetaText}`);
        } else if (
          typeof (p as any)?.pose?.x === "number" &&
          typeof (p as any)?.pose?.y === "number"
        ) {
          const pose = (p as any).pose;
          const thetaText =
            typeof pose.theta === "number" ? `, θ: ${pose.theta.toFixed(2)} rad` : "";
          setLocationText(
            `x: ${pose.x.toFixed(2)} m, y: ${pose.y.toFixed(2)} m${thetaText}`
          );
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
  }, [lidarActive]);

  const sys = telemetry?.system ?? null;
  const cpuText = sys?.cpu_percent != null ? `${sys.cpu_percent}%` : loading ? "…" : "-";
  const ramText = sys?.ram ?? (loading ? "…" : "-");
  const diskText = sys?.disk ?? (loading ? "…" : "-");
  const ipText = sys?.ip ?? (loading ? "…" : "-");
  const batteryValue =
    telemetry?.battery != null ? `${telemetry.battery}%` : loading ? "…" : "-";
  const mergedError = errorExternal || errorStatus;

  const panelShell = isDark
    ? "border border-white/10 bg-[linear-gradient(180deg,rgba(22,6,38,0.98),rgba(12,5,32,0.96))] shadow-[0_12px_30px_rgba(0,0,0,0.22)]"
    : "border border-[var(--border)] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(247,242,255,0.96))] shadow-[0_12px_30px_rgba(124,77,255,0.06)]";

  return (
    <div className="mb-5">
      <header className="flex items-center justify-between gap-4">
        <h1 className={`gradient-title select-none transition-all duration-300 ${isFPV ? "opacity-100" : "opacity-90"}`}>
          {isFPV ? "FPV CONTROL MODE" : "REMOTE CONTROL MODE"}
        </h1>

        <div className="flex items-center gap-3">
          <Link
            href="/control"
            className="rounded-xl border border-pink-300/30 bg-gradient-to-r from-pink-500/20 to-fuchsia-500/20 px-3 py-1 text-sm text-pink-500 transition hover:scale-[1.03] active:scale-95"
          >
            Disconnect
          </Link>

          <ThemeToggle />

          <span className={`text-sm font-semibold transition-colors ${isFPV ? "text-[var(--muted)]" : "text-[#24163f] dark:text-white"}`}>
            Remote
          </span>
          <button
            onClick={onToggle}
            className={`cursor-pointer relative h-8 w-14 rounded-full border p-1 transition-all duration-300 ${
              isFPV
                ? "border-cyan-300 bg-gradient-to-r from-[#FD749B]/30 via-[#7C4DFF]/25 to-[#00C2FF]/25"
                : "border-violet-300 bg-gradient-to-r from-[#E8DDFF] to-[#D9F5FF]"
            }`}
            aria-label="Toggle FPV mode"
          >
            <div
              className={`h-6 w-6 rounded-full border border-white/60 bg-white shadow-[0_2px_10px_rgba(0,0,0,0.15)] transition-transform duration-300 ${
                isFPV ? "translate-x-6" : "translate-x-0"
              }`}
            />
          </button>
          <span className={`text-sm font-semibold transition-colors ${isFPV ? "text-[#24163f] dark:text-white" : "text-[var(--muted)]"}`}>
            FPV
          </span>
        </div>
      </header>

      <div className={`relative mt-4 rounded-2xl p-4 ${panelShell}`}>
        <div className="flex flex-wrap items-center gap-4 mb-3">
          <div className={`text-lg font-semibold ${isDark ? "text-white" : "text-[var(--foreground)]"}`}>
            🤖 {robotName}
          </div>

          <span className={`text-xs font-semibold ${connected ? "text-emerald-500" : "text-rose-500"}`}>
            {connected ? "Connected" : "Not connected"}
          </span>

          {sys?.time && <div className={`text-xs font-medium ${isDark ? "text-white/60" : "text-[var(--muted)]"}`}>Time: {sys.time}</div>}

          <div className="ml-auto flex items-center gap-2">
            <span className={`text-[11px] ${isDark ? "text-white/55" : "text-[var(--muted-2)]"}`}>View:</span>
            <button onClick={() => setViewMode("debug")}
              className={`cursor-pointer rounded-lg border px-2 py-1 text-[11px] transition-all ${
                viewMode === "debug"
                  ? "border-pink-300 bg-gradient-to-r from-[#FD749B] to-[#7C4DFF] text-white"
                  : isDark
                  ? "border-[rgba(255,255,255,0.12)] bg-[rgba(255,255,255,0.04)] text-white/80"
                  : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              Debug
            </button>
            <button onClick={() => setViewMode("info")}
              className={`cursor-pointer rounded-lg border px-2 py-1 text-[11px] transition-all ${
                viewMode === "info"
                  ? "border-sky-300 bg-gradient-to-r from-[#00C2FF] to-[#7C4DFF] text-white"
                  : isDark
                  ? "border-[rgba(255,255,255,0.12)] bg-[rgba(255,255,255,0.04)] text-white/80"
                  : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              Info
            </button>
          </div>
        </div>

        <div className={`overflow-hidden transition-all duration-300 ${collapsed ? "max-h-0 opacity-0" : "max-h-72 opacity-100"}`}>
          {viewMode === "debug" ? (
            <div className="flex gap-4 h-40">
              <div className={`w-56 space-y-1 text-xs leading-relaxed ${isDark ? "text-white/82" : "text-[var(--foreground)]/88"}`}>
                {mergedError && (
                  <div>
                    <span className="font-semibold text-rose-500">Status error: </span>
                    <span className="text-rose-400">{mergedError}</span>
                  </div>
                )}

                <div>
                  <span className="font-semibold text-[inherit]">Robot connected flag: </span>
                  <span className="font-semibold text-amber-400">
                    {String(robotConnectedFlag ?? telemetry?.robot_connected ?? false)}
                  </span>
                </div>

                {lidarUrl && (
                  <div className="truncate">
                    <span className="font-semibold text-[inherit]">Lidar URL: </span>
                    <span className="text-sky-400">{lidarUrl}</span>
                  </div>
                )}

                <div>
                  <span className="font-semibold text-[inherit]">Location: </span>
                  <span className={isDark ? "text-white/60" : "text-[var(--muted)]"}>{locationText}</span>
                </div>
              </div>

              <div className="flex min-w-0 flex-1 flex-col">
                <div className={`flex-1 overflow-y-auto rounded-xl border px-3 py-2 font-mono text-[11px] ${isDark ? "border-white/10 bg-[rgba(255,255,255,0.04)] text-white/88" : "border-[var(--border)] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(243,238,255,0.94))] text-[var(--foreground)] shadow-[inset_0_1px_0_rgba(255,255,255,0.65)]"}`}>
                  {commandLog && commandLog.length > 0 ? (
                    commandLog.map((line, idx) => (
                      <div key={idx} className="whitespace-pre-wrap">
                        {line}
                      </div>
                    ))
                  ) : (
                    <span className={isDark ? "text-white/45" : "text-[var(--muted)]"}>No command log yet.</span>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="grid h-40 grid-cols-2 content-start gap-4 text-sm md:grid-cols-3">
              <Metric label="Location" value={locationText} />
              <Metric label="CPU" value={cpuText} />
              <Metric label="RAM" value={ramText} />
              <Metric label="SDC" value={diskText} />
              <Metric label="IPA" value={ipText} />
              <Metric label="Battery" value={batteryValue} />
            </div>
          )}
        </div>

        <button onClick={() => setCollapsed((v) => !v)}
          className="cursor-pointer absolute -bottom-3 right-6 flex h-7 w-7 items-center justify-center rounded-full border border-[var(--border)] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(242,236,255,0.96))] text-[var(--foreground)] shadow-md transition-all hover:bg-[var(--surface)] dark:border-white/10 dark:bg-[rgba(255,255,255,0.06)] dark:text-white"
          aria-label="Toggle details"
        >
          <ChevronDown
            size={16}
            className={`transition-transform duration-300 ${collapsed ? "" : "rotate-180"}`}
          />
        </button>
      </div>
    </div>
  );
}
