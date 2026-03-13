"use client";

import { useState } from "react";
import { Bot, Wifi, WifiOff, Activity, AlertTriangle } from "lucide-react";

// ─── Mock data (thay thế bằng API thực tế sau) ─────────────────────────────
const ROBOT = {
    name: "Robot A",
    connected: true,
    location: "25.23234, 19.76543",
    cleaningProgress: "80% (stopped)",
    floor: "1st",
    status: "Resting",
    waterLevel: "50%",
    battery: "85%",
};

const SENSOR_METRICS = [
    { label: "Motor", value: "80%" },
    { label: "Speech", value: "90%" },
    { label: "Vision", value: "70%" },
    { label: "Air", value: "90%" },
    { label: "Water", value: "80%" },
    { label: "Speed", value: "90%" },
    { label: "Sensor", value: "100%" },
    { label: "Battery", value: "80%" },
];

const ACTIVITY_LOG = [
    "10:30 / 20.05.2023 / disconnected to Robot A",
    "10:30 / 20.05.2023 / Stopped Robot A",
];

// ─── Subcomponents ───────────────────────────────────────────────────────────

function StatBlock({
    value,
    label,
}: {
    value: string;
    label: string;
}) {
    return (
        <div>
            <div className="text-white font-semibold text-base">{value}</div>
            <div className="text-white/50 text-[11px] tracking-widest uppercase mt-0.5">
                {label}
            </div>
        </div>
    );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
    return (
        <h3 className="text-white/60 text-xs font-semibold uppercase tracking-widest mb-3">
            {children}
        </h3>
    );
}

function DarkCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
    return (
        <div className={`bg-[#0f0822] rounded-xl p-4 ${className}`}>
            {children}
        </div>
    );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function AutonomousControlPage() {
    const [connected, setConnected] = useState(ROBOT.connected);

    return (
        <div className="flex h-full min-h-screen bg-[#160626]">
            {/* ── CENTER CONTENT ── */}
            <div className="flex-1 flex flex-col p-6 gap-5 overflow-y-auto">
                {/* Page title */}
                <h1 className="gradient-title text-center text-2xl">Autonomous Control</h1>

                {/* ─ Robot Info Card ─ */}
                <DarkCard>
                    {/* Robot name + disconnect */}
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-gradient-to-br from-pink-500/30 to-purple-600/30 border border-pink-500/20">
                                <Bot size={28} className="text-green-400" />
                            </div>
                            <span className="text-white text-xl font-bold">{ROBOT.name}</span>
                        </div>

                        <button
                            onClick={() => setConnected((c) => !c)}
                            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-semibold transition-all duration-200 cursor-pointer ${connected
                                    ? "bg-red-500 hover:bg-red-600 text-white"
                                    : "bg-green-600 hover:bg-green-700 text-white"
                                }`}
                        >
                            {connected ? (
                                <>
                                    <WifiOff size={14} />
                                    Disconnect
                                </>
                            ) : (
                                <>
                                    <Wifi size={14} />
                                    Connect
                                </>
                            )}
                        </button>
                    </div>

                    {/* Robot Details label */}
                    <p className="text-white/50 text-xs mb-4 uppercase tracking-widest">
                        Robot Details
                    </p>

                    {/* Stats grid */}
                    <div className="grid grid-cols-3 gap-y-5 gap-x-8">
                        <StatBlock value={ROBOT.location} label="Location" />
                        <StatBlock value={ROBOT.cleaningProgress} label="Cleaning Progress" />
                        <StatBlock value={ROBOT.floor} label="Floor" />
                        <StatBlock value={ROBOT.status} label="Status" />
                        <StatBlock value={ROBOT.waterLevel} label="Water Level" />
                        <StatBlock value={ROBOT.battery} label="Battery" />
                    </div>
                </DarkCard>

                {/* ─ Maps Row ─ */}
                <div className="grid grid-cols-2 gap-4">
                    {/* Lidar Map */}
                    <div>
                        <SectionLabel>Lidar map</SectionLabel>
                        <div className="bg-[#0f0822] rounded-xl h-44 flex items-center justify-center border border-white/5">
                            <span className="text-white/20 text-xs">No data</span>
                        </div>
                    </div>

                    {/* Path Planning */}
                    <div>
                        <SectionLabel>Path planning</SectionLabel>
                        <div className="bg-[#0f0822] rounded-xl h-44 flex items-center justify-center border border-white/5">
                            <span className="text-white/20 text-xs">No data</span>
                        </div>
                    </div>
                </div>

                {/* ─ Camera Stream ─ */}
                <div className="bg-[#0f0822] rounded-xl overflow-hidden border border-white/5 relative">
                    {/* Simulated camera feed / placeholder */}
                    <div className="w-full h-72 bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center relative">
                        {/* FPS overlay */}
                        <span className="absolute top-3 left-4 text-green-400 font-mono font-bold text-sm tracking-wider">
                            PS:30
                        </span>
                        <div className="text-white/20 text-sm flex flex-col items-center gap-2">
                            <Activity size={32} className="text-white/10" />
                            <span>Camera stream unavailable</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* ── RIGHT PANEL ── */}
            <div className="w-72 shrink-0 bg-[#1A0F28] border-l border-white/10 flex flex-col gap-5 p-5 overflow-y-auto">

                {/* Sensor Metrics */}
                <div>
                    <div className="space-y-2">
                        {SENSOR_METRICS.map(({ label, value }) => (
                            <div key={label} className="flex items-center justify-between py-1">
                                <span className="text-white/70 text-sm">{label}</span>
                                <span className="text-white font-semibold text-sm">{value}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Divider */}
                <div className="border-t border-white/10" />

                {/* Activity Log */}
                <div>
                    <SectionLabel>Activity log</SectionLabel>
                    <DarkCard className="min-h-[120px]">
                        {ACTIVITY_LOG.length === 0 ? (
                            <span className="text-white/20 text-xs">No activity yet</span>
                        ) : (
                            <ul className="space-y-1">
                                {ACTIVITY_LOG.map((entry, i) => (
                                    <li key={i} className="text-white/60 text-xs leading-relaxed">
                                        {entry}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </DarkCard>
                </div>

                {/* Error Log */}
                <div>
                    <SectionLabel>Error log</SectionLabel>
                    <DarkCard className="min-h-[100px] flex items-start gap-2">
                        <AlertTriangle size={14} className="text-white/20 mt-0.5 shrink-0" />
                        <span className="text-white/20 text-xs">No errors recorded</span>
                    </DarkCard>
                </div>
            </div>
        </div>
    );
}
