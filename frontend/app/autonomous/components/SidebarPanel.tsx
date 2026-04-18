"use client";

import { AlertTriangle } from "lucide-react";
import type { QrPositionData } from "../types";
import { DarkCard, SectionLabel, TopDownQrView } from "./Shared";

type SidebarPanelProps = {
    isDark: boolean;
    planningHeadline: string;
    poseText: string;
    qrPosition: QrPositionData | null;
    qrPositionError: string;
    slamError: string;
    qrError: string;
    obstacleText: string;
    slamConnectionText: string;
    tfConnectionText: string;
};

export function SidebarPanel({
    isDark,
    planningHeadline,
    poseText,
    qrPosition,
    qrPositionError,
    slamError,
    qrError,
    obstacleText,
    slamConnectionText,
    tfConnectionText,
}: SidebarPanelProps) {
    const sidebarShellClass = isDark
        ? "w-80 shrink-0 border-l border-white/10 bg-[linear-gradient(180deg,#0c0718_0%,#120a22_100%)] p-5"
        : "w-80 shrink-0 border-l border-[#e5dbff] bg-[linear-gradient(180deg,#fffdfd_0%,#faf7ff_100%)] p-5";
    const sidebarCardClass = isDark
        ? "rounded-[28px] border border-white/10 bg-white/[0.03] shadow-[0_20px_50px_rgba(0,0,0,0.22)]"
        : "rounded-[28px] border border-[#eadfff] bg-white/92 shadow-[0_18px_40px_rgba(86,51,163,0.08)]";
    const sidebarPlanningHeroClass = isDark
        ? "rounded-[28px] border border-cyan-400/10 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.14),transparent_42%),linear-gradient(180deg,#1a1230_0%,#10081c_100%)] p-5 shadow-[0_26px_60px_rgba(0,0,0,0.28)]"
        : "rounded-[28px] border border-[#ded1ff] bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_38%),linear-gradient(180deg,#ffffff_0%,#f9f6ff_100%)] p-5 shadow-[0_24px_48px_rgba(86,51,163,0.10)]";
    const sidebarMiniCardClass = isDark
        ? "rounded-2xl border border-white/6 bg-white/[0.04] px-3.5 py-3"
        : "rounded-2xl border border-[#efe7ff] bg-[#fcfbff] px-3.5 py-3";
    const sidebarLabelClass = isDark
        ? "text-[10px] uppercase tracking-[0.22em] text-white/45"
        : "text-[10px] uppercase tracking-[0.22em] text-[#7a69a5]";
    const sidebarValueClass = isDark
        ? "mt-2 text-sm font-semibold text-white"
        : "mt-2 text-sm font-semibold text-[#21153f]";
    const sidebarMutedClass = isDark ? "text-white/55" : "text-[#705d94]";
    const sectionTitleClass = isDark
        ? "mb-3 text-[11px] font-semibold uppercase tracking-[0.24em] text-white/72"
        : "mb-3 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#625186]";
    const planningHeadlineClass = isDark
        ? "mt-3 max-w-[15rem] text-[1.7rem] font-semibold leading-[1.1] text-white"
        : "mt-3 max-w-[15rem] text-[1.7rem] font-semibold leading-[1.1] text-[#1f1640]";
    const subtleMetaClass = isDark ? "text-xs text-white/45" : "text-xs text-[#8575ad]";

    return (
        <div className={`${sidebarShellClass} flex flex-col gap-5 overflow-y-auto`}>
            <div>
                <div className={sectionTitleClass}>Path planning</div>
                <div className="space-y-3">
                    <div className={sidebarPlanningHeroClass}>
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <div className={planningHeadlineClass}>
                                    {planningHeadline}
                                </div>
                            </div>
                        </div>

                        <div className="mt-5 grid grid-cols-1 gap-3">
                            <div className={sidebarMiniCardClass}>
                                <div className={sidebarLabelClass}>Pose</div>
                                <div className={sidebarValueClass}>{poseText}</div>
                                <div className={`mt-2 ${subtleMetaClass}`}>x, y</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div>
                <div className={sectionTitleClass}>QR detections</div>
                <DarkCard className={`p-3 ${sidebarCardClass}`}>
                    {qrPositionError && !qrPosition ? (
                        <span className={`text-xs ${sidebarMutedClass}`}>{qrPositionError}</span>
                    ) : (
                        <TopDownQrView data={qrPosition} />
                    )}
                </DarkCard>
            </div>

            <div>
                <div className={sectionTitleClass}>Issues</div>
                <DarkCard className={`flex items-start gap-2 px-4 py-4 ${sidebarCardClass}`}>
                    <AlertTriangle
                        size={14}
                        className={`mt-0.5 shrink-0 ${isDark ? "text-white/45" : "text-[#705d94]"}`}
                    />
                    <span
                        className={`min-w-0 break-words text-xs [overflow-wrap:anywhere] ${sidebarMutedClass}`}
                    >
                        {slamError || qrPositionError || qrError || "No errors recorded"}
                    </span>
                </DarkCard>
            </div>

            <div>
                <div className={sectionTitleClass}>Connection</div>
                <DarkCard
                    className={`space-y-2 px-4 py-4 text-xs ${isDark ? "text-white/70" : "text-[#4c3b73]"} ${sidebarCardClass}`}
                >
                    <div className="flex items-center justify-between">
                        <span>SLAM</span>
                        <span className={isDark ? "text-white" : "text-[#1f1640]"}>
                            {slamConnectionText}
                        </span>
                    </div>
                    <div className="flex items-center justify-between">
                        <span>TF</span>
                        <span className={isDark ? "text-white" : "text-[#1f1640]"}>
                            {tfConnectionText}
                        </span>
                    </div>
                    <div className="flex items-center justify-between">
                        <span>Obstacle</span>
                        <span className={isDark ? "text-white" : "text-[#1f1640]"}>
                            {obstacleText}
                        </span>
                    </div>
                </DarkCard>
            </div>
        </div>
    );
}
