"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Battery,
  ChevronDown,
  ChevronUp,
  Cpu,
  Download,
  Expand,
  Gauge,
  HeartPulse,
  Loader2,
  MoreHorizontal,
  Navigation,
  Pause,
  Play,
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
  networkName: string;
  networkType: string;
  status: string;
  statusLabel: string;
  summary: string;
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

  // New mockable operational metrics
  voltage?: number;
  remaining_minutes?: number;
  speed?: number;
  heading?: number;
  mission_success_rate?: number;
  avg_delivery_time?: number;
  path_efficiency?: number;
  missions_total?: number;
  missions_attempted?: number;
  missions_failed?: number;
  qr_scan_success_rate?: number;
  total_distance?: number;
};

type SessionEvent = {
  time: string;
  type: string;
};

type EffPoint = { time: string; eff: number };

type PatrolResult = {
  point: string;
  status: string;
  attempts: number;
  reach_time_sec: number | null;
  started_at: string | null;
  finished_at: string | null;
};

type PatrolMission = {
  mission_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  total_distance_m?: number | null;
  results: PatrolResult[];
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

  // Derive robot state string
  let derivedState = "Idle";
  if (raw?.robot_connected) {
    derivedState = raw?.gait_type ? "Navigating" : "Online";
  } else {
    derivedState = "Offline";
  }

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

function getNetworkString(source: JsonRecord | null, keys: string[], fallback = "") {
  if (!source) return fallback;

  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }

  const nested = source.data || source.result || source.metrics || source.connection;
  if (nested && nested !== source) {
    return getNetworkString(nested, keys, fallback);
  }

  return fallback;
}

function getNetworkSummary(source: JsonRecord | null): NetworkSummary {
  const networkName = getNetworkString(source, ["network_name", "name", "ssid", "interface"], "Unknown network");
  const statusLabel = getNetworkString(source, ["network_status_label", "status_label"], "N/A");

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
    networkName,
    networkType: getNetworkString(source, ["network_type", "type"], "unknown"),
    status: getNetworkString(source, ["network_status", "status"], "unknown"),
    statusLabel,
    summary: getNetworkString(source, ["network_summary", "summary"], `${networkName} - ${statusLabel}`),
  };
}

