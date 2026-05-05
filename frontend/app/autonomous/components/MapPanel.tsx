"use client";

import { useEffect, useState, type MouseEvent, type RefObject } from "react";
import { Expand, X } from "lucide-react";
import { SectionLabel } from "./Shared";
import type { MapMode, NavPlacementMode } from "../types";

type MapPanelProps = {
  mapMode: MapMode;
  slamDisplayAngle: number;
  slamMapSrc: string;
  lidarUrl: string;
  lidarActive: boolean;
  lidarBusy: boolean;
  lidarControlError: string | null;
  isModalOpen: boolean;
  navPlacementMode: NavPlacementMode;
  hasPendingPlacement: boolean;
  showRobot: boolean;
  showPath: boolean;
  showGrid: boolean;
  mapImgRef: RefObject<HTMLImageElement | null>;
  overlayRef: RefObject<HTMLCanvasElement | null>;
  modalMapImgRef: RefObject<HTMLImageElement | null>;
  modalOverlayRef: RefObject<HTMLCanvasElement | null>;
  onSetMapMode: (mode: MapMode) => void;
  onOpenModal: () => void;
  onCloseModal: () => void;
  onSetNavPlacementMode: (mode: NavPlacementMode) => void;
  onCancelPlacement: () => void;
  onClearPath: () => void;
  onToggleLidar: () => void;
  onStartStatic: () => void;
  onToggleRobot: () => void;
  onTogglePath: () => void;
  onToggleGrid: () => void;
  onResetView: () => void;
  onRotateLeft: () => void;
  onRotateRight: () => void;
  onSlamImageClick: (
    event: MouseEvent<HTMLImageElement>,
    isModal: boolean
  ) => void;
  drawSlamOverlay: () => void;
};

