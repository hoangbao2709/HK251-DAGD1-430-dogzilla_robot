"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { ArrowLeft, Crosshair, Download, Eye, Grid3X3, LocateFixed, MapPinned, Navigation, RotateCcw, RotateCw, Square, Upload } from "lucide-react";
import Link from "next/link";
import { RobotAPI } from "@/app/lib/robotApi";
import RequireAuth from "@/components/auth/RequireAuth";
import type { MapMode, NavPlacementMode, PointsResponse, SlamRenderInfo, SlamStateData } from "../autonomous/types";

type CanvasPoint = {
  x: number;
  y: number;
};

function containedRect(width: number, height: number, naturalWidth: number, naturalHeight: number) {
  if (!width || !height || !naturalWidth || !naturalHeight) return null;

  const imageRatio = naturalWidth / naturalHeight;
  const boxRatio = width / height;
  let drawW = width;
  let drawH = height;
  let offsetX = 0;
  let offsetY = 0;

  if (imageRatio > boxRatio) {
    drawW = width;
    drawH = width / imageRatio;
    offsetY = (height - drawH) / 2;
  } else {
    drawH = height;
    drawW = height * imageRatio;
    offsetX = (width - drawW) / 2;
  }

  return { x: offsetX, y: offsetY, width: drawW, height: drawH };
}

function worldToCanvasPoint(
  x: number,
  y: number,
  renderInfo: SlamRenderInfo,
  image: HTMLImageElement
): CanvasPoint | null {
  const rect = containedRect(
    image.clientWidth,
    image.clientHeight,
    image.naturalWidth || image.clientWidth,
    image.naturalHeight || image.clientHeight
  );
  if (!rect) return null;

  const u = (x - renderInfo.origin_x) / (renderInfo.width_cells * renderInfo.resolution);
  const v = (y - renderInfo.origin_y) / (renderInfo.height_cells * renderInfo.resolution);

  return {
    x: rect.x + u * rect.width,
    y: rect.y + (1 - v) * rect.height,
  };
}

function rotatedClientToWorldPoint(
  clientX: number,
  clientY: number,
  stage: HTMLElement,
  image: HTMLImageElement,
  renderInfo: SlamRenderInfo,
  rotationDeg: number
) {
  const stageRect = stage.getBoundingClientRect();
  const cx = stageRect.left + stageRect.width / 2;
  const cy = stageRect.top + stageRect.height / 2;
  const angle = (-rotationDeg * Math.PI) / 180;
  const dx = clientX - cx;
  const dy = clientY - cy;
  const localX = stageRect.width / 2 + dx * Math.cos(angle) - dy * Math.sin(angle);
  const localY = stageRect.height / 2 + dx * Math.sin(angle) + dy * Math.cos(angle);

  const rect = containedRect(
    image.clientWidth,
    image.clientHeight,
    image.naturalWidth || image.clientWidth,
    image.naturalHeight || image.clientHeight
  );
  if (!rect) return null;

  if (
    localX < rect.x ||
    localX > rect.x + rect.width ||
    localY < rect.y ||
    localY > rect.y + rect.height
  ) {
    return null;
  }

  const u = (localX - rect.x) / rect.width;
  const v = 1 - (localY - rect.y) / rect.height;

  return {
    x: renderInfo.origin_x + u * renderInfo.width_cells * renderInfo.resolution,
    y: renderInfo.origin_y + v * renderInfo.height_cells * renderInfo.resolution,
  };
}

