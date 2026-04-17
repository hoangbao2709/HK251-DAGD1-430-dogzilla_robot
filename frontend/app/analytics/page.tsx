"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
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

type NetworkPoint = {
  time: string;
  uplink: number;
  downlink: number;
  latency: number;
  packetLoss: number;
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

type EventsResponse = {
  ok?: boolean;
  count?: number;
  limit?: number;
  offset?: number;
  items?: Array<{
    id: string;
    timestamp: string;
    robot: string;
    event: string;
    severity: "Info" | "Warning" | "Critical" | "High" | "Medium" | "Low";
    duration: string | null;
    status: "Success" | "Failed" | "Active" | "Resolved";
    action?: string;
    detail?: string | null;
    payload?: Record<string, unknown>;
  }>;
};

type Snapshot = {
  server: JsonRecord | null;
  health: JsonRecord | null;
  status: JsonRecord | null;
  controlStatus: JsonRecord | null;
  network: JsonRecord | null;
};

type NetworkSummary = {
  uplink: number;
  downlink: number;
  latency: number;
  jitter: number;
  packetLoss: number;
  signalQuality: number;
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

function normalizeEventItem(item: NonNullable<EventsResponse["items"]>[number]): EventItem {
  const severityMap: Record<string, EventItem["severity"]> = {
    Info: "Low",
    Low: "Low",
    Medium: "Medium",
    Warning: "Warning",
    High: "High",
    Critical: "Critical",
  };

  const statusMap: Record<string, EventItem["status"]> = {
    Active: "Active",
    Failed: "Resolved",
    Success: "Resolved",
    Resolved: "Resolved",
  };

  return {
    id: item.id,
    timestamp: item.timestamp,
    robot: item.robot,
    event: item.event || item.action || "Unknown event",
    severity: severityMap[item.severity] ?? "Low",
    duration: item.duration ?? "-",
    status: statusMap[item.status] ?? "Resolved",
  };
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

function getNetworkNumber(source: JsonRecord | null, keys: string[], fallback = 0) {
  if (!source) return fallback;

  for (const key of keys) {
    const value = source[key];
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }

  const nested = source.data || source.result || source.metrics;
  if (nested && nested !== source) {
    return getNetworkNumber(nested, keys, fallback);
  }

  return fallback;
}

function getNetworkSummary(source: JsonRecord | null): NetworkSummary {
  return {
    uplink: Math.max(
      0,
      getNetworkNumber(source, [
        "uplink_kbps",
        "up_kbps",
        "tx_kbps",
        "upload_kbps",
        "uplink",
        "tx",
      ])
    ),
    downlink: Math.max(
      0,
      getNetworkNumber(source, [
        "downlink_kbps",
        "down_kbps",
        "rx_kbps",
        "download_kbps",
        "downlink",
        "rx",
      ])
    ),
    latency: Math.max(
      0,
      getNetworkNumber(source, ["latency_ms", "ping_ms", "rtt_ms", "latency"])
    ),
    jitter: Math.max(
      0,
      getNetworkNumber(source, ["jitter_ms", "jitter"])
    ),
    packetLoss: Math.max(
      0,
      getNetworkNumber(source, ["packet_loss_pct", "packet_loss", "loss_pct"])
    ),
    signalQuality: clamp(
      getNetworkNumber(source, ["signal_quality", "quality", "signal"]) || 0,
      0,
      100
    ),
  };
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
    <svg width="96" height="96" viewBox="0 0 96 96" className="text-[var(--foreground)]">
      <circle cx="48" cy="48" r={r} fill="none" stroke="currentColor" strokeOpacity="0.12" strokeWidth="8" />
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
      <text x="48" y="53" textAnchor="middle" fill="currentColor" fontSize="15" fontWeight="700">
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
      <div className="flex-1 rounded-full h-1.5 bg-[rgba(23,19,39,0.10)] dark:bg-white/10">
        <div
          className="h-1.5 rounded-full bg-gradient-to-r from-blue-500 to-purple-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[var(--foreground)]/80 w-6 text-right">{count}</span>
    </div>
  );
}

function NetworkChart({ data }: { data: NetworkPoint[] }) {
  const safeData =
    data.length > 1
      ? data
      : [
          { time: "--", uplink: 0, downlink: 0, latency: 0, packetLoss: 0 },
          { time: "--", uplink: 0, downlink: 0, latency: 0, packetLoss: 0 },
        ];

  const W = 500;
  const H = 100;
  const pad = { top: 8, right: 8, bottom: 8, left: 8 };
  const iW = W - pad.left - pad.right;
  const iH = H - pad.top - pad.bottom;

  const maxThroughput = Math.max(100, ...safeData.map((d) => Math.max(d.uplink, d.downlink)));
  const maxLatency = Math.max(20, ...safeData.map((d) => d.latency));

  const toX = (i: number) => pad.left + (i / (safeData.length - 1)) * iW;
  const toY = (v: number, max: number) => pad.top + (1 - v / max) * iH;

  const uplinkPath = safeData
    .map((d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toY(d.uplink, maxThroughput)}`)
    .join(" ");
  const downlinkPath = safeData
    .map((d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toY(d.downlink, maxThroughput)}`)
    .join(" ");
  const latencyPath = safeData
    .map((d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toY(d.latency, maxLatency)}`)
    .join(" ");

  return (
    <svg viewBox="0 0 500 100" className="w-full h-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="uplinkGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.9" />
        </linearGradient>
        <linearGradient id="downlinkGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#22c55e" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#10b981" stopOpacity="0.9" />
        </linearGradient>
      </defs>

      <path d={uplinkPath} fill="none" stroke="url(#uplinkGrad)" strokeWidth="1.8" />
      <path d={downlinkPath} fill="none" stroke="url(#downlinkGrad)" strokeWidth="1.8" />
      <path d={latencyPath} fill="none" stroke="#f97316" strokeWidth="1.5" strokeDasharray="4 2" />
    </svg>
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
    network: null,
  });

  const [batteryHistory, setBatteryHistory] = useState<BatteryPoint[]>([]);
  const [networkHistory, setNetworkHistory] = useState<NetworkPoint[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
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

      let network = null;
      try {
        network = await RobotAPI.networkMetrics();
      } catch {
        network = null;
      }

      setSnapshot({
        server,
        health,
        status,
        controlStatus,
        network,
      });

      try {
        const response = await RobotAPI.events(20, 0);
        const items = (response as EventsResponse)?.items ?? [];
        setEvents(items.map(normalizeEventItem));
      } catch {
        setEvents([]);
      }

      const battery = getBattery(status);
      const power = getPower(status);
      const networkSummary = getNetworkSummary(network);

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

      setNetworkHistory((prev) =>
        [
          ...prev,
          {
            time: formatClock(),
            uplink: networkSummary.uplink,
            downlink: networkSummary.downlink,
            latency: networkSummary.latency,
            packetLoss: networkSummary.packetLoss,
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
  const networkSummary = getNetworkSummary(snapshot.network);
  const hasNetworkData =
    networkSummary.uplink > 0 ||
    networkSummary.downlink > 0 ||
    networkSummary.latency > 0 ||
    networkSummary.packetLoss > 0 ||
    networkSummary.signalQuality > 0;

  const activeErrors = events.filter((e) => e.status === "Active").length;
  const recentAlerts = useMemo(() => events.slice(0, 4), [events]);

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
              subColor="text-[var(--muted)]"
            />

            <StatCard
              icon={<HeartPulse size={16} className={healthOk ? "text-green-400" : "text-red-400"} />}
              iconBg={healthOk ? "bg-green-500/20" : "bg-red-500/20"}
              label="Health"
              main={<span className={healthOk ? "text-green-400" : "text-red-400"}>{healthOk ? "Healthy" : "Error"}</span>}
              sub="RobotAPI.health()"
              subColor="text-[var(--muted)]"
            />

            <StatCard
              icon={<Battery size={16} className="text-green-400" />}
              iconBg="bg-green-500/20"
              label="Battery"
              main={<span className="text-3xl text-green-400">{battery}%</span>}
              sub={`${remainingHours.toFixed(1)} hr remaining`}
              subColor="text-[var(--muted)]"
              extra={
                <div className="flex gap-1 mt-1">
                  {[20, 40, 60, 80, 100].map((v, i) => (
                    <div
                      key={i}
                      className={`h-1.5 flex-1 rounded-full ${battery >= v ? "bg-green-400" : "bg-[rgba(23,19,39,0.12)] dark:bg-white/20"}`}
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
                  <span className="text-base text-[var(--muted)]">w</span>
                </>
              }
              sub="Estimated from live status"
              subColor="text-[var(--muted)]"
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

          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-start justify-between mb-3 gap-3">
              <div>
                <p className="text-[var(--foreground)] font-semibold text-sm">
                  Link Throughput &amp; Latency
                </p>
                <p className="text-[var(--muted)] text-xs mt-0.5">
                  Live network telemetry between robot and backend
                </p>
              </div>
              <span className="text-[11px] text-cyan-400 border border-cyan-400/30 bg-cyan-500/10 rounded px-2 py-0.5">
                {hasNetworkData ? "Network Live" : "No data"}
              </span>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
              <StatCard
                icon={<Server size={16} className="text-cyan-400" />}
                iconBg="bg-cyan-500/20"
                label="Uplink"
                main={
                  <span className="text-2xl text-cyan-400">
                    {networkSummary.uplink > 0 ? `${networkSummary.uplink.toFixed(0)}` : "No data"}
                  </span>
                }
                sub="kbps to backend"
                subColor="text-[var(--muted)]"
              />
              <StatCard
                icon={<Server size={16} className="text-emerald-400" />}
                iconBg="bg-emerald-500/20"
                label="Downlink"
                main={
                  <span className="text-2xl text-emerald-400">
                    {networkSummary.downlink > 0 ? `${networkSummary.downlink.toFixed(0)}` : "No data"}
                  </span>
                }
                sub="kbps from backend"
                subColor="text-[var(--muted)]"
              />
              <StatCard
                icon={<Navigation size={16} className="text-orange-400" />}
                iconBg="bg-orange-500/20"
                label="Latency"
                main={
                  <span className="text-2xl text-orange-400">
                    {networkSummary.latency > 0 ? `${networkSummary.latency.toFixed(0)} ms` : "No data"}
                  </span>
                }
                sub="Round-trip time"
                subColor="text-[var(--muted)]"
              />
              <StatCard
                icon={<HeartPulse size={16} className="text-violet-400" />}
                iconBg="bg-violet-500/20"
                label="Packet loss"
                main={
                  <span className="text-2xl text-violet-400">
                    {networkSummary.packetLoss > 0 ? `${networkSummary.packetLoss.toFixed(2)}%` : "No data"}
                  </span>
                }
                sub={`Quality ${networkSummary.signalQuality > 0 ? `${networkSummary.signalQuality.toFixed(0)}%` : "N/A"}`}
                subColor="text-[var(--muted)]"
              />
            </div>

            <div className="h-28 w-full">
              <NetworkChart data={networkHistory} />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2 px-1">
              {(networkHistory.length
                ? networkHistory
                : [{ time: "--", uplink: 0, downlink: 0, latency: 0, packetLoss: 0 }]
              ).map((p, i, arr) => (
                <span key={`${p.time}-${i}`} className="text-[var(--muted-2)] text-[10px]">
                  {i === 0 || i === arr.length - 1 || i % Math.max(1, Math.ceil(arr.length / 4)) === 0
                    ? p.time
                    : ""}
                </span>
              ))}
            </div>
          </div>

        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <p className="text-[var(--foreground)] font-semibold text-sm">System Overview</p>
                <p className="text-[var(--muted)] text-xs mt-0.5">
                  Live robot/backend health snapshot
                </p>
              </div>
              <span className="text-[11px] text-violet-400 border border-violet-400/30 bg-violet-500/10 rounded px-2 py-0.5">
                {activeErrors > 0 ? `${activeErrors} active alerts` : "All clear"}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <div className="text-[10px] uppercase tracking-widest text-[var(--muted)]">Server</div>
                <div className={`mt-1 text-lg font-bold ${serverOnline ? "text-green-400" : "text-red-400"}`}>
                  {serverOnline ? "Online" : "Offline"}
                </div>
                <div className="text-[var(--muted)] text-xs mt-1">RobotAPI.server()</div>
              </div>

              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <div className="text-[10px] uppercase tracking-widest text-[var(--muted)]">Health</div>
                <div className={`mt-1 text-lg font-bold ${healthOk ? "text-green-400" : "text-red-400"}`}>
                  {healthOk ? "Healthy" : "Error"}
                </div>
                <div className="text-[var(--muted)] text-xs mt-1">RobotAPI.health()</div>
              </div>

              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <div className="text-[10px] uppercase tracking-widest text-[var(--muted)]">Lidar</div>
                <div className={`mt-1 text-lg font-bold ${lidarRunning ? "text-cyan-400" : "text-slate-400"}`}>
                  {lidarRunning ? "Running" : "Stopped"}
                </div>
                <div className="text-[var(--muted)] text-xs mt-1">Control status</div>
              </div>

              <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                <div className="text-[10px] uppercase tracking-widest text-[var(--muted)]">Refresh</div>
                <div className="mt-1 text-lg font-bold text-[var(--foreground)]">{lastRefresh}</div>
                <div className="text-[var(--muted)] text-xs mt-1">Latest snapshot</div>
              </div>
            </div>
          </div>

          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-[var(--muted)] text-xs font-medium uppercase tracking-widest">
                  Recent Alerts
                </span>
              </div>
              <span className="text-2xl font-bold text-[var(--foreground)]">{activeErrors}</span>
            </div>

            <div className="space-y-2">
              {recentAlerts.length > 0 ? (
                recentAlerts.map((e) => (
                  <div
                    key={e.id}
                    className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-[var(--foreground)]">{e.event}</div>
                      <div className="text-xs text-[var(--muted)]">{e.timestamp}</div>
                    </div>
                    <span
                      className={`inline-block px-2.5 py-0.5 rounded text-xs font-semibold ${severityBadge(
                        e.severity
                      )}`}
                    >
                      {e.severity}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-[var(--muted)] text-sm">Chưa có event nào.</p>
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
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Robot
                </th>
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Event Type
                </th>
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Severity
                </th>
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">
                  Duration
                </th>
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">
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
