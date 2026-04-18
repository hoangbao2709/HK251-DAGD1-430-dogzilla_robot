"use client";

import { useState, type RefObject } from "react";
import { Expand, X } from "lucide-react";
import type { MapViewMode } from "../types";
import { SectionLabel } from "./Shared";

const MAP_ROTATE_STEP_DEG = 15;

type SlamViewControlsProps = {
    angle: number;
    compact?: boolean;
    onReset: () => void;
    onRotate: (deltaDeg: number) => void;
    onAutoAlign: () => void;
    onSetAngle: (angle: number) => void;
};

function SlamViewControls({
    angle,
    compact = false,
    onReset,
    onRotate,
    onAutoAlign,
    onSetAngle,
}: SlamViewControlsProps) {
    const shellClass = compact
        ? "absolute left-3 top-0 z-10 w-[min(360px,calc(100%-1.5rem))] rounded-2xl border border-white/10 bg-[#2a2e34]/88 p-3 text-white shadow-[0_18px_40px_rgba(0,0,0,0.35)] backdrop-blur-md"
        : "absolute left-4 top-4 z-10 w-[min(430px,calc(100%-2rem))] rounded-2xl border border-white/10 bg-[#2a2e34]/88 p-4 text-white shadow-[0_24px_60px_rgba(0,0,0,0.35)] backdrop-blur-md";
    const buttonClass = compact
        ? "rounded-2xl bg-[#31363d] px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-white transition hover:bg-[#3b4149]"
        : "rounded-2xl bg-[#31363d] px-4 py-3 text-sm font-bold uppercase tracking-wide text-white transition hover:bg-[#3b4149]";
    const gapClass = compact ? "grid-cols-6 gap-2" : "grid-cols-6 gap-3";
    const textClass = compact ? "mt-2 text-xs text-white/72" : "mt-3 text-sm text-white/72";

    return (
        <div className={shellClass}>
            <div className={`grid ${gapClass}`}>
                <button onClick={onReset} className={`col-span-2 ${buttonClass}`}>
                    Reset view
                </button>
                <button
                    onClick={() => onRotate(-MAP_ROTATE_STEP_DEG)}
                    className={`col-span-2 ${buttonClass}`}
                >
                    Rotate -
                </button>
                <button
                    onClick={() => onRotate(MAP_ROTATE_STEP_DEG)}
                    className={`col-span-2 ${buttonClass}`}
                >
                    Rotate +
                </button>
                <button onClick={onAutoAlign} className={`col-span-3 ${buttonClass}`}>
                    Auto align
                </button>
                <button onClick={() => onSetAngle(0)} className={`col-span-3 ${buttonClass}`}>
                    Angle 0
                </button>
            </div>
        </div>
    );
}

type MapPanelProps = {
    mapViewMode: MapViewMode;
    lidarBusy: boolean;
    lidarEnabled: boolean;
    lidarStatusReady: boolean;
    lidarCommandError: string;
    lidarFrameUrl: string;
    slamDisplayAngle: number;
    slamMapSrc: string;
    isModalOpen: boolean;
    mapImgRef: RefObject<HTMLImageElement | null>;
    overlayRef: RefObject<HTMLCanvasElement | null>;
    modalMapImgRef: RefObject<HTMLImageElement | null>;
    modalOverlayRef: RefObject<HTMLCanvasElement | null>;
    onToggleLidar: () => void;
    onSetMapViewMode: (mode: MapViewMode) => void;
    onOpenModal: () => void;
    onCloseModal: () => void;
    onResetSlamView: () => void;
    onRotateSlamView: (deltaDeg: number) => void;
    onAutoAlignSlamView: () => void;
    onSetSlamDisplayAngle: (angle: number) => void;
    drawSlamOverlay: () => void;
};