export function MapPanel({
  mapMode,
  slamDisplayAngle,
  slamMapSrc,
  lidarUrl,
  lidarActive,
  lidarBusy,
  lidarControlError,
  isModalOpen,
  navPlacementMode,
  hasPendingPlacement,
  mapImgRef,
  overlayRef,
  modalMapImgRef,
  modalOverlayRef,
  onSetMapMode,
  onOpenModal,
  onCloseModal,
  onSetNavPlacementMode,
  onCancelPlacement,
  onClearPath,
  onToggleLidar,
  onStartStatic,
  onSlamImageClick,
  drawSlamOverlay,
}: MapPanelProps) {
  const [lidarError, setLidarError] = useState<string | null>(null);
  const [lidarFrameLoaded, setLidarFrameLoaded] = useState(false);

  useEffect(() => {
    const id = window.requestAnimationFrame(() => {
      drawSlamOverlay();
    });
    return () => window.cancelAnimationFrame(id);
  }, [slamMapSrc, mapMode, navPlacementMode, hasPendingPlacement, drawSlamOverlay]);

  useEffect(() => {
    setLidarFrameLoaded(false);
    setLidarError(null);
  }, [lidarUrl, lidarActive, mapMode]);

  const handleImageClick = (
    event: MouseEvent<HTMLImageElement>,
    isModal: boolean
  ) => {
    if (mapMode !== "navigate") return;
    onSlamImageClick(event, isModal);
  };

  const lidarStatus = lidarError
    ? "LiDAR error"
    : lidarControlError
      ? "LiDAR error"
    : lidarActive
      ? lidarFrameLoaded
        ? "Live"
        : "Loading..."
      : "Offline";
  const lidarButtonLabel = lidarBusy
    ? lidarActive
      ? "Stopping LiDAR..."
      : "Starting LiDAR..."
    : lidarActive
      ? "Stop Lidar"
      : "Start Lidar";
  const lidarMessage = lidarError || lidarControlError;

  return (
    <>
      <div className="flex h-full flex-col space-y-4">
        <div>
          <div className="flex items-center justify-between gap-3 pb-3">
            <SectionLabel>SLAM map overlay</SectionLabel>

            <div className="flex flex-wrap items-center justify-end gap-2">
              <div className="flex rounded-xl border border-[var(--border)] bg-[var(--surface)] p-1 text-xs">
                <button onClick={() => onSetMapMode("view")}
                  className={`cursor-pointer rounded-lg px-3 py-1.5 transition ${
                    mapMode === "view"
                      ? "bg-cyan-400 font-semibold text-black"
                      : "text-[var(--muted)]"
                  }`}
                >
                  View
                </button>

                <button onClick={() => onSetMapMode("navigate")}
                  className={`cursor-pointer rounded-lg px-3 py-1.5 transition ${
                    mapMode === "navigate"
                      ? "bg-cyan-400 font-semibold text-black"
                      : "text-[var(--muted)]"
                  }`}
                >
                  Navigate
                </button>
              </div>

              <button
                onClick={onToggleLidar}
                disabled={lidarBusy}
                className={`cursor-pointer rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:cursor-wait disabled:opacity-60 ${
                  lidarActive
                    ? "bg-emerald-500 text-black hover:bg-emerald-400"
                    : "border border-[var(--border)] bg-[var(--surface)] text-[var(--foreground)] hover:bg-[var(--surface-2)]"
                }`}
              >
                {lidarButtonLabel}
              </button>
              <button
                onClick={onStartStatic}
                disabled={lidarBusy}
                className="flex cursor-pointer items-center justify-center gap-2 rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
              >
                Start static
              </button>
              <button
                onClick={onOpenModal}
                className="cursor-pointer inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--foreground)] transition hover:bg-[var(--surface-2)]"
              >
                <Expand size={14} />
                Expand
              </button>
            </div>
          </div>

          {mapMode === "navigate" ? (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <button onClick={() => onSetNavPlacementMode("goal")}
                className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-semibold ${
                  navPlacementMode === "goal"
                    ? "bg-emerald-500 text-black"
                    : "bg-[var(--surface)] text-[var(--foreground)]"
                }`}
              >
                Set goal
              </button>

              <button onClick={() => onSetNavPlacementMode("initialPose")}
                className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-semibold ${
                  navPlacementMode === "initialPose"
                    ? "bg-amber-400 text-black"
                    : "bg-[var(--surface)] text-[var(--foreground)]"
                }`}
              >
                Set initial pose
              </button>

              <button
                onClick={onClearPath}
                className="cursor-pointer rounded-lg bg-red-500 px-3 py-2 text-xs font-semibold text-white"
              >
                Stop & clear
              </button>

              {hasPendingPlacement ? (
                <button
                  onClick={onCancelPlacement}
                  className="cursor-pointer rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs font-semibold text-[var(--foreground)]"
                >
                  Cancel placing
                </button>
              ) : null}
            </div>
          ) : (
            <div className="mb-3 flex items-center gap-2 text-xs text-[var(--muted)]"/>
          )}

          <div className="relative min-h-[360px] overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] xl:min-h-[560px]">
            <div className="absolute left-3 top-3 z-10 rounded-lg bg-black/45 px-2 py-1 text-[11px] font-medium text-white backdrop-blur-sm">
              Display angle: {Number.isFinite(slamDisplayAngle) ? slamDisplayAngle.toFixed(1) : "0.0"}°
            </div>

            <div className="absolute inset-0">
              <img
                ref={mapImgRef}
                src={slamMapSrc}
                alt="SLAM map"
                className={`h-full w-full object-contain bg-[var(--surface-elev)] ${
                  mapMode === "navigate" ? "cursor-crosshair" : "cursor-default"
                }`}
                onLoad={drawSlamOverlay}
                onClick={(event: MouseEvent<HTMLImageElement>) =>
                  handleImageClick(event, false)
                }
              />
              <canvas
                ref={overlayRef}
                className="pointer-events-none absolute left-0 top-0"
              />
            </div>

            {mapMode === "view" ? (
              <>
                {lidarActive && lidarUrl ? (
                  <iframe
                    src={lidarUrl}
                    title="LiDAR map"
                    className={`absolute inset-0 w-full h-full border-0 transition-opacity duration-300 ${
                      lidarFrameLoaded ? "opacity-100" : "opacity-0"
                    }`}
                    onLoad={() => {
                      setLidarFrameLoaded(true);
                      setLidarError(null);
                    }}
                  />
                ) : null}

                <div
                  className={`absolute inset-0 flex items-center justify-center text-xs transition-opacity duration-300 ${
                    lidarActive && lidarFrameLoaded
                      ? "opacity-0 pointer-events-none"
                      : "opacity-100"
                  }`}
                >
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-center text-[var(--foreground)]/70">
                    {lidarMessage
                      ? `LiDAR error: ${lidarMessage}`
                      : lidarActive
                        ? "Waiting for LiDAR stream..."
                        : "LiDAR is currently off"}
                  </div>
                </div>
              </>
            ) : null}
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
                  {mapMode === "view"
                    ? "View mode: chỉ quan sát"
                    : "Navigate mode: click chọn goal hoặc initial pose"}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={onToggleLidar}
                  disabled={lidarBusy}
                  className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-semibold transition disabled:cursor-wait disabled:opacity-60 ${
                    lidarActive
                      ? "bg-emerald-500 text-black hover:bg-emerald-400"
                      : "border border-[var(--border)] bg-[var(--surface-elev)] text-[var(--foreground)] hover:bg-[var(--surface-2)]"
                  }`}
                >
                  {lidarButtonLabel}
                </button>

                <button
                  onClick={onCloseModal}
                  className="cursor-pointer inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-elev)] px-3 py-2 text-xs font-semibold text-[var(--foreground)] transition hover:bg-[var(--surface-2)]"
                >
                  <X size={14} />
                  Close
                </button>
              </div>
            </div>

            <div className="flex-1 p-4">
              <div className="relative h-full overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-elev)]">
                <img
                  ref={modalMapImgRef}
                  src={slamMapSrc}
                  alt="SLAM map expanded"
                  className={`h-full w-full object-contain bg-[var(--surface-elev)] ${
                    mapMode === "navigate" ? "cursor-crosshair" : "cursor-default"
                  }`}
                  onLoad={drawSlamOverlay}
                  onClick={(event: MouseEvent<HTMLImageElement>) =>
                    handleImageClick(event, true)
                  }
                />
                <canvas
                  ref={modalOverlayRef}
                  className="pointer-events-none absolute left-0 top-0"
                />

                {mapMode === "view" ? (
                  <>
                    {lidarActive && lidarUrl ? (
                      <iframe
                        src={lidarUrl}
                        title="LiDAR map"
                        className={`absolute inset-0 w-full h-full border-0 transition-opacity duration-300 ${
                          lidarFrameLoaded ? "opacity-100" : "opacity-0"
                        }`}
                        onLoad={() => {
                          setLidarFrameLoaded(true);
                          setLidarError(null);
                        }}
                      />
                    ) : null}

                    <div
                      className={`absolute inset-0 flex items-center justify-center text-xs transition-opacity duration-300 ${
                        lidarActive && lidarFrameLoaded
                          ? "opacity-0 pointer-events-none"
                          : "opacity-100"
                      }`}
                    >
                      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-center text-[var(--foreground)]/70">
                        {lidarMessage
                          ? `LiDAR error: ${lidarMessage}`
                          : lidarActive
                            ? "Waiting for LiDAR stream..."
                            : "LiDAR is currently off"}
                      </div>
                    </div>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
