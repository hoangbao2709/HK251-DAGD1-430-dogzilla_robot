"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Battery,
  HeartPulse,
  Loader2,
  Navigation,
  RefreshCw,
  Server,
  Zap,
} from "lucide-react";
import { RobotAPI, robotId } from "@/app/lib/robotApi";

// ───────────────────────────────────────────────────────────────────────────────
// Types
// ───────────────────────────────────────────────────────────────────────────────

type JsonRecord = Record<string, any>;

type BatteryPoint = {
  time: string;
  battery: number;
  power: number;
};

type EventItem = {
  id: string;
  timestamp: string;
  robot: string;
  event: string;
  severity: "Critical" | "Warning" | "High" | "Medium" | "Low";
  duration: string;
  status: "Active" | "Resolved";
};

type Snapshot = {
  server: JsonRecord | null;
  health: JsonRecord | null;
  status: JsonRecord | null;
  controlStatus: JsonRecord | null;
};

// ───────────────────────────────────────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────────────────────────────────────

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function formatClock(date = new Date()) {
  return date.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function severityBadge(severity: string) {
  const map: Record<string, string> = {
    Critical: "bg-red-500/20 text-red-400 border border-red-500/40",
    Warning: "bg-orange-500/20 text-orange-400 border border-orange-500/40",
    High: "bg-amber-500/20 text-amber-400 border border-amber-500/40",
    Medium: "bg-blue-500/20 text-blue-400 border border-blue-500/40",
    Low: "bg-slate-500/20 text-slate-400 border border-slate-500/40",
  };
  return map[severity] ?? map.Low;
}

function statusBadge(status: string) {
  return status === "Active"
    ? "bg-red-500/20 text-red-400 border border-red-500/40"
    : "bg-green-500/20 text-green-400 border border-green-500/40";
}

function getBattery(status: JsonRecord | null) {
  if (!status) return 0;

  const candidates = [
    status.battery,
    status.battery_level,
    status.data?.battery,
    status.data?.battery_level,
    status.result?.battery,
    status.result?.battery_level,
  ];

  for (const item of candidates) {
    const n = Number(item);
    if (Number.isFinite(n)) return clamp(n, 0, 100);
  }

  return 0;
}

function getPower(status: JsonRecord | null) {
  if (!status) return 0;

  const candidates = [
    status.power,
    status.power_draw,
    status.watts,
    status.data?.power,
    status.data?.power_draw,
    status.result?.power,
    status.result?.power_draw,
  ];

  for (const item of candidates) {
    const n = Number(item);
    if (Number.isFinite(n)) return Math.max(0, n);
  }

  const battery = getBattery(status);
  return Math.max(6, Math.round((100 - battery) / 5 + 8));
}

function getRemainingHours(status: JsonRecord | null, battery: number) {
  const candidates = [
    status?.remaining_hours,
    status?.remaining_time_hours,
    status?.data?.remaining_hours,
    status?.result?.remaining_hours,
  ];

  for (const item of candidates) {
    const n = Number(item);
    if (Number.isFinite(n)) return n;
  }

  return Number((battery / 13).toFixed(1));
}

function getRobotName(snapshot: Snapshot) {
  return (
    snapshot.status?.name ||
    snapshot.status?.robot ||
    snapshot.server?.name ||
    snapshot.server?.robot ||
    robotId
  );
}

function getHealthOk(health: JsonRecord | null) {
  if (!health) return false;
  return Boolean(health.ok ?? health.success ?? health.status ?? true);
}

function getLidarRunning(snapshot: Snapshot) {
  return Boolean(
    snapshot.controlStatus?.lidar_running ??
      snapshot.controlStatus?.lidar?.running ??
      snapshot.status?.lidar_running ??
      snapshot.status?.lidar?.running ??
      false
  );
}

function buildErrorBreakdown(events: EventItem[]) {
  const counters: Record<string, number> = {
    "HTTP Failed": 0,
    "Lidar Error": 0,
    "Control Busy": 0,
    "Motion Error": 0,
    "Unknown Error": 0,
  };

  events.forEach((e) => {
    const text = e.event.toLowerCase();
    if (text.includes("lidar")) counters["Lidar Error"] += 1;
    else if (text.includes("busy")) counters["Control Busy"] += 1;
    else if (
      text.includes("move") ||
      text.includes("turn") ||
      text.includes("posture") ||
      text.includes("behavior")
    ) counters["Motion Error"] += 1;
    else if (text.includes("http") || text.includes("failed")) counters["HTTP Failed"] += 1;
    else counters["Unknown Error"] += 1;
  });

  return Object.entries(counters)
    .map(([label, count]) => ({ label, count, max: Math.max(4, count || 1) }))
    .filter((x) => x.count > 0);
}

// ───────────────────────────────────────────────────────────────────────────────
// UI Components
// ───────────────────────────────────────────────────────────────────────────────

function StatCard({
  icon,
  iconBg,
  label,
  main,
  sub,
  subColor = "text-green-400",
  extra,
}: {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  main: React.ReactNode;
  sub?: string;
  subColor?: string;
  extra?: React.ReactNode;
}) {
  return (
    <div className="bg-[var(--surface)] rounded-xl p-4 flex flex-col gap-1 border border-[var(--border)]">
      <div className="flex items-center gap-2 mb-1">
        <div className={`p-1.5 rounded-lg ${iconBg}`}>{icon}</div>
        <span className="text-[var(--muted)] text-xs font-medium">{label}</span>
      </div>
      <div className="text-2xl font-bold text-[var(--foreground)]">{main}</div>
      {sub && <div className={`text-xs ${subColor}`}>{sub}</div>}
      {extra}
    </div>
  );
}

function BatteryChart({ data }: { data: BatteryPoint[] }) {
  const safeData =
    data.length > 1
      ? data
      : [
          { time: "00:00", battery: 0, power: 0 },
          { time: "00:01", battery: 0, power: 0 },
        ];

  const W = 500;
  const H = 100;
  const pad = { top: 8, right: 8, bottom: 8, left: 8 };
  const iW = W - pad.left - pad.right;
  const iH = H - pad.top - pad.bottom;

  const maxPower = Math.max(20, ...safeData.map((d) => d.power), 20);

  const toX = (i: number) => pad.left + (i / (safeData.length - 1)) * iW;
  const toYBat = (v: number) => pad.top + (1 - v / 100) * iH;
  const toYPow = (v: number) => pad.top + (1 - v / maxPower) * iH;

  const batteryPath = safeData
    .map((d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toYBat(d.battery)}`)
    .join(" ");

  const powerPath = safeData
    .map((d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toYPow(d.power)}`)
    .join(" ");

  const batteryFill =
    batteryPath +
    ` L ${toX(safeData.length - 1)} ${H - pad.bottom} L ${pad.left} ${H - pad.bottom} Z`;

  return (
    <svg viewBox={`0 0 500 100`} className="w-full h-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="batGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#10b981" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={batteryFill} fill="url(#batGrad)" />
      <path d={batteryPath} fill="none" stroke="#10b981" strokeWidth="1.5" />
      <path d={powerPath} fill="none" stroke="#f97316" strokeWidth="1.5" strokeDasharray="4 2" />
    </svg>
  );
}

function CircleProgress({ value }: { value: number }) {
  const r = 38;
  const circ = 2 * Math.PI * r;
  const dash = (value / 100) * circ;

  return (
    <svg width="96" height="96" viewBox="0 0 96 96">
      <circle cx="48" cy="48" r={r} fill="none" stroke="#ffffff10" strokeWidth="8" />
      <circle
        cx="48"
        cy="48"
        r={r}
        fill="none"
        stroke="#10b981"
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeDashoffset={circ / 4}
      />
      <text x="48" y="53" textAnchor="middle" fill="white" fontSize="15" fontWeight="700">
        {value}%
      </text>
    </svg>
  );
}

function NavErrorBar({ label, count, max }: { label: string; count: number; max: number }) {
  const pct = (count / max) * 100;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-[var(--muted)] w-32 shrink-0 truncate">{label}</span>
      <div className="flex-1 bg-black/10 dark:bg-white/10 rounded-full h-1.5">
        <div
          className="h-1.5 rounded-full bg-gradient-to-r from-blue-500 to-purple-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[var(--foreground)]/80 w-6 text-right">{count}</span>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────────────────
// Main Page
// ───────────────────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [snapshot, setSnapshot] = useState<Snapshot>({
    server: null,
    health: null,
    status: null,
    controlStatus: null,
  });

  const [batteryHistory, setBatteryHistory] = useState<BatteryPoint[]>([]);
  const [events] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState("");
  const [lastRefresh, setLastRefresh] = useState("-");

  const refreshAll = useCallback(async () => {
    try {
      setErrorText("");

      const [server, health, status, controlStatus] = await Promise.all([
        RobotAPI.server(),
        RobotAPI.health(),
        RobotAPI.status(),
        RobotAPI.controlStatus(),
      ]);

      setSnapshot({
        server,
        health,
        status,
        controlStatus,
      });

      const battery = getBattery(status);
      const power = getPower(status);

      setBatteryHistory((prev) =>
        [
          ...prev,
          {
            time: formatClock(),
            battery,
            power,
          },
        ].slice(-12)
      );

      setLastRefresh(formatClock());
    } catch (err: any) {
      const msg = err?.message || "Failed to refresh analytics";
      setErrorText(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshAll();
    const timer = setInterval(refreshAll, 5000);
    return () => clearInterval(timer);
  }, [refreshAll]);

  const battery = getBattery(snapshot.status);
  const power = getPower(snapshot.status);
  const remainingHours = getRemainingHours(snapshot.status, battery);
  const robotName = getRobotName(snapshot);
  const healthOk = getHealthOk(snapshot.health);
  const serverOnline = Boolean(snapshot.server);
  const lidarRunning = getLidarRunning(snapshot);

  const activeErrors = events.filter((e) => e.status === "Active").length;
  const navSuccessRate = events.length
    ? Math.max(
        0,
        Math.round(
          ((events.length -
            events.filter((e) => e.severity === "Critical" || e.severity === "High").length) /
            events.length) *
            100
        )
      )
    : 100;

  const navErrors = useMemo(() => buildErrorBreakdown(events), [events]);

  return (
    <section className="min-h-screen bg-[var(--background)] text-[var(--foreground)] p-5 flex flex-col gap-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="gradient-title text-2xl">Analytics</h1>
          <p className="text-[var(--muted)] text-sm mt-1">
            Robot: <span className="text-[var(--foreground)]">{robotName}</span> · ID:{" "}
            <span className="text-blue-300">{robotId}</span>
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs px-3 py-1 rounded-full border border-[var(--border)] bg-[var(--surface)] text-[var(--foreground)]/70">
            Last refresh: {lastRefresh}
          </span>
          <button
            onClick={refreshAll}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm hover:bg-[var(--surface-2)] disabled:opacity-50"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            Refresh
          </button>
        </div>
      </div>

      {errorText ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {errorText}
        </div>
      ) : null}

      <div className="grid grid-cols-1 xl:grid-cols-[1.1fr_0.9fr] gap-5">
        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <StatCard
              icon={<Server size={16} className={serverOnline ? "text-green-400" : "text-red-400"} />}
              iconBg={serverOnline ? "bg-green-500/20" : "bg-red-500/20"}
              label="Server"
              main={<span className={serverOnline ? "text-green-400" : "text-red-400"}>{serverOnline ? "Online" : "Offline"}</span>}
              sub="RobotAPI.server()"
              subColor="text-white/50"
            />

            <StatCard
              icon={<HeartPulse size={16} className={healthOk ? "text-green-400" : "text-red-400"} />}
              iconBg={healthOk ? "bg-green-500/20" : "bg-red-500/20"}
              label="Health"
              main={<span className={healthOk ? "text-green-400" : "text-red-400"}>{healthOk ? "Healthy" : "Error"}</span>}
              sub="RobotAPI.health()"
              subColor="text-white/50"
            />

            <StatCard
              icon={<Battery size={16} className="text-green-400" />}
              iconBg="bg-green-500/20"
              label="Battery"
              main={<span className="text-3xl text-green-400">{battery}%</span>}
              sub={`${remainingHours.toFixed(1)} hr remaining`}
              subColor="text-white/50"
              extra={
                <div className="flex gap-1 mt-1">
                  {[20, 40, 60, 80, 100].map((v, i) => (
                    <div
                      key={i}
                      className={`h-1.5 flex-1 rounded-full ${battery >= v ? "bg-green-400" : "bg-white/20"}`}
                    />
                  ))}
                </div>
              }
            />

            <StatCard
              icon={<Zap size={16} className="text-yellow-400" />}
              iconBg="bg-yellow-500/20"
              label="Power Draw"
              main={
                <>
                  <span className="text-3xl text-yellow-400">{power}</span>
                  <span className="text-base text-white/60">w</span>
                </>
              }
              sub="Estimated from live status"
              subColor="text-white/50"
            />
          </div>

          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-start justify-between mb-3 gap-3">
              <div>
                <p className="text-[var(--foreground)] font-semibold text-sm">Battery &amp; Energy Consumption</p>
                <p className="text-[var(--muted)] text-xs mt-0.5">Live history from RobotAPI.status()</p>
              </div>
              <span className="text-[11px] text-blue-400 border border-blue-400/30 bg-blue-500/10 rounded px-2 py-0.5">
                {lidarRunning ? "LIDAR Running" : "LIDAR Stopped"}
              </span>
            </div>

            <div className="h-28 w-full">
              <BatteryChart data={batteryHistory} />
            </div>

            <div className="flex justify-between mt-1 px-1">
              {(batteryHistory.length ? batteryHistory : [{ time: "--", battery: 0, power: 0 }]).map(
                (p, i, arr) => (
                  <span key={`${p.time}-${i}`} className="text-[var(--muted-2)] text-[10px]">
                    {i === 0 || i === arr.length - 1 || i % Math.max(1, Math.ceil(arr.length / 4)) === 0
                      ? p.time
                      : ""}
                  </span>
                )
              )}
            </div>
          </div>

        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-center gap-2 mb-3">
              <Navigation size={14} className="text-blue-400" />
              <span className="text-[var(--muted)] text-xs font-medium uppercase tracking-widest">
                Navigation Success Rate
              </span>
              <span className="ml-auto text-2xl font-bold text-[var(--foreground)]">{navSuccessRate}%</span>
            </div>

            <div className="flex items-center gap-4">
              <CircleProgress value={navSuccessRate} />
              <div className="flex-1">
                <p className="text-[var(--muted)] text-xs">
                  Calculated from recent action results on this page
                </p>
              </div>
            </div>
          </div>

          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <AlertTriangle size={14} className="text-orange-400" />
                <span className="text-[var(--muted)] text-xs font-medium uppercase tracking-widest">
                  Navigation Errors
                </span>
              </div>
              <span className="text-2xl font-bold text-[var(--foreground)]">{activeErrors}</span>
            </div>

            <div className="space-y-2">
              {navErrors.length > 0 ? (
                navErrors.map((e) => <NavErrorBar key={e.label} {...e} />)
              ) : (
                <p className="text-[var(--muted)] text-sm">Chưa có lỗi nào được ghi nhận.</p>
              )}
            </div>
          </div>

        </div>
      </div>

      <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] overflow-hidden">
        <div className="p-5 pb-3">
          <h2 className="text-[var(--foreground)] text-lg font-bold">Recent Critical Events</h2>
          <p className="text-[var(--muted)] text-xs mt-0.5">Logs generated from RobotAPI actions</p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-t border-[var(--border)] bg-[var(--surface-2)]">
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Timestamp
                </th>
                <th className="text-left text-white/50 font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Robot
                </th>
                <th className="text-left text-white/50 font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Event Type
                </th>
                <th className="text-left text-white/50 font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Severity
                </th>
                <th className="text-left text-white/50 font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Duration
                </th>
                <th className="text-left text-white/50 font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Status
                </th>
              </tr>
            </thead>

            <tbody>
              {events.length > 0 ? (
                events.map((row) => (
                  <tr
                    key={row.id}
                    className="border-t border-[var(--border)] hover:bg-[var(--surface-2)] transition-colors duration-150"
                  >
                    <td className="px-5 py-3.5 text-[var(--muted)] font-mono text-xs">{row.timestamp}</td>
                    <td className="px-5 py-3.5 text-[var(--foreground)]/80">{row.robot}</td>
                    <td className="px-5 py-3.5 text-[var(--foreground)]/80">{row.event}</td>
                    <td className="px-5 py-3.5">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded text-xs font-semibold ${severityBadge(
                          row.severity
                        )}`}
                      >
                        {row.severity}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-[var(--muted)]">{row.duration}</td>
                    <td className="px-5 py-3.5">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded text-xs font-semibold ${statusBadge(
                          row.status
                        )}`}
                      >
                        {row.status}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr className="border-t border-white/5">
                  <td colSpan={6} className="px-5 py-6 text-center text-[var(--muted)]">
                    Chưa có event nào.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
