"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Battery,
  Cpu,
  Gauge,
  HeartPulse,
  Loader2,
  Navigation,
  RefreshCw,
  Server,
  ShieldCheck,
  Waves,
} from "lucide-react";
import { RobotAPI, robotId } from "@/app/lib/robotApi";

type JsonRecord = Record<string, any>;

type StatusPoint = {
  time: string;
  battery: number;
  fps: number;
};

type NetworkPoint = {
  time: string;
  uplink: number;
  downlink: number;
  latency: number;
  packetLoss: number;
};

type NetworkSummary = {
  uplink: number;
  downlink: number;
  latency: number;
  jitter: number;
  packetLoss: number;
  signalQuality: number;
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
  items?: Array<{
    id: string;
    timestamp: string;
    robot: string;
    event: string;
    severity: "Info" | "Warning" | "Critical" | "High" | "Medium" | "Low";
    duration: string | null;
    status: "Success" | "Failed" | "Active" | "Resolved";
    action?: string;
  }>;
};

type RobotStatus = {
  battery?: number;
  fps?: number;
  fw?: string | null;
  gait_type?: string;
  perform_enabled?: boolean;
  pitch_current?: number;
  pitch_range?: [number, number];
  robot_connected?: boolean;
  roll_current?: number;
  speed_mode?: string;
  stabilizing_enabled?: boolean;
  step_default?: number;
  system?: {
    cpu_percent?: number;
    disk?: string;
    ip?: string;
    ram?: string;
    time?: string;
  } | null;
  turn_speed_range?: [number, number];
  yaw_current?: number;
  z_current?: number;
  z_range?: [number, number];
  telemetry?: Partial<RobotStatus>;
};

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

function getNumber(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeRobotStatus(raw: any): RobotStatus {
  const telemetry = raw?.telemetry && typeof raw.telemetry === "object" ? raw.telemetry : {};
  const system =
    telemetry?.system && typeof telemetry.system === "object"
      ? telemetry.system
      : raw?.system && typeof raw.system === "object"
        ? raw.system
        : null;

  return {
    ...raw,
    ...telemetry,
    system,
  };
}

function getNetworkNumber(source: JsonRecord | null, keys: string[], fallback = 0) {
  if (!source) return fallback;

  for (const key of keys) {
    const value = source[key];
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
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
      getNetworkNumber(source, ["uplink_kbps", "up_kbps", "tx_kbps", "upload_kbps", "uplink", "tx"])
    ),
    downlink: Math.max(
      0,
      getNetworkNumber(source, ["downlink_kbps", "down_kbps", "rx_kbps", "download_kbps", "downlink", "rx"])
    ),
    latency: Math.max(0, getNetworkNumber(source, ["latency_ms", "ping_ms", "rtt_ms", "latency"])),
    jitter: Math.max(0, getNetworkNumber(source, ["jitter_ms", "jitter"])),
    packetLoss: Math.max(0, getNetworkNumber(source, ["packet_loss_pct", "packet_loss", "loss_pct"])),
    signalQuality: clamp(getNetworkNumber(source, ["signal_quality", "quality", "signal"]), 0, 100),
  };
}

function getPercentFromRange(value: number, range?: [number, number]) {
  if (!range || range.length !== 2) return 0;
  const [min, max] = range;
  if (max <= min) return 0;
  return clamp(((value - min) / (max - min)) * 100, 0, 100);
}

function formatBool(value?: boolean) {
  return value ? "On" : "Off";
}

function formatRange(range?: [number, number], unit = "") {
  if (!range || range.length !== 2) return "N/A";
  return `${range[0]}${unit} to ${range[1]}${unit}`;
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

function StatCard({
  icon,
  iconBg,
  label,
  main,
  sub,
  subColor = "text-[var(--muted)]",
}: {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  main: React.ReactNode;
  sub?: React.ReactNode;
  subColor?: string;
}) {
  return (
    <div className="bg-[var(--surface)] rounded-xl p-4 flex flex-col gap-1 border border-[var(--border)]">
      <div className="flex items-center gap-2 mb-1">
        <div className={`p-1.5 rounded-lg ${iconBg}`}>{icon}</div>
        <span className="text-[var(--muted)] text-xs font-medium">{label}</span>
      </div>
      <div className="text-2xl font-bold text-[var(--foreground)]">{main}</div>
      {sub ? <div className={`text-xs ${subColor}`}>{sub}</div> : null}
    </div>
  );
}

function MetricRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-widest text-[var(--muted)]">{label}</div>
      <div className="mt-1 text-sm font-semibold text-[var(--foreground)] break-all">{value}</div>
      {hint ? <div className="mt-1 text-xs text-[var(--muted)]">{hint}</div> : null}
    </div>
  );
}

