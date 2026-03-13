"use client";

import { Battery, Zap, TrendingUp, AlertTriangle, Navigation } from "lucide-react";

// ─── Mock Data ────────────────────────────────────────────────────────────────

const BATTERY_CHART_DATA = [
    { hour: "0h", battery: 95, power: 12 },
    { hour: "2h", battery: 92, power: 11 },
    { hour: "4h", battery: 88, power: 13 },
    { hour: "6h", battery: 82, power: 14 },
    { hour: "8h", battery: 76, power: 15 },
    { hour: "10h", battery: 70, power: 14 },
    { hour: "12h", battery: 75, power: 10 }, // charging
    { hour: "14h", battery: 82, power: 11 },
    { hour: "16h", battery: 78, power: 15 },
    { hour: "18h", battery: 73, power: 16 },
    { hour: "20h", battery: 68, power: 14 },
    { hour: "22h", battery: 72, power: 10 }, // charging
    { hour: "24h", battery: 68, power: 12 },
];

const NAV_ERRORS = [
    { label: "Stair Detection", count: 4, max: 4 },
    { label: "Obstacle Re-route", count: 3, max: 4 },
    { label: "Balance Recovery", count: 3, max: 4 },
    { label: "Path Timeout", count: 2, max: 4 },
    { label: "Localization Drift", count: 1, max: 4 },
    { label: "Sensor Conflict", count: 1, max: 4 },
];

const CRITICAL_EVENTS = [
    {
        timestamp: "2026-03-05 14:23",
        robot: "Dogzilla-04",
        event: "Stair Detection Failure",
        severity: "Critical",
        duration: "14 min",
        status: "Active",
    },
    {
        timestamp: "2026-03-05 13:45",
        robot: "Dogzilla-03",
        event: "Battery Critical",
        severity: "Warning",
        duration: "5 min",
        status: "Resolved",
    },
    {
        timestamp: "2026-03-05 12:15",
        robot: "Dogzilla-01",
        event: "LIDAR Recalibration",
        severity: "Medium",
        duration: "18 min",
        status: "Resolved",
    },
    {
        timestamp: "2026-03-05 11:30",
        robot: "Dogzilla-04",
        event: "Balance Controller Fault",
        severity: "High",
        duration: "22 min",
        status: "Resolved",
    },
    {
        timestamp: "2026-03-05 10:20",
        robot: "Dogzilla-02",
        event: "Path Planning Timeout",
        severity: "Medium",
        duration: "8 min",
        status: "Resolved",
    },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function severityBadge(severity: string) {
    const map: Record<string, string> = {
        Critical: "bg-red-500/20 text-red-400 border border-red-500/40",
        Warning: "bg-orange-500/20 text-orange-400 border border-orange-500/40",
        High: "bg-amber-500/20 text-amber-400 border border-amber-500/40",
        Medium: "bg-blue-500/20 text-blue-400 border border-blue-500/40",
        Low: "bg-slate-500/20 text-slate-400 border border-slate-500/40",
    };
    return map[severity] ?? map["Low"];
}

function statusBadge(status: string) {
    return status === "Active"
        ? "bg-red-500/20 text-red-400 border border-red-500/40"
        : "bg-green-500/20 text-green-400 border border-green-500/40";
}

// ─── Battery Line Chart (pure SVG) ───────────────────────────────────────────

function BatteryChart() {
    const W = 500;
    const H = 100;
    const pad = { top: 8, right: 8, bottom: 8, left: 8 };
    const iW = W - pad.left - pad.right;
    const iH = H - pad.top - pad.bottom;

    const toX = (i: number) => pad.left + (i / (BATTERY_CHART_DATA.length - 1)) * iW;
    const toYBat = (v: number) => pad.top + (1 - v / 100) * iH;
    const toYPow = (v: number) => pad.top + (1 - v / 20) * iH;

    const batteryPath = BATTERY_CHART_DATA.map(
        (d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toYBat(d.battery)}`
    ).join(" ");

    const powerPath = BATTERY_CHART_DATA.map(
        (d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toYPow(d.power)}`
    ).join(" ");

    const batteryFill =
        batteryPath +
        ` L ${toX(BATTERY_CHART_DATA.length - 1)} ${H - pad.bottom} L ${pad.left} ${H - pad.bottom} Z`;

    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full" preserveAspectRatio="none">
            <defs>
                <linearGradient id="batGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity="0.4" />
                    <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
                </linearGradient>
            </defs>
            {/* Battery fill */}
            <path d={batteryFill} fill="url(#batGrad)" />
            {/* Battery line */}
            <path d={batteryPath} fill="none" stroke="#10b981" strokeWidth="1.5" />
            {/* Power line */}
            <path d={powerPath} fill="none" stroke="#f97316" strokeWidth="1.5" strokeDasharray="4 2" />
        </svg>
    );
}

// ─── Circular Progress (success rate) ────────────────────────────────────────