function networkStatusColor(statusValue: string) {
  const status = statusValue.toLowerCase();
  if (status === "strong") return "text-[#4ade80]";
  if (status === "medium") return "text-[#facc15]";
  if (status === "weak") return "text-[#fb923c]";
  if (status === "offline") return "text-red-400";
  return "text-white";
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

function DataCard({
  label,
  value,
  mainColor = "text-white",
  sub,
  trend,
  trendColor = "text-green-400",
  indicator,
}: {
  label: string;
  value: React.ReactNode;
  mainColor?: string;
  sub?: React.ReactNode;
  trend?: string;
  trendColor?: string;
  indicator?: React.ReactNode;
}) {
  return (
    <div className="bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg p-4 flex flex-col justify-between min-h-[110px]">
      <div className="flex justify-between items-start gap-2">
        <span className="text-[#888888] text-xs font-medium uppercase tracking-wider">{label}</span>
        {indicator}
      </div>
      <div className="mt-1">
        <div className={`text-2xl font-bold tracking-tight ${mainColor}`}>{value}</div>
        <div className="flex items-center gap-1.5 mt-1 min-h-[20px]">
          {trend ? <span className={`text-xs font-semibold ${trendColor}`}>{trend}</span> : null}
          {sub ? <span className="text-[#888888] text-xs font-medium truncate">{sub}</span> : null}
        </div>
      </div>
    </div>
  );
}

function MiniMetric({
  label,
  value,
  color = "text-white",
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-[#888888] text-[10px] uppercase font-bold tracking-widest">{label}</div>
      <div className={`text-base font-bold tracking-tight ${color}`}>{value}</div>
    </div>
  );
}

function StatusHistoryChart({ data }: { data: StatusPoint[] }) {
  const safeData =
    data.length > 2
      ? data
      : [
        { time: "00:00", battery: 80, fps: 30 },
        { time: "00:01", battery: 78, fps: 30 },
        { time: "00:02", battery: 75, fps: 30 },
      ];

  const width = 600;
  const height = 120;
  const pad = { top: 15, right: 10, bottom: 5, left: 10 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;

  const toX = (index: number) => pad.left + (index / (safeData.length - 1)) * innerWidth;
  const toY = (v: number) => pad.top + (1 - v / 100) * innerHeight;

  const pathD = safeData
    .map((p, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toY(p.battery)}`)
    .join(" ");

  // Mock mission event markers (vertical items)
  const markers = [0.3, 0.6, 0.9].map((ratio) => Math.floor(ratio * (safeData.length - 1)));

  return (
    <div className="relative w-full h-[140px] bg-[#1a1a1a] rounded-lg border border-[#2d2d2d] p-4">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-bold text-gray-400">Battery over time</span>
        <div className="flex gap-4">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-[#4ade80]" />
            <span className="text-[10px] text-gray-400 font-medium">battery %</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-[#60a5fa]" />
            <span className="text-[10px] text-gray-400 font-medium">mission events</span>
          </div>
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-[80px]" preserveAspectRatio="none">
        {markers.map((idx, i) => (
          <line
            key={i}
            x1={toX(idx)}
            y1={0}
            x2={toX(idx)}
            y2={height}
            stroke="#60a5fa"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            opacity="0.6"
          />
        ))}
        <path d={pathD} fill="none" stroke="#4ade80" strokeWidth="2.5" />
      </svg>
    </div>
  );
}

function DeliveryBarChart({ missions }: { missions: PatrolMission[] }) {
  const bars = missions.map(m => ({
    // Lấy reach_time_sec của điểm đầu tiên trong mission
    value: m.results?.[0]?.reach_time_sec ?? 0,
    success: m.status === "completed",
  }));

  if (bars.length === 0) {
    return (
      <div className="relative w-full h-[140px] bg-[#1a1a1a] rounded-lg
                       border border-[#2d2d2d] p-4 flex items-center justify-center">
        <span className="text-[#888888] text-sm">Chưa có mission data</span>
      </div>
    );
  }

  const max = Math.max(...bars.map(b => b.value), 1);
  return (
    <div className="relative w-full h-[140px] bg-[#1a1a1a] rounded-lg border border-[#2d2d2d] p-4">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-bold text-gray-400">Delivery time per mission</span>
        <div className="flex gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-[#4ade80]" />
            <span className="text-[10px] text-gray-400">success</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-[#f87171]" />
            <span className="text-[10px] text-gray-400">failed</span>
          </div>
        </div>
      </div>
      <div className="flex items-end justify-between h-[80px] pt-2 gap-1">
        {bars.map((b, i) => (
          <div
            key={i}
            className={`flex-1 rounded-t-sm ${b.success ? "bg-[#4ade80]" : "bg-[#f87171]"}`}
            style={{ height: `${(b.value / max) * 100}%`, opacity: 0.75 }}
            title={`${b.value}s — ${b.success ? "success" : "failed"}`}
          />
        ))}
      </div>
    </div>
  );
}


function EfficiencyChart({ data }: { data: EffPoint[] }) {
  const width = 600;
  const height = 100;

  const safeData = data.length >= 2 ? data : [
    { time: "", eff: 0 },
    { time: "", eff: 0 },
  ];

  const toX = (i: number) => (i / (safeData.length - 1)) * width;
  const toYEff = (v: number) => height - (v / 100) * height;

  const d1 = safeData
    .map((p, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toYEff(p.eff)}`)
    .join(" ");

  return (
    <div className="relative w-full h-[140px] bg-[#1a1a1a] rounded-lg
                     border border-[#2d2d2d] p-4 mt-2">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-bold text-gray-400">
          Path efficiency trend
        </span>
        <div className="flex gap-4">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-[#a78bfa]" />
            <span className="text-[10px] text-gray-400">efficiency %</span>
          </div>
        </div>
      </div>
      {data.length < 2 ? (
        <div className="flex items-center justify-center h-[80px]">
          <span className="text-[#888888] text-xs">Đang tích lũy data...</span>
        </div>
      ) : (
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-[90px]"
          preserveAspectRatio="none">
          <path d={d1} fill="none" stroke="#a78bfa" strokeWidth="2.5" />
        </svg>
      )}
    </div>
  );
}

export default function AnalyticsPage() {
  const [status, setStatus] = useState<RobotStatus | null>(null);
  const [statusHistory, setStatusHistory] = useState<StatusPoint[]>([]);
  const [networkHistory, setNetworkHistory] = useState<NetworkPoint[]>([]);
  const [networkMetrics, setNetworkMetrics] = useState<JsonRecord | null>(null);
  const [pathEfficiency, setPathEfficiency] = useState<number | null>(null);
  const [totalDistance, setTotalDistance] = useState<number | null>(null);
  const [effHistory, setEffHistory] = useState<EffPoint[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState("");
  const [lastRefresh, setLastRefresh] = useState("-");
  const [isPaused, setIsPaused] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [filterDate, setFilterDate] = useState<string>("today");

  const [missionStats, setMissionStats] = useState({
    attempted: 0,
    completed: 0,
    failed: 0,
    successRate: 0,
    avgDelivery: 0,
  });
  const [patrolMissions, setPatrolMissions] = useState<PatrolMission[]>([]);

  const [qrMetrics, setQrMetrics] = useState({
    attempts: 0,
    successes: 0,
    successRate: 0,
  });

  const refreshStatus = useCallback(async () => {
    try {
      setErrorText("");
      let newPathEfficiency: number | null = null;
      let newObstacleEvents: number | null = null;

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

      try {
        const navResp = await RobotAPI.navigationMetrics();
        const metrics = navResp?.data ?? navResp ?? {};
        const nextPathEfficiency = Number(metrics.path_efficiency_pct);
        setPathEfficiency(Number.isFinite(nextPathEfficiency) ? nextPathEfficiency : null);
      } catch {
        setPathEfficiency(null);
      }

      try {
        const qrResp = await RobotAPI.qrMetrics();
        const qrData = qrResp?.qr_scan || {};
        setQrMetrics({
          attempts: Number(qrData.attempts) || 0,
          successes: Number(qrData.successes) || 0,
          successRate: Number(qrData.success_rate_pct) || 0,
        });
      } catch (err) {
        console.warn("Failed to fetch QR metrics:", err);
      }

      try {
        const histResp = await RobotAPI.patrolHistory(filterDate) as any;
        const missions: PatrolMission[] = histResp?.history ?? [];
        setPatrolMissions(missions);

        const attempted = missions.length;
        const completed = missions.filter(m => m.status === "completed").length;

        // ✅ FIX: tính cả stopped vào failed
        const failed = missions.filter(m =>
          m.status === "failed" || m.status === "stopped"
        ).length;

        const successRate = attempted > 0
          ? Math.round(completed / attempted * 100) : 0;

        // ✅ FIX: fallback tính avgDelivery
        const times = missions
          .filter(m => m.status === "completed")
          .flatMap(m => {
            const fromResults = (m.results ?? [])
              .map(r => r.reach_time_sec)
              .filter((t): t is number => t != null && t > 0);
            if (fromResults.length > 0) return fromResults;
            if (m.started_at != null && m.finished_at != null) {
              const diff = Number(m.finished_at) - Number(m.started_at);
              if (diff > 0) return [diff];
            }
            return [];
          });
        const avgDelivery = times.length > 0
          ? Math.round(times.reduce((a, b) => a + b, 0) / times.length) : 0;

        const calculatedTotalDistance = missions.reduce((sum, m) => sum + (m.total_distance_m || 0), 0);
        setTotalDistance(calculatedTotalDistance > 0 ? Number(calculatedTotalDistance.toFixed(2)) : null);

        setMissionStats({ attempted, completed, failed, successRate, avgDelivery });
      } catch (err) {
        console.error("Failed to fetch patrol history:", err);
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
      setEffHistory(prev => [...prev, {
        time: timestamp,
        eff: pathEfficiency ?? 0,

      }].slice(-20));
    } catch (err: any) {
      setErrorText(err?.message || "Failed to load robot status");
    } finally {
      setLoading(false);
    }
  }, [filterDate]);

  useEffect(() => {
    if (!isPaused) {
      refreshStatus();
      const timer = setInterval(refreshStatus, 5000);
      return () => clearInterval(timer);
    }
  }, [refreshStatus, isPaused]);

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

  const roll = status?.roll_current ?? 0;
  const pitch = status?.pitch_current ?? 0;
  const imuLabel = Math.abs(roll) < 10 && Math.abs(pitch) < 15
    ? "Stable"
    : "Unstable";
  const imuColor = imuLabel === "Stable"
    ? "text-white"
    : "text-red-400";

  return (
    <div className="min-h-screen text-white p-6 font-sans">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Analytics</h1>
          <p className="text-[#888888] text-sm mt-0.5 font-medium"> Операционный мониторинг — robot dogzilla_s2</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-[#1a1a1a] border border-[#2d2d2d] rounded-full px-3 py-1.5">
            <div className={`w-2 h-2 rounded-full ${isPaused ? "bg-orange-500" : "bg-green-500 animate-pulse"}`} />
            <span className={`${isPaused ? "text-orange-500" : "text-[#4ade80]"} text-[10px] font-bold uppercase tracking-wider`}>
              {isPaused ? "Paused" : "Live • auto-refresh 5s"}
            </span>
          </div>
          <select 
            value={filterDate === 'today' || filterDate === 'all' ? filterDate : 'custom'}
            onChange={(e) => {
              if (e.target.value === 'today' || e.target.value === 'all') {
                setFilterDate(e.target.value);
              } else {
                const tzoffset = (new Date()).getTimezoneOffset() * 60000;
                const localISOTime = (new Date(Date.now() - tzoffset)).toISOString().slice(0, 10);
                setFilterDate(localISOTime);
              }
            }}
            className="cursor-pointer bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg px-3 py-2 text-sm font-bold outline-none hover:bg-[#252525] transition-colors text-white appearance-none"
          >
            <option value="today">Today</option>
            <option value="all">All Time</option>
            <option value="custom">Custom Date</option>
          </select>
          {filterDate !== 'today' && filterDate !== 'all' && (
            <input 
              type="date"
              value={filterDate}
              onChange={(e) => setFilterDate(e.target.value)}
              className="cursor-pointer bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg px-3 py-[6px] text-sm font-bold outline-none hover:bg-[#252525] transition-colors text-white"
              style={{ colorScheme: 'dark' }}
            />
          )}
          <button onClick={() => setIsPaused(!isPaused)}
            className="cursor-pointer flex items-center gap-2 bg-[#1a1a1a] border border-[#2d2d2d] hover:bg-[#252525] transition-colors rounded-lg px-4 py-2 text-sm font-bold"
          >
            {isPaused ? <Play size={14} className="fill-current" /> : <Pause size={14} className="fill-current" />}
            {isPaused ? "Pause" : "Pause"}
          </button>
          <button className="cursor-pointer flex items-center gap-2 bg-[#1a1a1a] border border-[#2d2d2d] hover:bg-[#252525] transition-colors rounded-lg px-4 py-2 text-sm font-bold">
            <Download size={14} />
            Export session
          </button>
          <button className="cursor-pointer p-2 hover:bg-[#1a1a1a] rounded-lg text-gray-400">
            <MoreHorizontal size={20} />
          </button>
        </div>
      </div>

      <div className="space-y-8">
        {/* ZONE 1 - ROBOT HEALTH */}
        <section>
          <h2 className="text-[#888888] text-[10px] font-bold uppercase tracking-[0.2em] mb-4 border-b border-[#2d2d2d] pb-2">
            Zone 1 — Robot Health
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <DataCard
              label="Connection"
              value={connectionOk ? "Connected" : "Disconnected"}
              mainColor={connectionOk ? "text-[#4ade80]" : "text-red-500"}
              sub={`${status?.system?.ip || "192.168.1.105"} • ROS2`}
              indicator={
                <div className={`w-2.5 h-2.5 rounded-full ${connectionOk ? "bg-[#4ade80]" : "bg-red-500"}`} />
              }
            />
            <DataCard
              label="Battery"
              value={`${battery}%`}
              sub={`~${status?.remaining_minutes ?? "?"} min · ${status?.voltage != null ? `${status.voltage.toFixed(1)}V` : "N/A"
                }`}
            />
            <DataCard
              label="IMU posture"
              value={imuLabel}
              mainColor={imuColor}
              sub={`Roll ${roll.toFixed(1)}° · Pitch ${pitch.toFixed(1)}°`}
            />
            <DataCard
              label="Robot state"
              value={status?.gait_type || "Navigating"}
              mainColor="text-[#60a5fa]"
              sub={`${status?.speed || 0.18} m/s • heading ${status?.yaw_current ?? "N/A"}°`}
            />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 px-2 max-w-2xl">
            <MiniMetric label="CPU" value={`${cpuPercent}%`} />
            <MiniMetric label="RAM" value={status?.system?.ram ?? "N/A"} />
            <MiniMetric label="Disk" value={status?.system?.disk ?? "N/A"} />
            <MiniMetric label="Firmware" value={status?.fw ?? "N/A"} />
          </div>
        </section>

        {/* ZONE 2 - MISSION PERFORMANCE */}
        <section>
          <h2 className="text-[#888888] text-[10px] font-bold uppercase tracking-[0.2em] mb-4 border-b border-[#2d2d2d] pb-2">
            Zone 2 — Mission Performance ({filterDate === 'today' ? 'Today' : filterDate === 'all' ? 'All Time' : filterDate})
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <DataCard
              label="Mission success rate"
              value={missionStats.attempted > 0 ? `${missionStats.successRate}%` : "N/A"}
              trend={undefined}
            />
            <DataCard
              label="Avg delivery time"
              value={missionStats.avgDelivery > 0 ? `${missionStats.avgDelivery}s` : "N/A"}
              trend={undefined}
              trendColor="text-red-400"
            />
            <DataCard
              label="Path efficiency"
              value={pathEfficiency != null ? `${pathEfficiency}%` : "N/A"}
              sub="actual / optimal path"
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg p-4">
              <span className="text-[#888888] text-[10px] font-bold uppercase tracking-wider">Missions today</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-2xl font-bold">{missionStats.completed}</span>
                <span className="text-[#888888] text-sm">/ {missionStats.attempted} attempted</span>
              </div>
              <div className="text-[#888888] text-xs mt-1">{missionStats.failed} failed • 0 aborted</div>
            </div>
            {/* <div className="bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg p-4">
              <span className="text-[#888888] text-[10px] font-bold uppercase tracking-wider">QR scan success</span>
              <div className="text-2xl font-bold mt-1">{status?.qr_scan_success_rate || 94}%</div>
              <div className="text-[#888888] text-xs mt-1">17/18 scans • avg 320ms</div>
            </div> */}
            <div className="bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg p-4">
              <span className="text-[#888888] text-[10px] font-bold uppercase tracking-wider">QR scan success rate</span>
              <div className="flex items-baseline gap-3 mt-2">
                <span className="text-3xl font-bold text-[#4ade80]">
                  {qrMetrics.successRate}%
                </span>
                <span className="text-[#888888] text-sm">
                  {qrMetrics.successes} / {qrMetrics.attempts}
                </span>
              </div>

              {/* Progress Bar */}
              <div className="mt-3 h-1.5 bg-[#2d2d2d] rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-emerald-400 to-cyan-400 rounded-full transition-all duration-500"
                  style={{ width: `${qrMetrics.successRate}%` }}
                />
              </div>

              <div className="text-[#888888] text-xs mt-2">
                Today • Attempt: {qrMetrics.attempts} • Success: {qrMetrics.successes}
              </div>
            </div>
            <div className="bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg p-4">
              <span className="text-[#888888] text-[10px] font-bold uppercase tracking-wider">Total distance</span>
              <div className="text-2xl font-bold mt-1">{totalDistance != null ? `${totalDistance}m` : "N/A"}</div>
              <div className="text-[#888888] text-xs mt-1">9.8m / % battery • efficient</div>
            </div>
          </div>
        </section>

        {/* ZONE 3 - TIME-SERIES CHARTS */}
        <section>
          <h2 className="text-[#888888] text-[10px] font-bold uppercase tracking-[0.2em] mb-4 border-b border-[#2d2d2d] pb-2">
            Zone 3 — Time-series charts
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <StatusHistoryChart data={statusHistory} />
            <DeliveryBarChart missions={patrolMissions} />
          </div>
          <EfficiencyChart data={effHistory} />
        </section>

        {/* ZONE 4 - NETWORK */}
        <section>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-[#888888] text-[10px] font-bold uppercase tracking-[0.2em]">
              Zone 4 — Network
            </h2>
            <button onClick={() => setIsExpanded(!isExpanded)}
              className="cursor-pointer flex items-center gap-2 bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider hover:bg-[#252525] transition-colors"
            >
              <Expand size={12} />
              {isExpanded ? "Collapse" : "Expand"}
            </button>
          </div>

          <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg p-4 md:col-span-2">
              <span className="text-[#888888] text-[10px] font-bold uppercase tracking-wider">
                Mang dang ket noi
              </span>
              <div className="mt-2 text-2xl font-bold text-white">
                {networkSummary.networkName}
              </div>
              <div className="mt-1 text-xs text-[#888888]">
                {networkSummary.networkType.toUpperCase()} - {networkSummary.summary}
              </div>
            </div>

            <div className="bg-[#1a1a1a] border border-[#2d2d2d] rounded-lg p-4">
              <span className="text-[#888888] text-[10px] font-bold uppercase tracking-wider">
                Status
              </span>
              <div className={`mt-2 text-2xl font-bold ${networkStatusColor(networkSummary.status)}`}>
                {networkSummary.statusLabel}
              </div>
              <div className="mt-1 text-xs text-[#888888]">
                Signal quality: {hasNetworkData ? `${networkSummary.signalQuality}%` : "N/A"}
              </div>
            </div>
          </div>

          <div className={`transition-all duration-300 ease-in-out overflow-hidden ${isExpanded ? "max-h-[260px] opacity-100" : "max-h-0 opacity-0"}`}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-8 px-4 py-6 bg-[#1a1a1a] rounded-lg border border-[#2d2d2d]">
              <MiniMetric label="Uplink" value={networkSummary.uplink > 0 ? `${networkSummary.uplink.toFixed(0)} kbps` : "N/A"} color="text-white font-bold" />
              <MiniMetric label="Downlink" value={networkSummary.downlink > 0 ? `${networkSummary.downlink.toFixed(0)} kbps` : "N/A"} color="text-white font-bold" />
              <MiniMetric label="Latency" value={networkSummary.latency > 0 ? `${networkSummary.latency.toFixed(0)} ms` : "N/A"} color="text-white font-bold" />
              <MiniMetric label="Packet loss" value={networkSummary.packetLoss >= 0 && hasNetworkData ? `${networkSummary.packetLoss.toFixed(1)}%` : "N/A"} color={networkSummary.packetLoss > 1 ? "text-red-400" : "text-[#4ade80] font-bold"} />
            </div>
          </div>
        </section>
      </div>

      {errorText ? (
        <div className="fixed bottom-6 right-6 max-w-sm bg-red-900 border border-red-500 rounded-lg p-4 text-sm text-red-100 shadow-2xl z-50">
          <div className="flex items-center gap-2 font-bold mb-1">
            <ShieldCheck size={16} />
            System Alert
          </div>
          {errorText}
        </div>
      ) : null}
    </div>
  );
}