function PoseBar({
  label,
  value,
  range,
  unit = "",
  colorClass,
}: {
  label: string;
  value: number;
  range?: [number, number];
  unit?: string;
  colorClass: string;
}) {
  const percent = getPercentFromRange(value, range);

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-[var(--foreground)]">{label}</span>
        <span className="text-sm text-[var(--foreground)]">
          {value}
          {unit}
        </span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
        <div className={`h-full rounded-full ${colorClass}`} style={{ width: `${percent}%` }} />
      </div>
      <div className="mt-2 text-xs text-[var(--muted)]">Range: {formatRange(range, unit)}</div>
    </div>
  );
}

function StatusHistoryChart({ data }: { data: StatusPoint[] }) {
  const safeData =
    data.length > 1
      ? data
      : [
          { time: "00:00", battery: 0, fps: 0 },
          { time: "00:01", battery: 0, fps: 0 },
        ];

  const width = 500;
  const height = 110;
  const pad = { top: 8, right: 8, bottom: 8, left: 8 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const maxFps = Math.max(30, ...safeData.map((item) => item.fps));

  const toX = (index: number) => pad.left + (index / (safeData.length - 1)) * innerWidth;
  const toYBattery = (value: number) => pad.top + (1 - value / 100) * innerHeight;
  const toYFps = (value: number) => pad.top + (1 - value / maxFps) * innerHeight;

  const batteryPath = safeData
    .map((item, index) => `${index === 0 ? "M" : "L"} ${toX(index)} ${toYBattery(item.battery)}`)
    .join(" ");
  const fpsPath = safeData
    .map((item, index) => `${index === 0 ? "M" : "L"} ${toX(index)} ${toYFps(item.fps)}`)
    .join(" ");
  const batteryFill =
    batteryPath +
    ` L ${toX(safeData.length - 1)} ${height - pad.bottom} L ${pad.left} ${height - pad.bottom} Z`;

  return (
    <svg viewBox="0 0 500 110" className="w-full h-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="batteryGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#22c55e" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={batteryFill} fill="url(#batteryGrad)" />
      <path d={batteryPath} fill="none" stroke="#22c55e" strokeWidth="2" />
      <path d={fpsPath} fill="none" stroke="#38bdf8" strokeWidth="2" strokeDasharray="5 3" />
    </svg>
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

  const width = 500;
  const height = 100;
  const pad = { top: 8, right: 8, bottom: 8, left: 8 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const maxThroughput = Math.max(100, ...safeData.map((item) => Math.max(item.uplink, item.downlink)));
  const maxLatency = Math.max(20, ...safeData.map((item) => item.latency));

  const toX = (index: number) => pad.left + (index / (safeData.length - 1)) * innerWidth;
  const toY = (value: number, max: number) => pad.top + (1 - value / max) * innerHeight;

  const uplinkPath = safeData
    .map((item, index) => `${index === 0 ? "M" : "L"} ${toX(index)} ${toY(item.uplink, maxThroughput)}`)
    .join(" ");
  const downlinkPath = safeData
    .map((item, index) => `${index === 0 ? "M" : "L"} ${toX(index)} ${toY(item.downlink, maxThroughput)}`)
    .join(" ");
  const latencyPath = safeData
    .map((item, index) => `${index === 0 ? "M" : "L"} ${toX(index)} ${toY(item.latency, maxLatency)}`)
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

export default function AnalyticsPage() {
  const [status, setStatus] = useState<RobotStatus | null>(null);
  const [statusHistory, setStatusHistory] = useState<StatusPoint[]>([]);
  const [networkHistory, setNetworkHistory] = useState<NetworkPoint[]>([]);
  const [networkMetrics, setNetworkMetrics] = useState<JsonRecord | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState("");
  const [lastRefresh, setLastRefresh] = useState("-");

  const refreshStatus = useCallback(async () => {
    try {
      setErrorText("");

      const nextStatus = normalizeRobotStatus(await RobotAPI.status());
      setStatus(nextStatus);

      let nextNetworkMetrics: JsonRecord | null = null;
      try {
        nextNetworkMetrics = await RobotAPI.networkMetrics();
      } catch {
        nextNetworkMetrics = null;
      }
      setNetworkMetrics(nextNetworkMetrics);

      try {
        const response = (await RobotAPI.events(20, 0)) as EventsResponse;
        setEvents((response?.items ?? []).map(normalizeEventItem));
      } catch {
        setEvents([]);
      }

      const battery = clamp(getNumber(nextStatus?.battery, 0), 0, 100);
      const fps = Math.max(0, getNumber(nextStatus?.fps, 0));
      const timestamp = formatClock();
      const nextNetworkSummary = getNetworkSummary(nextNetworkMetrics);

      setStatusHistory((prev) => [...prev, { time: timestamp, battery, fps }].slice(-12));
      setNetworkHistory((prev) =>
        [
          ...prev,
          {
            time: timestamp,
            uplink: nextNetworkSummary.uplink,
            downlink: nextNetworkSummary.downlink,
            latency: nextNetworkSummary.latency,
            packetLoss: nextNetworkSummary.packetLoss,
          },
        ].slice(-12)
      );
      setLastRefresh(timestamp);
    } catch (err: any) {
      setErrorText(err?.message || "Failed to load robot status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    const timer = setInterval(refreshStatus, 5000);
    return () => clearInterval(timer);
  }, [refreshStatus]);

  const battery = clamp(getNumber(status?.battery, 0), 0, 100);
  const fps = Math.max(0, getNumber(status?.fps, 0));
  const cpuPercent = clamp(getNumber(status?.system?.cpu_percent, 0), 0, 100);
  const connectionOk = Boolean(status?.robot_connected);
  const networkSummary = getNetworkSummary(networkMetrics);
  const hasNetworkData =
    networkSummary.uplink > 0 ||
    networkSummary.downlink > 0 ||
    networkSummary.latency > 0 ||
    networkSummary.packetLoss > 0 ||
    networkSummary.signalQuality > 0;

  const poseRows = [
    {
      label: "Height Z",
      value: getNumber(status?.z_current, 0),
      range: status?.z_range,
      unit: " mm",
      colorClass: "bg-gradient-to-r from-cyan-400 to-sky-500",
    },
    {
      label: "Pitch",
      value: getNumber(status?.pitch_current, 0),
      range: status?.pitch_range,
      unit: "°",
      colorClass: "bg-gradient-to-r from-amber-400 to-orange-500",
    },
    {
      label: "Yaw",
      value: getNumber(status?.yaw_current, 0),
      range: status?.turn_speed_range,
      unit: "°",
      colorClass: "bg-gradient-to-r from-fuchsia-400 to-pink-500",
    },
  ];

  return (
    <section className="min-h-screen bg-[var(--background)] text-[var(--foreground)] p-5 flex flex-col gap-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="gradient-title text-2xl">Analytics</h1>
          <p className="text-[var(--muted)] text-sm mt-1">
            Live telemetry from <span className="text-[var(--foreground)]">/status</span> for robot{" "}
            <span className="text-blue-300">{robotId}</span>
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs px-3 py-1 rounded-full border border-[var(--border)] bg-[var(--surface)] text-[var(--foreground)]/70">
            Last refresh: {lastRefresh}
          </span>
          <button
            onClick={refreshStatus}
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

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <StatCard
          icon={<Server size={16} className={connectionOk ? "text-green-400" : "text-red-400"} />}
          iconBg={connectionOk ? "bg-green-500/20" : "bg-red-500/20"}
          label="Robot Connection"
          main={
            <span className={connectionOk ? "text-green-400" : "text-red-400"}>
              {connectionOk ? "Connected" : "Disconnected"}
            </span>
          }
          sub="robot_connected"
        />

        <StatCard
          icon={<Battery size={16} className="text-green-400" />}
          iconBg="bg-green-500/20"
          label="Battery"
          main={<span className="text-3xl text-green-400">{battery}%</span>}
          sub="Live battery level"
        />

        <StatCard
          icon={<Gauge size={16} className="text-sky-400" />}
          iconBg="bg-sky-500/20"
          label="Video FPS"
          main={<span className="text-3xl text-sky-400">{fps}</span>}
          sub="frames per second"
        />

        <StatCard
          icon={<Waves size={16} className="text-violet-400" />}
          iconBg="bg-violet-500/20"
          label="Motion Profile"
          main={
            <div className="leading-tight">
              <div className="text-lg text-violet-300">{status?.gait_type || "N/A"}</div>
              <div className="text-sm text-[var(--muted)] font-medium">{status?.speed_mode || "N/A"}</div>
            </div>
          }
          sub="gait_type and speed_mode"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-5">
        <div className="flex flex-col gap-5">
          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-start justify-between mb-3 gap-3">
              <div>
                <p className="text-[var(--foreground)] font-semibold text-sm">Battery and FPS History</p>
                <p className="text-[var(--muted)] text-xs mt-0.5">Updated every 5 seconds from live status</p>
              </div>
              <span className="text-[11px] text-emerald-400 border border-emerald-400/30 bg-emerald-500/10 rounded px-2 py-0.5">
                Battery: green, FPS: blue
              </span>
            </div>

            <div className="h-28 w-full">
              <StatusHistoryChart data={statusHistory} />
            </div>

            <div className="flex justify-between mt-2 px-1">
              {(statusHistory.length ? statusHistory : [{ time: "--", battery: 0, fps: 0 }]).map((point, index, arr) => (
                <span key={`${point.time}-${index}`} className="text-[var(--muted-2)] text-[10px]">
                  {index === 0 || index === arr.length - 1 || index % Math.max(1, Math.ceil(arr.length / 4)) === 0
                    ? point.time
                    : ""}
                </span>
              ))}
            </div>
          </div>

          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-start justify-between mb-4 gap-3">
              <div>
                <p className="text-[var(--foreground)] font-semibold text-sm">Link Throughput and Latency</p>
                <p className="text-[var(--muted)] text-xs mt-0.5">Live network telemetry between robot and backend</p>
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
                main={<span className="text-2xl text-cyan-400">{networkSummary.uplink > 0 ? `${networkSummary.uplink.toFixed(0)}` : "No data"}</span>}
                sub="kbps to backend"
              />
              <StatCard
                icon={<Server size={16} className="text-emerald-400" />}
                iconBg="bg-emerald-500/20"
                label="Downlink"
                main={<span className="text-2xl text-emerald-400">{networkSummary.downlink > 0 ? `${networkSummary.downlink.toFixed(0)}` : "No data"}</span>}
                sub="kbps from backend"
              />
              <StatCard
                icon={<Navigation size={16} className="text-orange-400" />}
                iconBg="bg-orange-500/20"
                label="Latency"
                main={<span className="text-2xl text-orange-400">{networkSummary.latency > 0 ? `${networkSummary.latency.toFixed(0)} ms` : "No data"}</span>}
                sub="Round-trip time"
              />
              <StatCard
                icon={<HeartPulse size={16} className="text-violet-400" />}
                iconBg="bg-violet-500/20"
                label="Packet loss"
                main={<span className="text-2xl text-violet-400">{networkSummary.packetLoss > 0 ? `${networkSummary.packetLoss.toFixed(2)}%` : "No data"}</span>}
                sub={`Quality ${networkSummary.signalQuality > 0 ? `${networkSummary.signalQuality.toFixed(0)}%` : "N/A"}`}
              />
            </div>

            <div className="h-28 w-full">
              <NetworkChart data={networkHistory} />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2 px-1">
              {(networkHistory.length ? networkHistory : [{ time: "--", uplink: 0, downlink: 0, latency: 0, packetLoss: 0 }]).map((point, index, arr) => (
                <span key={`${point.time}-${index}`} className="text-[var(--muted-2)] text-[10px]">
                  {index === 0 || index === arr.length - 1 || index % Math.max(1, Math.ceil(arr.length / 4)) === 0
                    ? point.time
                    : ""}
                </span>
              ))}
            </div>
          </div>

          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-start justify-between mb-4 gap-3">
              <div>
                <p className="text-[var(--foreground)] font-semibold text-sm">Body Pose and Limits</p>
                <p className="text-[var(--muted)] text-xs mt-0.5">Current posture values mapped against configured ranges</p>
              </div>
              <span className="text-[11px] text-amber-400 border border-amber-400/30 bg-amber-500/10 rounded px-2 py-0.5">
                Roll: {getNumber(status?.roll_current, 0)}°
              </span>
            </div>

            <div className="grid grid-cols-1 gap-3">
              {poseRows.map((row) => (
                <PoseBar key={row.label} label={row.label} value={row.value} range={row.range} unit={row.unit} colorClass={row.colorClass} />
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <p className="text-[var(--foreground)] font-semibold text-sm">System Overview</p>
                <p className="text-[var(--muted)] text-xs mt-0.5">Main runtime values from the robot system block</p>
              </div>
              <span className="text-[11px] text-cyan-400 border border-cyan-400/30 bg-cyan-500/10 rounded px-2 py-0.5">
                CPU {cpuPercent}%
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <MetricRow label="CPU" value={`${cpuPercent}%`} hint="system.cpu_percent" />
              <MetricRow label="RAM" value={status?.system?.ram || "N/A"} hint="system.ram" />
              <MetricRow label="Disk" value={status?.system?.disk || "N/A"} hint="system.disk" />
              <MetricRow label="IP" value={status?.system?.ip || "N/A"} hint="system.ip" />
              <MetricRow label="Robot Time" value={status?.system?.time || "N/A"} hint="system.time" />
              <MetricRow label="Firmware" value={status?.fw || "N/A"} hint="fw" />
            </div>
          </div>

          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)]">
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-[var(--foreground)] font-semibold text-sm">Runtime Flags</p>
                <p className="text-[var(--muted)] text-xs mt-0.5">Mode and safety related flags from live status</p>
              </div>
              <ShieldCheck size={16} className="text-emerald-400" />
            </div>

            <div className="grid grid-cols-1 gap-3">
              <MetricRow label="Perform" value={formatBool(status?.perform_enabled)} hint="perform_enabled" />
              <MetricRow label="Stabilizing" value={formatBool(status?.stabilizing_enabled)} hint="stabilizing_enabled" />
              <MetricRow label="Turn Speed Range" value={formatRange(status?.turn_speed_range, "°")} hint="turn_speed_range" />
              <MetricRow label="Z Range" value={formatRange(status?.z_range, " mm")} hint="z_range" />
              <MetricRow label="Pitch Range" value={formatRange(status?.pitch_range, "°")} hint="pitch_range" />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <StatCard
          icon={<HeartPulse size={16} className={connectionOk ? "text-green-400" : "text-red-400"} />}
          iconBg={connectionOk ? "bg-green-500/20" : "bg-red-500/20"}
          label="Health Snapshot"
          main={<span className={connectionOk ? "text-green-400" : "text-red-400"}>{connectionOk ? "Stable" : "Check link"}</span>}
          sub="Derived from robot_connected"
        />
        <StatCard
          icon={<Cpu size={16} className="text-orange-400" />}
          iconBg="bg-orange-500/20"
          label="System Load"
          main={<span className="text-orange-400">{cpuPercent}%</span>}
          sub="CPU usage from system block"
        />
        <StatCard
          icon={<Battery size={16} className="text-emerald-400" />}
          iconBg="bg-emerald-500/20"
          label="Step Default"
          main={<span className="text-emerald-400">{status?.step_default ?? "N/A"}</span>}
          sub="step_default"
        />
      </div>

      <div className="bg-[var(--surface)] rounded-xl border border-[var(--border)] overflow-hidden">
        <div className="p-5 pb-3">
          <h2 className="text-[var(--foreground)] text-lg font-bold">Action History</h2>
          <p className="text-[var(--muted)] text-xs mt-0.5">Recent actions and events from RobotAPI.events()</p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-t border-[var(--border)] bg-[var(--surface-2)]">
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">Timestamp</th>
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">Robot</th>
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">Action</th>
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">Severity</th>
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">Duration</th>
                <th className="text-left text-[var(--muted)] font-semibold px-5 py-3 text-xs uppercase tracking-widest">Status</th>
              </tr>
            </thead>
            <tbody>
              {events.length > 0 ? (
                events.map((row) => (
                  <tr key={row.id} className="border-t border-[var(--border)] hover:bg-[var(--surface-2)] transition-colors duration-150">
                    <td className="px-5 py-3.5 text-[var(--muted)] font-mono text-xs">{row.timestamp}</td>
                    <td className="px-5 py-3.5 text-[var(--foreground)]/80">{row.robot}</td>
                    <td className="px-5 py-3.5 text-[var(--foreground)]/80">{row.event}</td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-block px-2.5 py-0.5 rounded text-xs font-semibold ${severityBadge(row.severity)}`}>
                        {row.severity}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-[var(--muted)]">{row.duration}</td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-block px-2.5 py-0.5 rounded text-xs font-semibold ${statusBadge(row.status)}`}>
                        {row.status}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr className="border-t border-[var(--border)]">
                  <td colSpan={6} className="px-5 py-6 text-center text-[var(--muted)]">
                    Chua co lich su hanh dong.
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