function CircleProgress({ value }: { value: number }) {
    const r = 38;
    const circ = 2 * Math.PI * r;
    const dash = (value / 100) * circ;
    return (
        <svg width="96" height="96" viewBox="0 0 96 96">
            {/* Track */}
            <circle cx="48" cy="48" r={r} fill="none" stroke="#ffffff10" strokeWidth="8" />
            {/* Progress */}
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
                style={{ transition: "stroke-dasharray 0.5s ease" }}
            />
            {/* Label */}
            <text x="48" y="53" textAnchor="middle" fill="white" fontSize="15" fontWeight="700">
                {value}%
            </text>
        </svg>
    );
}

// ─── Nav Error Bar ────────────────────────────────────────────────────────────

function NavErrorBar({ label, count, max }: { label: string; count: number; max: number }) {
    const pct = (count / max) * 100;
    return (
        <div className="flex items-center gap-2 text-xs">
            <span className="text-white/60 w-32 shrink-0 truncate">{label}</span>
            <div className="flex-1 bg-white/10 rounded-full h-1.5">
                <div
                    className="h-1.5 rounded-full bg-gradient-to-r from-blue-500 to-purple-500"
                    style={{ width: `${pct}%` }}
                />
            </div>
            <span className="text-white/80 w-3 text-right">{count}</span>
        </div>
    );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

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
        <div className="bg-[#0f0822] rounded-xl p-4 flex flex-col gap-1 border border-white/5">
            <div className="flex items-center gap-2 mb-1">
                <div className={`p-1.5 rounded-lg ${iconBg}`}>{icon}</div>
                <span className="text-white/60 text-xs font-medium">{label}</span>
            </div>
            <div className="text-2xl font-bold text-white">{main}</div>
            {sub && <div className={`text-xs ${subColor}`}>{sub}</div>}
            {extra}
        </div>
    );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
    return (
        <section className="min-h-screen bg-[#160626] text-white p-5 flex flex-col gap-6">
            {/* Title */}
            <h1 className="gradient-title text-center text-2xl">Analytics</h1>

            {/* ── Top Two-Column Layout ── */}
            <div className="grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-5">

                {/* ── LEFT: Battery & Power Management ── */}
                <div className="flex flex-col gap-4">
                    <h2 className="text-white text-xl font-bold">Battery &amp; Power Management</h2>

                    {/* Stat cards row */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <StatCard
                            icon={<Battery size={16} className="text-green-400" />}
                            iconBg="bg-green-500/20"
                            label="Current Battery Level"
                            main={<><span className="text-3xl text-green-400">68%</span></>}
                            sub="5.2 hr remaining"
                            subColor="text-white/50"
                            extra={
                                <div className="flex gap-1 mt-1">
                                    {[1, 1, 1, 0, 0].map((on, i) => (
                                        <div
                                            key={i}
                                            className={`h-1.5 flex-1 rounded-full ${on ? "bg-green-400" : "bg-white/20"}`}
                                        />
                                    ))}
                                </div>
                            }
                        />
                        <StatCard
                            icon={<TrendingUp size={16} className="text-green-400" />}
                            iconBg="bg-green-500/20"
                            label="Avg Battery Life"
                            main={<><span className="text-3xl text-green-400">9.2</span><span className="text-lg text-white/60">h</span></>}
                            sub="+0.5h vs last week"
                            subColor="text-green-400"
                            extra={<span className="text-white/40 text-[11px]">Per full charge</span>}
                        />
                        <StatCard
                            icon={<Zap size={16} className="text-yellow-400" />}
                            iconBg="bg-yellow-500/20"
                            label="Avg Power Draw"
                            main={<><span className="text-3xl text-yellow-400">14.2</span><span className="text-base text-white/60">w</span></>}
                            sub="+ 4.3w vs last week"
                            subColor="text-red-400"
                            extra={<span className="text-white/40 text-[11px]">Last 24 hours</span>}
                        />
                    </div>

                    {/* Battery Chart Card */}
                    <div className="bg-[#0f0822] rounded-xl p-4 border border-white/5">
                        <div className="flex items-start justify-between mb-3">
                            <div>
                                <p className="text-white font-semibold text-sm">Battery &amp; Energy Consumption</p>
                                <p className="text-white/40 text-xs mt-0.5">
                                    Battery level and power draw over 24 hours — Dogzilla-04
                                </p>
                            </div>
                            <span className="text-[11px] text-blue-400 border border-blue-400/30 bg-blue-500/10 rounded px-2 py-0.5">
                                ⚡ Charging at 12:15 &amp; 22:00
                            </span>
                        </div>

                        {/* Chart */}
                        <div className="h-28 w-full">
                            <BatteryChart />
                        </div>

                        {/* X-axis labels */}
                        <div className="flex justify-between mt-1 px-1">
                            {["0h", "4h", "8h", "12h", "16h", "20h", "24h"].map((h) => (
                                <span key={h} className="text-white/30 text-[10px]">
                                    {h}
                                </span>
                            ))}
                        </div>

                        {/* Legend */}
                        <div className="flex gap-5 mt-3">
                            <div className="flex items-center gap-1.5">
                                <div className="w-6 h-0.5 bg-green-400 rounded-full" />
                                <span className="text-white/50 text-[11px]">Battery %</span>
                            </div>
                            <div className="flex items-center gap-1.5">
                                <div className="w-6 h-0.5 bg-orange-400 rounded-full" style={{ borderTop: "1.5px dashed #f97316", background: "none" }} />
                                <span className="text-white/50 text-[11px]">Power Draw (W)</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* ── RIGHT: Navigation Efficiency ── */}
                <div className="flex flex-col gap-4">
                    <h2 className="text-white text-xl font-bold">Navigation Efficiency</h2>

                    {/* Success Rate Card */}
                    <div className="bg-[#0f0822] rounded-xl p-4 border border-white/5">
                        <div className="flex items-center gap-2 mb-3">
                            <Navigation size={14} className="text-blue-400" />
                            <span className="text-white/60 text-xs font-medium uppercase tracking-widest">
                                Navigation Success Rate
                            </span>
                            <span className="ml-auto text-2xl font-bold text-white">92%</span>
                        </div>
                        <div className="flex items-center gap-4">
                            <CircleProgress value={92} />
                            <div className="flex-1">
                                {/* Mini sparkline placeholder */}
                                <svg viewBox="0 0 120 40" className="w-full h-10">
                                    <polyline
                                        points="0,30 20,25 40,28 60,15 80,18 100,10 120,12"
                                        fill="none"
                                        stroke="#10b981"
                                        strokeWidth="1.5"
                                    />
                                    <polyline
                                        points="0,35 20,32 40,34 60,28 80,30 100,25 120,27"
                                        fill="none"
                                        stroke="#f97316"
                                        strokeWidth="1.5"
                                        strokeOpacity="0.6"
                                    />
                                </svg>
                                <p className="text-green-400 text-xs mt-1">+1.2% vs last week</p>
                            </div>
                        </div>
                    </div>

                    {/* Navigation Errors Card */}
                    <div className="bg-[#0f0822] rounded-xl p-4 border border-white/5">
                        <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                                <AlertTriangle size={14} className="text-orange-400" />
                                <span className="text-white/60 text-xs font-medium uppercase tracking-widest">
                                    Navigation Errors
                                </span>
                            </div>
                            <span className="text-2xl font-bold text-white">5</span>
                        </div>
                        <div className="flex gap-6 mb-4">
                            <div>
                                <p className="text-white font-semibold text-sm">5</p>
                                <p className="text-white/40 text-[11px]">Today</p>
                            </div>
                            <div>
                                <p className="text-white font-semibold text-sm">27</p>
                                <p className="text-white/40 text-[11px]">Past Week</p>
                            </div>
                            <div className="ml-auto">
                                <p className="text-red-400 text-xs">+27 Past Week</p>
                            </div>
                        </div>

                        {/* Error type breakdown */}
                        <p className="text-white/40 text-[11px] mb-3 uppercase tracking-widest">
                            Navigation Errors | by Type
                        </p>
                        <div className="space-y-2">
                            {NAV_ERRORS.map((e) => (
                                <NavErrorBar key={e.label} {...e} />
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* ── Recent Critical Events Table ── */}
            <div className="bg-[#0f0822] rounded-xl border border-white/5 overflow-hidden">
                <div className="p-5 pb-3">
                    <h2 className="text-white text-lg font-bold">Recent Critical Events</h2>
                    <p className="text-white/40 text-xs mt-0.5">
                        High-severity incidents from the past 24 hours
                    </p>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-t border-white/10 bg-white/5">
                                <th className="text-left text-white/50 font-semibold px-5 py-3 text-xs uppercase tracking-widest">
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
                            {CRITICAL_EVENTS.map((row, i) => (
                                <tr
                                    key={i}
                                    className="border-t border-white/5 hover:bg-white/5 transition-colors duration-150"
                                >
                                    <td className="px-5 py-3.5 text-white/70 font-mono text-xs">{row.timestamp}</td>
                                    <td className="px-5 py-3.5 text-white/80">{row.robot}</td>
                                    <td className="px-5 py-3.5 text-white/80">{row.event}</td>
                                    <td className="px-5 py-3.5">
                                        <span
                                            className={`inline-block px-2.5 py-0.5 rounded text-xs font-semibold ${severityBadge(row.severity)}`}
                                        >
                                            {row.severity}
                                        </span>
                                    </td>
                                    <td className="px-5 py-3.5 text-white/70">{row.duration}</td>
                                    <td className="px-5 py-3.5">
                                        <span
                                            className={`inline-block px-2.5 py-0.5 rounded text-xs font-semibold ${statusBadge(row.status)}`}
                                        >
                                            {row.status}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    );
}