export function MapPanel({
    mapViewMode,
    lidarBusy,
    lidarEnabled,
    lidarStatusReady,
    lidarCommandError,
    lidarFrameUrl,
    slamDisplayAngle,
    slamMapSrc,
    isModalOpen,
    mapImgRef,
    overlayRef,
    modalMapImgRef,
    modalOverlayRef,
    onToggleLidar,
    onSetMapViewMode,
    onOpenModal,
    onCloseModal,
    onResetSlamView,
    onRotateSlamView,
    onAutoAlignSlamView,
    onSetSlamDisplayAngle,
    drawSlamOverlay,
}: MapPanelProps) {
    const [controlsOpen, setControlsOpen] = useState(true);
    const lidarToggleDisabled = lidarBusy || !lidarStatusReady;
    const lidarToggleLabel = !lidarStatusReady
        ? "Checking..."
        : lidarBusy
          ? lidarEnabled
              ? "Stopping..."
              : "Starting..."
          : lidarEnabled
            ? "Stop LiDAR"
            : "Start LiDAR";
    const rotatedStyle = {
        transform: `rotate(${slamDisplayAngle}deg)`,
        transformOrigin: "center center" as const,
    };

    return (
        <>
            <div className="flex h-full flex-col space-y-4">
                <div>
                    <div className="flex items-center justify-between gap-3 pb-3">
                        <SectionLabel>SLAM map overlay</SectionLabel>
                        <div className="flex flex-wrap items-center justify-end gap-2">
                            <button
                                onClick={onToggleLidar}
                                disabled={lidarToggleDisabled}
                                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
                                    lidarEnabled
                                        ? "bg-red-500 text-white hover:bg-red-400"
                                        : "bg-emerald-500 text-black hover:bg-emerald-400"
                                }`}
                            >
                                {lidarToggleLabel}
                            </button>

                            <div className="flex rounded-xl border border-[var(--border)] bg-[var(--surface)] p-1 text-xs">
                                <button
                                    onClick={() => onSetMapViewMode("lidar")}
                                    className={`rounded-lg px-3 py-1.5 transition ${
                                        mapViewMode === "lidar"
                                            ? "bg-cyan-400 font-semibold text-black"
                                            : "text-[var(--muted)]"
                                    }`}
                                >
                                    LiDAR view
                                </button>
                                <button
                                    onClick={() => onSetMapViewMode("slam")}
                                    className={`rounded-lg px-3 py-1.5 transition ${
                                        mapViewMode === "slam"
                                            ? "bg-cyan-400 font-semibold text-black"
                                            : "text-[var(--muted)]"
                                    }`}
                                >
                                    SLAM overlay
                                </button>
                            </div>

                            <button
                                onClick={onOpenModal}
                                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--foreground)] transition hover:bg-[var(--surface-2)]"
                            >
                                <Expand size={14} />
                                Phóng to
                            </button>
                        </div>
                    </div>

                    {lidarCommandError ? (
                        <p className="mb-3 text-xs text-red-300/80">{lidarCommandError}</p>
                    ) : null}

                    <div className="relative flex-1 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] min-h-[360px] xl:min-h-[560px]">
                        {mapViewMode === "slam" ? (
                            <>
                                <button
                                    onClick={() => setControlsOpen((value) => !value)}
                                    className="absolute right-3 top-3 z-20 rounded-xl border border-white/10 bg-[#2a2e34]/88 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-white shadow-[0_12px_28px_rgba(0,0,0,0.28)] backdrop-blur-md transition hover:bg-[#353b44]/92"
                                >
                                    {controlsOpen ? "Hide controls" : "Show controls"}
                                </button>
                                {controlsOpen ? (
                                    <SlamViewControls
                                        angle={slamDisplayAngle}
                                        compact
                                        onReset={onResetSlamView}
                                        onRotate={onRotateSlamView}
                                        onAutoAlign={onAutoAlignSlamView}
                                        onSetAngle={onSetSlamDisplayAngle}
                                    />
                                ) : null}
                            </>
                        ) : null}

                        {mapViewMode === "lidar" ? (
                            lidarFrameUrl ? (
                                <iframe
                                    key={lidarFrameUrl}
                                    src={lidarFrameUrl}
                                    title="LiDAR map"
                                    className="absolute inset-0 h-full w-full border-0 bg-[var(--surface-elev)]"
                                />
                            ) : (
                                <div className="absolute inset-0 flex items-center justify-center bg-[var(--surface-elev)] text-xs text-[var(--muted)]">
                                    LiDAR URL unavailable
                                </div>
                            )
                        ) : (
                            <div className="absolute inset-0" style={rotatedStyle}>
                                <img
                                    ref={mapImgRef}
                                    src={slamMapSrc}
                                    alt="SLAM map"
                                    className="h-full w-full object-contain bg-[var(--surface-elev)]"
                                    onLoad={drawSlamOverlay}
                                />
                                <canvas
                                    ref={overlayRef}
                                    className="pointer-events-none absolute left-0 top-0"
                                />
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {isModalOpen ? (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
                    onClick={onCloseModal}
                >
                    <div
                        className="relative flex h-[92vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[var(--surface)] shadow-2xl"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-5 py-4">
                            <div>
                                <div className="text-sm font-semibold text-[var(--foreground)]">
                                    SLAM map overlay
                                </div>
                                <div className="mt-1 text-xs text-[var(--muted)]">
                                    Chế độ xem phóng to để quan sát map và overlay rõ hơn
                                </div>
                            </div>
                            <button
                                onClick={onCloseModal}
                                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-elev)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] transition hover:bg-[var(--surface-2)]"
                            >
                                <X size={14} />
                                Đóng
                            </button>
                        </div>

                        <div className="flex-1 p-4">
                            <div className="relative h-full overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-elev)]">
                                {mapViewMode === "slam" ? (
                                    <>
                                        <button
                                            onClick={() => setControlsOpen((value) => !value)}
                                            className="absolute right-4 top-4 z-20 rounded-xl border border-white/10 bg-[#2a2e34]/88 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-white shadow-[0_12px_28px_rgba(0,0,0,0.28)] backdrop-blur-md transition hover:bg-[#353b44]/92"
                                        >
                                            {controlsOpen ? "Hide controls" : "Show controls"}
                                        </button>
                                        {controlsOpen ? (
                                            <SlamViewControls
                                                angle={slamDisplayAngle}
                                                onReset={onResetSlamView}
                                                onRotate={onRotateSlamView}
                                                onAutoAlign={onAutoAlignSlamView}
                                                onSetAngle={onSetSlamDisplayAngle}
                                            />
                                        ) : null}
                                    </>
                                ) : null}

                                {mapViewMode === "lidar" ? (
                                    lidarFrameUrl ? (
                                        <iframe
                                            key={`modal-${lidarFrameUrl}`}
                                            src={lidarFrameUrl}
                                            title="LiDAR map expanded"
                                            className="absolute inset-0 h-full w-full border-0 bg-[var(--surface-elev)]"
                                        />
                                    ) : (
                                        <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--muted)]">
                                            LiDAR URL unavailable
                                        </div>
                                    )
                                ) : (
                                    <div className="absolute inset-0" style={rotatedStyle}>
                                        <img
                                            ref={modalMapImgRef}
                                            src={slamMapSrc}
                                            alt="SLAM map expanded"
                                            className="h-full w-full object-contain bg-[var(--surface-elev)]"
                                            onLoad={drawSlamOverlay}
                                        />
                                        <canvas
                                            ref={modalOverlayRef}
                                            className="pointer-events-none absolute left-0 top-0"
                                        />
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            ) : null}
        </>
    );
}