function drawRobot(ctx: CanvasRenderingContext2D, center: CanvasPoint, yaw: number) {
  ctx.save();
  ctx.translate(center.x, center.y);
  ctx.rotate(-yaw);
  ctx.fillStyle = "#00e5a8";
  ctx.strokeStyle = "#001f16";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(14, 0);
  ctx.lineTo(-9, -8);
  ctx.lineTo(-5, 0);
  ctx.lineTo(-9, 8);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

export default function RobotMapPage() {
  const [slamState, setSlamState] = useState<SlamStateData | null>(null);
  const [savedPoints, setSavedPoints] = useState<PointsResponse>({});
  const [error, setError] = useState("");
  const [mapMode, setMapMode] = useState<MapMode>("view");
  const [navPlacementMode, setNavPlacementMode] = useState<NavPlacementMode>("goal");
  const [pendingPlacement, setPendingPlacement] = useState<{ x: number; y: number } | null>(null);
  const [showRobot, setShowRobot] = useState(true);
  const [showPath, setShowPath] = useState(true);
  const [showScan, setShowScan] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [rotationDeg, setRotationDeg] = useState(0);
  const [mapReloadKey, setMapReloadKey] = useState(0);
  const [busyMessage, setBusyMessage] = useState("");

  const stageRef = useRef<HTMLDivElement | null>(null);
  const mapImgRef = useRef<HTMLImageElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  const mapSrc = useMemo(() => RobotAPI.slamMapUrl(mapReloadKey), [mapReloadKey]);

  const fetchSlamState = useCallback(async () => {
    try {
      const json = await RobotAPI.slamState();
      const data = json?.data ?? json ?? null;
      setSlamState(data);
      setError("");
      if (typeof data?.map_version === "number") {
        setMapReloadKey((current) => (current === data.map_version ? current : data.map_version));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Khong lay duoc SLAM state");
    }
  }, []);

  const fetchPoints = useCallback(async () => {
    try {
      const json = await RobotAPI.points();
      setSavedPoints(json?.data ?? json ?? {});
    } catch {
      setSavedPoints({});
    }
  }, []);

  const drawOverlay = useCallback(() => {
    const image = mapImgRef.current;
    const canvas = overlayRef.current;
    const renderInfo = slamState?.render_info;
    if (!image || !canvas || !renderInfo) return;

    const dpr = window.devicePixelRatio || 1;
    const width = image.clientWidth;
    const height = image.clientHeight;
    if (!width || !height) return;

    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const metersW = renderInfo.width_cells * renderInfo.resolution;
    const metersH = renderInfo.height_cells * renderInfo.resolution;

    if (showGrid) {
      ctx.strokeStyle = "rgba(255,255,255,0.16)";
      ctx.lineWidth = 1;
      const step = 0.5;
      const startX = Math.floor(renderInfo.origin_x / step) * step;
      const endX = renderInfo.origin_x + metersW;
      const startY = Math.floor(renderInfo.origin_y / step) * step;
      const endY = renderInfo.origin_y + metersH;

      for (let x = startX; x <= endX; x += step) {
        const a = worldToCanvasPoint(x, renderInfo.origin_y, renderInfo, image);
        const b = worldToCanvasPoint(x, endY, renderInfo, image);
        if (!a || !b) continue;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      for (let y = startY; y <= endY; y += step) {
        const a = worldToCanvasPoint(renderInfo.origin_x, y, renderInfo, image);
        const b = worldToCanvasPoint(renderInfo.origin_x + metersW, y, renderInfo, image);
        if (!a || !b) continue;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
    }

    if (showScan && slamState?.scan?.points?.length) {
      ctx.fillStyle = "#00ff9c";
      for (const point of slamState.scan.points) {
        const p = worldToCanvasPoint(point.x, point.y, renderInfo, image);
        if (!p) continue;
        ctx.fillRect(p.x - 1, p.y - 1, 2, 2);
      }
    }

    if (showPath && slamState?.paths?.a_star?.length) {
      ctx.strokeStyle = "#ff2d55";
      ctx.lineWidth = 3;
      ctx.beginPath();
      let started = false;
      for (const point of slamState.paths.a_star) {
        const p = worldToCanvasPoint(point.x, point.y, renderInfo, image);
        if (!p) continue;
        if (!started) {
          ctx.moveTo(p.x, p.y);
          started = true;
        } else {
          ctx.lineTo(p.x, p.y);
        }
      }
      if (started) ctx.stroke();
    }

    for (const [name, point] of Object.entries(savedPoints)) {
      const p = worldToCanvasPoint(point.x, point.y, renderInfo, image);
      if (!p) continue;
      ctx.fillStyle = "#ffd84d";
      ctx.strokeStyle = "#251a00";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#ffffff";
      ctx.font = "600 11px Arial";
      ctx.fillText(name, p.x + 8, p.y - 8);
    }

    if (slamState?.goal?.x != null && slamState.goal.y != null) {
      const p = worldToCanvasPoint(Number(slamState.goal.x), Number(slamState.goal.y), renderInfo, image);
      if (p) {
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 9, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    if (pendingPlacement) {
      const p = worldToCanvasPoint(pendingPlacement.x, pendingPlacement.y, renderInfo, image);
      if (p) {
        ctx.strokeStyle = navPlacementMode === "goal" ? "#10b981" : "#f59e0b";
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.arc(p.x, p.y, 11, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    if (showRobot && slamState?.pose?.ok) {
      const p = worldToCanvasPoint(slamState.pose.x, slamState.pose.y, renderInfo, image);
      if (p) drawRobot(ctx, p, slamState.pose.theta || 0);
    }
  }, [navPlacementMode, pendingPlacement, savedPoints, showGrid, showPath, showRobot, showScan, slamState]);

  useEffect(() => {
    fetchSlamState();
    fetchPoints();
    const timers = [
      window.setInterval(fetchSlamState, 900),
      window.setInterval(fetchPoints, 5000),
    ];
    return () => timers.forEach(window.clearInterval);
  }, [fetchPoints, fetchSlamState]);

  useEffect(() => {
    const id = window.requestAnimationFrame(drawOverlay);
    return () => window.cancelAnimationFrame(id);
  }, [drawOverlay, mapSrc, rotationDeg]);

  const handleMapClick = async (event: MouseEvent<HTMLImageElement>) => {
    if (mapMode !== "navigate") return;
    const renderInfo = slamState?.render_info;
    const image = mapImgRef.current;
    const stage = stageRef.current;
    if (!renderInfo || !image || !stage) return;

    const point = rotatedClientToWorldPoint(
      event.clientX,
      event.clientY,
      stage,
      image,
      renderInfo,
      rotationDeg
    );
    if (!point) return;

    if (!pendingPlacement) {
      setPendingPlacement(point);
      return;
    }

    const yaw = Math.atan2(point.y - pendingPlacement.y, point.x - pendingPlacement.x);
    setBusyMessage(navPlacementMode === "goal" ? "Sending goal..." : "Setting initial pose...");

    try {
      if (navPlacementMode === "goal") {
        await RobotAPI.manualGoal({
          x: pendingPlacement.x,
          y: pendingPlacement.y,
          yaw,
          route_name: "robot_map_goal",
        });
      } else {
        await RobotAPI.setInitialPose({
          x: pendingPlacement.x,
          y: pendingPlacement.y,
          yaw,
        });
      }
      setPendingPlacement(null);
      await fetchSlamState();
    } finally {
      setBusyMessage("");
    }
  };

  const stopAndClear = async () => {
    setBusyMessage("Stopping navigation...");
    try {
      await RobotAPI.patrolStop().catch(() => {});
      await RobotAPI.clearNavigation();
      setPendingPlacement(null);
      await fetchSlamState();
    } finally {
      setBusyMessage("");
    }
  };

  const saveMap = async () => {
    const fallbackName = `map_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}`;
    const name = window.prompt("Map name", fallbackName);
    if (!name) return;

    setBusyMessage("Saving map...");
    try {
      const result = await RobotAPI.saveSlamMap(name);
      const bundle = result?.result?.bundle;
      if (bundle) {
        window.open(RobotAPI.slamMapFileUrl(bundle), "_blank");
      }
    } finally {
      setBusyMessage("");
    }
  };

  const uploadMap = async (file: File | undefined) => {
    if (!file) return;
    setBusyMessage("Uploading map...");
    try {
      await RobotAPI.uploadSlamMap(file);
      setMapReloadKey(Date.now());
      await fetchSlamState();
    } finally {
      setBusyMessage("");
      if (uploadInputRef.current) uploadInputRef.current.value = "";
    }
  };

  const useLiveMap = async () => {
    setBusyMessage("Switching to live map...");
    try {
      await RobotAPI.useLiveSlamMap();
      setMapReloadKey(Date.now());
      await fetchSlamState();
    } finally {
      setBusyMessage("");
    }
  };

  const autoAlign = () => {
    const theta = slamState?.pose?.theta;
    if (typeof theta === "number" && Number.isFinite(theta)) {
      setRotationDeg((-theta * 180) / Math.PI);
    }
  };

  const modeText =
    mapMode === "view"
      ? "VIEW"
      : navPlacementMode === "goal"
        ? pendingPlacement
          ? "NAV: choose heading"
          : "NAV: choose goal"
        : pendingPlacement
          ? "INIT: choose heading"
          : "INIT: choose pose";

  return (
    <RequireAuth>
      <main className="fixed inset-0 overflow-hidden bg-[#1f2222] text-[#eef3f2]">
      <div
        ref={stageRef}
        className={`absolute inset-0 overflow-hidden ${mapMode === "navigate" ? "cursor-crosshair" : "cursor-default"}`}
      >
        <div
          className="absolute inset-0 transition-transform duration-150"
          style={{ transform: `rotate(${rotationDeg}deg)` }}
        >
          <img
            ref={mapImgRef}
            src={mapSrc}
            alt="SLAM map"
            className="absolute inset-0 h-full w-full select-none object-contain [image-rendering:pixelated]"
            draggable={false}
            onLoad={drawOverlay}
            onClick={handleMapClick}
          />
          <canvas ref={overlayRef} className="pointer-events-none absolute inset-0 h-full w-full" />
        </div>
      </div>

      <aside className="absolute left-5 top-5 z-20 w-[330px] rounded-2xl border border-white/10 bg-[#1d1f20]/90 p-4 shadow-2xl backdrop-blur">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="text-xs font-bold uppercase tracking-[0.18em] text-white/85">Options</div>
          <Link
            href="/autonomous"
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-white transition hover:bg-white/15"
            title="Back to autonomous"
          >
            <ArrowLeft size={16} />
          </Link>
        </div>

        <div className="space-y-3">
          <section className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
            <div className="mb-3 inline-flex rounded-xl border border-white/10 bg-white/5 p-1">
              <button
                onClick={() => setMapMode("view")}
                className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold transition ${
                  mapMode === "view" ? "bg-[#3b9df6] text-white shadow-inner" : "text-white/75 hover:bg-white/10"
                }`}
              >
                <Eye size={14} />
                View
              </button>
              <button
                onClick={() => setMapMode("navigate")}
                className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold transition ${
                  mapMode === "navigate" ? "bg-[#3b9df6] text-white shadow-inner" : "text-white/75 hover:bg-white/10"
                }`}
              >
                <Navigation size={14} />
                Nav
              </button>
            </div>

            {mapMode === "navigate" ? (
              <div className="mb-3 flex flex-wrap gap-2">
                <button
                  onClick={() => {
                    setNavPlacementMode("goal");
                    setPendingPlacement(null);
                  }}
                  className={`rounded-lg px-3 py-2 text-xs font-bold ${
                    navPlacementMode === "goal" ? "bg-emerald-500 text-black" : "bg-white/10 text-white"
                  }`}
                >
                  Set goal
                </button>
                <button
                  onClick={() => {
                    setNavPlacementMode("initialPose");
                    setPendingPlacement(null);
                  }}
                  className={`rounded-lg px-3 py-2 text-xs font-bold ${
                    navPlacementMode === "initialPose" ? "bg-amber-400 text-black" : "bg-white/10 text-white"
                  }`}
                >
                  Initial pose
                </button>
                <button onClick={stopAndClear} className="rounded-lg bg-red-500 px-3 py-2 text-xs font-bold text-white">
                  Stop & clear
                </button>
              </div>
            ) : null}

            <div className="grid grid-cols-2 gap-2 text-xs text-white/80">
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={showRobot} onChange={() => setShowRobot((value) => !value)} />
                Robot
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={showPath} onChange={() => setShowPath((value) => !value)} />
                Path
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={showScan} onChange={() => setShowScan((value) => !value)} />
                Scan
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={showGrid} onChange={() => setShowGrid((value) => !value)} />
                Grid
              </label>
            </div>
          </section>

          <section className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
            <div className="grid grid-cols-2 gap-2">
              <button onClick={saveMap} className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#2d93ea] px-3 py-2 text-xs font-bold text-white">
                <Download size={14} />
                Save map
              </button>
              <button onClick={() => uploadInputRef.current?.click()} className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#2d93ea] px-3 py-2 text-xs font-bold text-white">
                <Upload size={14} />
                Load map
              </button>
              <input
                ref={uploadInputRef}
                type="file"
                className="hidden"
                accept=".zip,.yaml,.yml,.pgm,.png,.jpg,.jpeg"
                onChange={(event) => uploadMap(event.target.files?.[0])}
              />
            </div>

            <div className="mt-2 grid grid-cols-3 gap-2">
              <button onClick={() => setRotationDeg(0)} className="rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white">
                Reset view
              </button>
              <button onClick={() => setRotationDeg((value) => value - 15)} className="inline-flex items-center justify-center gap-1 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white">
                <RotateCcw size={14} />
                Rotate -
              </button>
              <button onClick={() => setRotationDeg((value) => value + 15)} className="inline-flex items-center justify-center gap-1 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white">
                <RotateCw size={14} />
                Rotate +
              </button>
            </div>

            <div className="mt-2 grid grid-cols-2 gap-2">
              <button onClick={autoAlign} className="inline-flex items-center justify-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white">
                <LocateFixed size={14} />
                Auto align
              </button>
              <button onClick={useLiveMap} className="inline-flex items-center justify-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-white">
                <MapPinned size={14} />
                Live map
              </button>
            </div>

            <div className="mt-3 text-xs text-white/65">Display angle: {rotationDeg.toFixed(1)} deg</div>
          </section>
        </div>
      </aside>

      <div className="absolute bottom-5 left-5 z-20 flex flex-wrap items-center gap-2 text-xs">
        <span className="inline-flex items-center gap-2 rounded-full bg-black/45 px-3 py-2 text-white backdrop-blur">
          <Crosshair size={14} />
          {modeText}
        </span>
        <span className="inline-flex items-center gap-2 rounded-full bg-black/45 px-3 py-2 text-white/75 backdrop-blur">
          <Grid3X3 size={14} />
          map v{slamState?.map_version ?? "-"}
        </span>
        {busyMessage ? (
          <span className="inline-flex items-center gap-2 rounded-full bg-[#2d93ea]/90 px-3 py-2 text-white backdrop-blur">
            {busyMessage}
          </span>
        ) : null}
        {error ? (
          <span className="inline-flex items-center gap-2 rounded-full bg-red-500/90 px-3 py-2 text-white backdrop-blur">
            {error}
          </span>
        ) : null}
      </div>

      {pendingPlacement ? (
        <button
          onClick={() => setPendingPlacement(null)}
          className="absolute bottom-5 right-5 z-20 inline-flex items-center gap-2 rounded-full bg-red-500 px-4 py-3 text-xs font-bold text-white shadow-xl"
        >
          <Square size={14} />
          Cancel placing
        </button>
      ) : null}
      </main>
    </RequireAuth>
  );
}
