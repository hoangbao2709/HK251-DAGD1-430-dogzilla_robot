"use client";

import {
  useEffect,
  useRef,
  useState,
  type MouseEvent,
  type RefObject,
} from "react";
import {
  Crosshair,
  Download,
  Expand,
  Eye,
  Grid3X3,
  Map as MapIcon,
  Navigation,
  RotateCcw,
  RotateCw,
  SlidersHorizontal,
  Upload,
  X,
} from "lucide-react";
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
  mapActionMessage: string;
  isModalOpen: boolean;
  navPlacementMode: NavPlacementMode;
  hasPendingPlacement: boolean;
  showRobot: boolean;
  showPath: boolean;
  showScan: boolean;
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
  onToggleRobot: () => void;
  onTogglePath: () => void;
  onToggleScan: () => void;
  onToggleGrid: () => void;
  onResetView: () => void;
  onRotateLeft: () => void;
  onRotateRight: () => void;
  onSaveMap: () => void;
  onLoadMap: (file: File) => void;
  onUseLiveMap: () => void;
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
  mapActionMessage,
  isModalOpen,
  navPlacementMode,
  hasPendingPlacement,
  showRobot,
  showPath,
  showScan,
  showGrid,
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
  onToggleRobot,
  onTogglePath,
  onToggleScan,
  onToggleGrid,
  onResetView,
  onRotateLeft,
  onRotateRight,
  onSaveMap,
  onLoadMap,
  onUseLiveMap,
  onSlamImageClick,
  drawSlamOverlay,
}: MapPanelProps) {
  const [lidarError, setLidarError] = useState<string | null>(null);
  const [controlsOpen, setControlsOpen] = useState(true);
  const controlsRef = useRef<HTMLDivElement | null>(null);
  const modalControlsRef = useRef<HTMLDivElement | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const id = window.requestAnimationFrame(() => {
      drawSlamOverlay();
    });
    return () => window.cancelAnimationFrame(id);
  }, [
    slamMapSrc,
    mapMode,
    navPlacementMode,
    hasPendingPlacement,
    slamDisplayAngle,
    drawSlamOverlay,
  ]);

  useEffect(() => {
    setLidarError(null);
  }, [lidarUrl, lidarActive, mapMode]);

  useEffect(() => {
    if (!controlsOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        (controlsRef.current?.contains(target) ||
          modalControlsRef.current?.contains(target))
      ) {
        return;
      }
      setControlsOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setControlsOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [controlsOpen]);

  const handleImageClick = (
    event: MouseEvent<HTMLImageElement>,
    isModal: boolean
  ) => {
    if (mapMode !== "navigate") return;
    onSlamImageClick(event, isModal);
  };

  const handleUpload = (file: File | undefined) => {
    if (!file) return;
    onLoadMap(file);
    if (uploadInputRef.current) {
      uploadInputRef.current.value = "";
    }
  };

  const lidarStatus =
    lidarError || lidarControlError
      ? "LiDAR error"
      : lidarActive
        ? "LiDAR active"
        : "LiDAR offline";
  const lidarButtonLabel = lidarBusy
    ? lidarActive
      ? "Stopping LiDAR..."
      : "Starting LiDAR..."
    : lidarActive
      ? "Stop Lidar"
      : "Start Lidar";
  const lidarMessage = lidarError || lidarControlError;
  const isNavigateMode = mapMode === "navigate";
  const modeText =
    mapMode === "view"
      ? "VIEW"
      : navPlacementMode === "goal"
        ? hasPendingPlacement
          ? "NAV: choose heading"
          : "NAV: choose goal"
        : hasPendingPlacement
          ? "INIT: choose heading"
          : "INIT: choose pose";
  const panelButtonClass =
    "cursor-pointer rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white transition hover:bg-white/15";
  const navActionClass =
    "cursor-pointer rounded-lg px-3 py-2 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-45";
  const toggleClass = (active: boolean) =>
    `cursor-pointer rounded-lg px-3 py-2 text-xs font-bold transition ${active
      ? "bg-[#3b9df6] text-white shadow-inner"
      : "bg-white/10 text-white hover:bg-white/15"
    }`;

  const renderMapStage = (
    imageRef: RefObject<HTMLImageElement | null>,
    canvasRef: RefObject<HTMLCanvasElement | null>,
    isModalMap: boolean
  ) => (
    <div
      className={`absolute inset-0 overflow-hidden ${mapMode === "navigate" ? "cursor-crosshair" : "cursor-default"
        }`}
    >
      <div
        className="absolute inset-0 transition-transform duration-150"
        style={{ transform: `rotate(${slamDisplayAngle}deg)` }}
      >
        <img
          ref={imageRef}
          src={slamMapSrc}
          alt={isModalMap ? "SLAM map expanded" : "SLAM map"}
          className="absolute inset-0 h-full w-full select-none bg-[#1f2222] object-contain [image-rendering:pixelated]"
          draggable={false}
          onLoad={drawSlamOverlay}
          onMouseDown={(event: MouseEvent<HTMLImageElement>) =>
            handleImageClick(event, isModalMap)
          }
        />
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
        />
      </div>
    </div>
  );

  const renderOptionsOverlay = (rootRef: RefObject<HTMLDivElement | null>) => (
    <div ref={rootRef} className="absolute left-4 top-4 z-20">
      {controlsOpen ? (
        <aside className="w-[300px] rounded-2xl border border-white/10 bg-[#1d1f20]/90 p-4 shadow-2xl backdrop-blur">
          <div className="mb-4 flex items-center justify-between gap-3">
            <SectionLabel>Options</SectionLabel>
            <button
              onClick={() => setControlsOpen(false)}
              className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg bg-white/10 text-white transition hover:bg-white/15"
              aria-label="Close map controls"
            >
              <X size={16} />
            </button>
          </div>

          <div className="space-y-3">
            <section className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <div className="mb-3 flex items-center gap-2">
                <button
                  onClick={onToggleLidar}
                  disabled={lidarBusy}
                  className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-bold transition disabled:cursor-wait disabled:opacity-60 ${lidarActive
                    ? "bg-emerald-500 text-black hover:bg-emerald-400"
                    : "bg-white/10 text-white hover:bg-white/15"
                    }`}
                >
                  {lidarButtonLabel}
                </button>
                <span className="rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white/70">
                  {lidarStatus}
                </span>
              </div>

              <div className="mb-3 grid w-full grid-cols-2 gap-1 rounded-2xl border border-white/10 bg-white/5 p-1 shadow-inner backdrop-blur">
                <button
                  onClick={() => onSetMapMode("view")}
                  className={`flex cursor-pointer items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-bold transition-all duration-200 ${mapMode === "view"
                    ? "scale-[1.02] bg-[#3b9df6] text-white shadow-[0_8px_24px_rgba(59,157,246,0.35)]"
                    : "text-white/70 hover:bg-white/10 hover:text-white"
                    }`}
                >
                  <Eye size={14} />
                  View
                </button>

                <button
                  onClick={() => onSetMapMode("navigate")}
                  className={`flex cursor-pointer items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-bold transition-all duration-200 ${mapMode === "navigate"
                    ? "scale-[1.02] bg-[#3b9df6] text-white shadow-[0_8px_24px_rgba(59,157,246,0.35)]"
                    : "text-white/70 hover:bg-white/10 hover:text-white"
                    }`}
                >
                  <Navigation size={14} />
                  Nav
                </button>
              </div>

              {isNavigateMode ? (
                <div className="mb-3 grid grid-cols-3 gap-3">
                  <button
                    onClick={() => onSetNavPlacementMode("goal")}
                    className={`${navActionClass} w-full ${navPlacementMode === "goal"
                      ? "bg-emerald-500 text-black"
                      : "bg-white/10 text-white"
                      }`}
                  >
                    Set goal
                  </button>

                  <button
                    onClick={() => onSetNavPlacementMode("initialPose")}
                    className={`${navActionClass} w-full ${navPlacementMode === "initialPose"
                      ? "bg-amber-400 text-black"
                      : "bg-white/10 text-white"
                      }`}
                  >
                    Initial pose
                  </button>

                  <button
                    onClick={onClearPath}
                    className="w-full cursor-pointer rounded-lg bg-red-500 px-3 py-2 text-xs font-bold text-white transition hover:bg-red-600"
                  >
                    Stop & clear
                  </button>
                </div>
              ) : null}

              {!isNavigateMode ? (
                <div className="grid grid-cols-2 gap-2 text-xs text-white/80">
                  <button
                    onClick={onToggleRobot}
                    className={toggleClass(showRobot)}
                  >
                    Robot
                  </button>
                  <button
                    onClick={onTogglePath}
                    className={toggleClass(showPath)}
                  >
                    Path
                  </button>
                  <button
                    onClick={onToggleScan}
                    className={toggleClass(showScan)}
                  >
                    Scan
                  </button>
                  <button
                    onClick={onToggleGrid}
                    className={toggleClass(showGrid)}
                  >
                    Grid
                  </button>
                </div>
              ) : null}
            </section>

            {!isNavigateMode ? (
              <section className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={onSaveMap}
                    className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-[#2d93ea] px-3 py-2 text-xs font-bold text-white transition hover:bg-[#2385d8]"
                  >
                    <Download size={14} />
                    Save map
                  </button>
                  <button
                    onClick={() => uploadInputRef.current?.click()}
                    className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-[#2d93ea] px-3 py-2 text-xs font-bold text-white transition hover:bg-[#2385d8]"
                  >
                    <Upload size={14} />
                    Load map
                  </button>
                  <input
                    ref={uploadInputRef}
                    type="file"
                    accept=".zip,.yaml,.yml,.pgm,.png,.jpg,.jpeg"
                    className="hidden"
                    onChange={(event) => handleUpload(event.target.files?.[0])}
                  />
                </div>

                <div className="mt-2 grid grid-cols-3 gap-2">
                  <button onClick={onResetView} className={panelButtonClass}>
                    Reset view
                  </button>
                  <button
                    onClick={onRotateLeft}
                    className="inline-flex cursor-pointer items-center justify-center gap-1 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white transition hover:bg-white/15"
                  >
                    <RotateCcw size={14} />
                    Rotate -
                  </button>
                  <button
                    onClick={onRotateRight}
                    className="inline-flex cursor-pointer items-center justify-center gap-1 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white transition hover:bg-white/15"
                  >
                    <RotateCw size={14} />
                    Rotate +
                  </button>
                </div>

                <div className="mt-2 grid grid-cols-2 gap-2">
                  <button
                    onClick={onCancelPlacement}
                    disabled={!hasPendingPlacement}
                    className={`${panelButtonClass} disabled:cursor-not-allowed disabled:opacity-45`}
                  >
                    Cancel placing
                  </button>
                  <button
                    onClick={onUseLiveMap}
                    className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white transition hover:bg-white/15"
                  >
                    <MapIcon size={14} />
                    Live map
                  </button>
                </div>

                <div className="mt-3 text-xs text-white/65">
                  Display angle:{" "}
                  {Number.isFinite(slamDisplayAngle)
                    ? slamDisplayAngle.toFixed(1)
                    : "0.0"}{" "}
                  deg
                </div>
              </section>
            ) : null}
          </div>
        </aside>
      ) : (
        <button
          onClick={() => setControlsOpen(true)}
          className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-black/45 px-3 py-2 text-xs font-bold text-white shadow-xl backdrop-blur transition hover:bg-black/55"
        >
          <SlidersHorizontal size={14} />
          Options
        </button>
      )}
    </div>
  );

  return (
    <>
      <div className="relative h-[520px] overflow-hidden rounded-xl border border-white/10 bg-[#1f2222] text-[#eef3f2] shadow-2xl xl:h-[640px]">
        {renderMapStage(mapImgRef, overlayRef, false)}
  
        <div ref={controlsRef} className="absolute left-4 top-4 z-20">
          {controlsOpen ? (
            <aside className="w-[300px] rounded-2xl border border-white/10 bg-[#1d1f20]/90 p-4 shadow-2xl backdrop-blur">
              <div className="mb-4 flex items-center justify-between gap-3">
                <SectionLabel>Options</SectionLabel>
                <button
                  onClick={() => setControlsOpen(false)}
                  className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg bg-white/10 text-white transition hover:bg-white/15"
                  aria-label="Close map controls"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="space-y-3">
                <section className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                  <div className="mb-3 flex items-center gap-2">
                    <button
                      onClick={onToggleLidar}
                      disabled={lidarBusy}
                      className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-bold transition disabled:cursor-wait disabled:opacity-60 ${lidarActive
                        ? "bg-emerald-500 text-black hover:bg-emerald-400"
                        : "bg-white/10 text-white hover:bg-white/15"
                        }`}
                    >
                      {lidarButtonLabel}
                    </button>
                    <span className="rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white/70">
                      {lidarStatus}
                    </span>
                  </div>

                  <div className="mb-3 grid w-full grid-cols-2 gap-1 rounded-2xl border border-white/10 bg-white/5 p-1 shadow-inner backdrop-blur">
                    <button
                      onClick={() => onSetMapMode("view")}
                      className={`flex cursor-pointer items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-bold transition-all duration-200 ${mapMode === "view"
                          ? "bg-[#3b9df6] text-white shadow-[0_8px_24px_rgba(59,157,246,0.35)] scale-[1.02]"
                          : "text-white/70 hover:bg-white/10 hover:text-white"
                        }`}
                    >
                      <Eye size={14} />
                      View
                    </button>

                    <button
                      onClick={() => onSetMapMode("navigate")}
                      className={`flex cursor-pointer items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-bold transition-all duration-200 ${mapMode === "navigate"
                          ? "bg-[#3b9df6] text-white shadow-[0_8px_24px_rgba(59,157,246,0.35)] scale-[1.02]"
                          : "text-white/70 hover:bg-white/10 hover:text-white"
                        }`}
                    >
                      <Navigation size={14} />
                      Nav
                    </button>
                  </div>

                  {isNavigateMode ? (
                    <div className="mb-3 grid grid-cols-3 gap-3">
                      <button
                        onClick={() => onSetNavPlacementMode("goal")}
                        className={`${navActionClass} w-full ${navPlacementMode === "goal"
                          ? "bg-emerald-500 text-black"
                          : "bg-white/10 text-white"
                          }`}
                      >
                        Set goal
                      </button>

                      <button
                        onClick={() => onSetNavPlacementMode("initialPose")}
                        className={`${navActionClass} w-full ${navPlacementMode === "initialPose"
                          ? "bg-amber-400 text-black"
                          : "bg-white/10 text-white"
                          }`}
                      >
                        Initial pose
                      </button>

                      <button
                        onClick={onClearPath}
                        className="w-full cursor-pointer rounded-lg bg-red-500 px-3 py-2 text-xs font-bold text-white transition hover:bg-red-600"
                      >
                        Stop & clear
                      </button>
                    </div>
                  ) : null}

                  {!isNavigateMode ? (
                    <div className="grid grid-cols-2 gap-2 text-xs text-white/80">
                      <button
                        onClick={onToggleRobot}
                        className={toggleClass(showRobot)}
                      >
                        Robot
                      </button>
                      <button
                        onClick={onTogglePath}
                        className={toggleClass(showPath)}
                      >
                        Path
                      </button>
                      <button
                        onClick={onToggleScan}
                        className={toggleClass(showScan)}
                      >
                        Scan
                      </button>
                      <button
                        onClick={onToggleGrid}
                        className={toggleClass(showGrid)}
                      >
                        Grid
                      </button>
                    </div>
                  ) : null}
                </section>

                {!isNavigateMode ? (
                  <section className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={onSaveMap}
                        className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-[#2d93ea] px-3 py-2 text-xs font-bold text-white transition hover:bg-[#2385d8]"
                      >
                        <Download size={14} />
                        Save map
                      </button>
                      <button
                        onClick={() => uploadInputRef.current?.click()}
                        className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-[#2d93ea] px-3 py-2 text-xs font-bold text-white transition hover:bg-[#2385d8]"
                      >
                        <Upload size={14} />
                        Load map
                      </button>
                      <input
                        ref={uploadInputRef}
                        type="file"
                        accept=".zip,.yaml,.yml,.pgm,.png,.jpg,.jpeg"
                        className="hidden"
                        onChange={(event) => handleUpload(event.target.files?.[0])}
                      />
                    </div>

                    <div className="mt-2 grid grid-cols-3 gap-2">
                      <button onClick={onResetView} className={panelButtonClass}>
                        Reset view
                      </button>
                      <button
                        onClick={onRotateLeft}
                        className="inline-flex cursor-pointer items-center justify-center gap-1 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white transition hover:bg-white/15"
                      >
                        <RotateCcw size={14} />
                        Rotate -
                      </button>
                      <button
                        onClick={onRotateRight}
                        className="inline-flex cursor-pointer items-center justify-center gap-1 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white transition hover:bg-white/15"
                      >
                        <RotateCw size={14} />
                        Rotate +
                      </button>
                    </div>

                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <button
                        onClick={onCancelPlacement}
                        disabled={!hasPendingPlacement}
                        className={`${panelButtonClass} disabled:cursor-not-allowed disabled:opacity-45`}
                      >
                        Cancel placing
                      </button>
                      <button
                        onClick={onUseLiveMap}
                        className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white transition hover:bg-white/15"
                      >
                        <MapIcon size={14} />
                        Live map
                      </button>
                    </div>

                    <div className="mt-3 text-xs text-white/65">
                      Display angle:{" "}
                      {Number.isFinite(slamDisplayAngle)
                        ? slamDisplayAngle.toFixed(1)
                        : "0.0"}{" "}
                      deg
                    </div>
                  </section>
                ) : null}
              </div>
            </aside>
          ) : (
            <button
              onClick={() => setControlsOpen(true)}
              className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-black/45 px-3 py-2 text-xs font-bold text-white shadow-xl backdrop-blur transition hover:bg-black/55"
            >
              <SlidersHorizontal size={14} />
              Options
            </button>
          )}
        </div>

        <div className="absolute right-4 top-4 z-20 flex flex-wrap justify-end gap-2">
          <button
            onClick={onOpenModal}
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-black/45 px-3 py-2 text-xs font-bold text-white backdrop-blur transition hover:bg-black/55"
          >
            <Expand size={14} />
            Expand
          </button>
          <a
            href="/robot-map"
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-black/45 px-3 py-2 text-xs font-bold text-white backdrop-blur transition hover:bg-black/55"
          >
            <MapIcon size={14} />
            Map UI
          </a>
        </div>

        <div className="absolute bottom-4 left-4 z-20 flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-2 rounded-full bg-black/45 px-3 py-2 font-bold text-white backdrop-blur">
            <Crosshair size={14} />
            {mapActionMessage || modeText}
          </span>
          <span className="inline-flex items-center gap-2 rounded-full bg-black/45 px-3 py-2 font-bold text-white/75 backdrop-blur">
            <Grid3X3 size={14} />
            {showGrid ? "grid on" : "grid off"}
          </span>
          {lidarMessage ? (
            <span className="inline-flex rounded-full bg-red-500/90 px-3 py-2 font-bold text-white backdrop-blur">
              {lidarMessage}
            </span>
          ) : null}
        </div>

        {hasPendingPlacement ? (
          <button
            onClick={onCancelPlacement}
            className="absolute bottom-4 right-4 z-20 inline-flex cursor-pointer items-center gap-2 rounded-full bg-red-500 px-4 py-3 text-xs font-bold text-white shadow-xl transition hover:bg-red-600"
          >
            <X size={14} />
            Cancel placing
          </button>
        ) : null}
      </div>

      {isModalOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
          onClick={onCloseModal}
        >
          <div
            className="relative flex h-[92vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#1f2222] text-[#eef3f2] shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
              <div>
                <div className="text-sm font-bold text-white">
                  SLAM map overlay
                </div>
                <div className="mt-1 text-xs text-white/65">
                  {mapActionMessage || modeText}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={onToggleLidar}
                  disabled={lidarBusy}
                  className={`cursor-pointer rounded-lg px-3 py-2 text-xs font-bold transition disabled:cursor-wait disabled:opacity-60 ${lidarActive
                    ? "bg-emerald-500 text-black hover:bg-emerald-400"
                    : "bg-white/10 text-white hover:bg-white/15"
                    }`}
                >
                  {lidarButtonLabel}
                </button>

                <button
                  onClick={onCloseModal}
                  className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white transition hover:bg-white/15"
                >
                  <X size={14} />
                  Close
                </button>
              </div>
            </div>

            <div className="relative flex-1 overflow-hidden">
              {renderMapStage(modalMapImgRef, modalOverlayRef, true)}
              {renderOptionsOverlay(modalControlsRef)}

              <div className="absolute bottom-4 left-4 z-20 flex flex-wrap items-center gap-2 text-xs">
                <span className="inline-flex items-center gap-2 rounded-full bg-black/45 px-3 py-2 font-bold text-white backdrop-blur">
                  <Crosshair size={14} />
                  {mapActionMessage || modeText}
                </span>
                <span className="inline-flex items-center gap-2 rounded-full bg-black/45 px-3 py-2 font-bold text-white/75 backdrop-blur">
                  <Grid3X3 size={14} />
                  angle{" "}
                  {Number.isFinite(slamDisplayAngle)
                    ? slamDisplayAngle.toFixed(1)
                    : "0.0"}{" "}
                  deg
                </span>
              </div>

              {lidarMessage ? (
                <div className="absolute bottom-4 right-4 z-20 rounded-lg border border-red-400/40 bg-red-500/90 px-3 py-2 text-xs font-bold text-white shadow-lg">
                  {lidarMessage}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
