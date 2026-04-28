"use client";

import type { PointsResponse } from "../types";
import { DarkCard, SectionLabel } from "./Shared";

type SavedPointsPanelProps = {
    isDark: boolean;
    pointNames: string[];
    savedPoints: PointsResponse;
    pointActionLoading: boolean;
    onCreatePoint: () => void;
    onStartPatrol: () => void;
    onDeleteLast: () => void;
    onClearAll: () => void;
    onGoToPoint: (name: string) => void;
    onDeletePoint: (name: string) => void;
};

export function SavedPointsPanel({
    isDark,
    pointNames,
    savedPoints,
    pointActionLoading,
    onCreatePoint,
    onStartPatrol,
    onDeleteLast,
    onClearAll,
    onGoToPoint,
    onDeletePoint,
}: SavedPointsPanelProps) {
    const savedShellClass = isDark
        ? "space-y-4 bg-[#0f0822] shadow-[0_18px_40px_rgba(124,77,255,0.08)]"
        : "space-y-4 bg-[#fffdfd] shadow-[0_18px_40px_rgba(124,77,255,0.08)]";
    const savedHeaderClass = isDark
        ? "flex flex-col gap-3 rounded-2xl border border-white/10 bg-[#201337] px-4 py-3 lg:flex-row lg:items-center lg:justify-between"
        : "flex flex-col gap-3 rounded-2xl border border-[#dacfff] bg-[#f6efff] px-4 py-3 lg:flex-row lg:items-center lg:justify-between";
    const savedEmptyClass = isDark
        ? "rounded-2xl border border-dashed border-white/10 bg-[#160a28] px-4 py-10 text-center text-sm text-white/45"
        : "rounded-2xl border border-dashed border-[#d7c4ff] bg-[#fbf7ff] px-4 py-10 text-center text-sm text-[#8d84a8]";
    const savedPointCardClass = isDark
        ? "rounded-2xl border border-white/10 bg-[#160a28] px-4 py-3 shadow-none"
        : "rounded-2xl border border-[#dacfff] bg-[#ffffff] px-4 py-3 shadow-[0_10px_24px_rgba(124,77,255,0.06)]";
    const savedStatClass = isDark
        ? "rounded-xl bg-[#241139] px-3 py-2 ring-1 ring-white/8"
        : "rounded-xl px-3 py-2 ring-1";
    const savedStatTone = {
        x: isDark ? "ring-white/8" : "ring-[#ffc3d8]",
        y: isDark ? "ring-white/8" : "ring-[#b8e9ff]",
        yaw: isDark ? "ring-white/8" : "ring-[#b5efc4]",
    };
    const savedStatFill = isDark ? "bg-[#241139]" : "";
    const savedButtonClass =
        "flex-1 rounded-full bg-[#10b981] px-3 py-2 text-xs font-semibold text-white";

    return (
        <DarkCard className={savedShellClass}>
            <div className={savedHeaderClass}>
                <SectionLabel>Saved points</SectionLabel>
                <div className="flex flex-wrap gap-2">
                    <button
                        onClick={onCreatePoint}
                        disabled={pointActionLoading}
                        className="cursor-pointer rounded-full bg-[#10b981] px-4 py-2 text-sm font-semibold text-white shadow-[0_10px_20px_rgba(11,183,111,0.22)] transition hover:bg-[#0ea56f] disabled:opacity-50"
                    >
                        Save point
                    </button>
                    <button
                        onClick={onStartPatrol}
                        disabled={pointActionLoading || pointNames.length === 0}
                        className="cursor-pointer rounded-full bg-[#2563eb] px-4 py-2 text-sm font-semibold text-white shadow-[0_10px_20px_rgba(37,99,235,0.18)] transition hover:bg-[#1d4ed8] disabled:opacity-50"
                    >
                        Patrol all
                    </button>
                    <button
                        onClick={onDeleteLast}
                        disabled={pointActionLoading || pointNames.length === 0}
                        className="cursor-pointer rounded-full bg-[#ff5574] px-4 py-2 text-sm font-semibold text-white shadow-[0_10px_20px_rgba(255,59,87,0.18)] transition hover:bg-[#f43f5e] disabled:opacity-50"
                    >
                        Delete last
                    </button>
                    <button
                        onClick={onClearAll}
                        disabled={pointActionLoading || pointNames.length === 0}
                        className="cursor-pointer rounded-full bg-[#f6c94c] px-4 py-2 text-sm font-semibold text-[#4a3200] shadow-[0_10px_20px_rgba(255,191,31,0.16)] transition hover:bg-[#eab308] disabled:opacity-50"
                    >
                        Clear all
                    </button>
                </div>
            </div>

            {pointNames.length === 0 ? (
                <div className={savedEmptyClass}>No saved points</div>
            ) : (
                <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
                    {pointNames.map((name) => {
                        const point = savedPoints[name];

                        return (
                            <div key={name} className={savedPointCardClass}>
                                <div className="space-y-4">
                                    <div className={isDark ? "text-lg font-semibold text-white" : "text-lg font-semibold text-[#24163f]"}>
                                        {name}
                                    </div>

                                    <div className="grid grid-cols-3 gap-3 text-xs text-[var(--muted)]">
                                        <div className={`${savedStatClass} ${savedStatFill} ${savedStatTone.x}`}>
                                            <div className="text-[10px] uppercase tracking-widest text-[var(--muted-2)]">
                                                X
                                            </div>
                                            <div className={isDark ? "mt-1 text-sm font-semibold text-white" : "mt-1 text-sm font-semibold text-[#1f1640]"}>
                                                {Number(point.x).toFixed(3)}
                                            </div>
                                        </div>
                                        <div className={`${savedStatClass} ${savedStatFill} ${savedStatTone.y}`}>
                                            <div className="text-[10px] uppercase tracking-widest text-[var(--muted-2)]">
                                                Y
                                            </div>
                                            <div className={isDark ? "mt-1 text-sm font-semibold text-white" : "mt-1 text-sm font-semibold text-[#1f1640]"}>
                                                {Number(point.y).toFixed(3)}
                                            </div>
                                        </div>
                                        <div className={`${savedStatClass} ${savedStatFill} ${savedStatTone.yaw}`}>
                                            <div className="text-[10px] uppercase tracking-widest text-[var(--muted-2)]">
                                                Yaw
                                            </div>
                                            <div className={isDark ? "mt-1 text-sm font-semibold text-white" : "mt-1 text-sm font-semibold text-[#1f1640]"}>
                                                {Number(point.yaw || 0).toFixed(3)}
                                            </div>
                                        </div>
                                    </div>

                                    <div className="flex gap-2">
                                        <button onClick={() => onGoToPoint(name)}
                                            disabled={pointActionLoading}
                                            className={`cursor-pointer ${savedButtonClass}`}
                                        >
                                            Go to
                                        </button>
                                        <button onClick={() => onDeletePoint(name)}
                                            disabled={pointActionLoading}
                                            className="cursor-pointer flex-1 rounded-full bg-[#ff5574] px-3 py-2 text-xs font-semibold text-white shadow-[0_8px_18px_rgba(255,55,88,0.16)] transition hover:bg-[#f43f5e] disabled:opacity-50"
                                        >
                                            Delete
                                        </button>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </DarkCard>
    );
}
