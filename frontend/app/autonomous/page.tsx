"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { RobotAPI, DEFAULT_DOG_SERVER } from "@/app/lib/robotApi";
import { getSelectedRobotAddr } from "@/app/lib/selectedRobot";
import { CameraPanel } from "./components/CameraPanel";
import { MapPanel } from "./components/MapPanel";
import { SavedPointsPanel } from "./components/SavedPointsPanel";
import { SidebarPanel } from "./components/SidebarPanel";
import { VoiceCommandPanel } from "./components/VoiceCommandPanel";
import type {
  ControlStatusResponse,
  MapMode,
  NavPlacementMode,
  PatrolMission,
  PatrolStatusResponse,
  PointsResponse,
  QrPositionData,
  QrStateData,
  RobotStatusResponse,
  SlamRenderInfo,
  SlamStateData,
} from "./types";

function getLidarUrl(server: string) {
  try {
    const url = new URL(server);
    const host = url.hostname;
    const port = url.port;

    if (port === "9000" || port === "") {
      return `${url.protocol}//${host}:8080`;
    }
    if (port === "9002") {
      return `${url.protocol}//${host}:9002/lidar/`;
    }
    return `${url.origin.replace(/\/$/, "")}/lidar/`;
  } catch {
    return "";
  }
}

function getContainedImageRect(image: HTMLImageElement) {
  const boxW = image.clientWidth;
  const boxH = image.clientHeight;
  const naturalW = image.naturalWidth || boxW;
  const naturalH = image.naturalHeight || boxH;

  if (!boxW || !boxH || !naturalW || !naturalH) return null;

  const imageRatio = naturalW / naturalH;
  const boxRatio = boxW / boxH;

  let drawW = boxW;
  let drawH = boxH;
  let offsetX = 0;
  let offsetY = 0;

  if (imageRatio > boxRatio) {
    drawW = boxW;
    drawH = boxW / imageRatio;
    offsetY = (boxH - drawH) / 2;
  } else {
    drawH = boxH;
    drawW = boxH * imageRatio;
    offsetX = (boxW - drawW) / 2;
  }

  return { x: offsetX, y: offsetY, width: drawW, height: drawH };
}

function worldToCanvasPoint(
  x: number,
  y: number,
  renderInfo: SlamRenderInfo,
  image: HTMLImageElement
) {
  const contained = getContainedImageRect(image);
  if (!contained) return null;

  const u =
    (x - renderInfo.origin_x) /
    (renderInfo.width_cells * renderInfo.resolution);
  const v =
    (y - renderInfo.origin_y) /
    (renderInfo.height_cells * renderInfo.resolution);

  return {
    x: contained.x + u * contained.width,
    y: contained.y + (1 - v) * contained.height,
  };
}

function clientToWorldPoint(
  clientX: number,
  clientY: number,
  image: HTMLImageElement,
  renderInfo: SlamRenderInfo
) {
  const rect = image.getBoundingClientRect();
  const contained = getContainedImageRect(image);
  if (!contained) return null;

  const localX = clientX - rect.left;
  const localY = clientY - rect.top;

  if (
    localX < contained.x ||
    localX > contained.x + contained.width ||
    localY < contained.y ||
    localY > contained.y + contained.height
  ) {
    return null;
  }

  const u = (localX - contained.x) / contained.width;
  const v = 1 - (localY - contained.y) / contained.height;

  return {
    x: renderInfo.origin_x + u * renderInfo.width_cells * renderInfo.resolution,
    y: renderInfo.origin_y + v * renderInfo.height_cells * renderInfo.resolution,
  };
}

function normalizePointName(name: string) {
  return name.trim().toLowerCase();
}

export default function AutonomousControlPage() {
  const { resolvedTheme } = useTheme();

  const [themeMounted, setThemeMounted] = useState(false);
  const [connected, setConnected] = useState(false);
  const [robotStatus, setRobotStatus] = useState<RobotStatusResponse | null>(null);

  const [slamState, setSlamState] = useState<SlamStateData | null>(null);
  const [slamError, setSlamError] = useState("");

  const [qrState, setQrState] = useState<QrStateData | null>(null);
  const [qrError, setQrError] = useState("");
  const [qrPosition, setQrPosition] = useState<QrPositionData | null>(null);
  const [qrPositionError, setQrPositionError] = useState("");
  const [controlStatus, setControlStatus] = useState<ControlStatusResponse | null>(
    null
  );
  const [lidarBusy, setLidarBusy] = useState(false);
  const [lidarError, setLidarError] = useState<string | null>(null);

  const [cameraError, setCameraError] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [mapReloadKey, setMapReloadKey] = useState(0);
  const [mapModalOpen, setMapModalOpen] = useState(false);

  const [selectedMapName, setSelectedMapName] = useState("warehouse_01");
  const [savedPoints, setSavedPoints] = useState<PointsResponse>({});
  const [pointActionLoading, setPointActionLoading] = useState(false);
  const [patrolRunning, setPatrolRunning] = useState(false);
  const [patrolMission, setPatrolMission] = useState<PatrolMission | null>(null);

  const mapImgRef = useRef<HTMLImageElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const modalMapImgRef = useRef<HTMLImageElement | null>(null);
  const modalOverlayRef = useRef<HTMLCanvasElement | null>(null);

  const [robotAddr, setRobotAddr] = useState(
    () => getSelectedRobotAddr() || DEFAULT_DOG_SERVER
  );
  const [backendSyncError, setBackendSyncError] = useState("");
  const [commandText, setCommandText] = useState("");
  const [isSendingCommand, setIsSendingCommand] = useState(false);
  const [commandResult, setCommandResult] = useState<any | null>(null);
  const [commandError, setCommandError] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dogServer, setDogServer] = useState(
    () => getSelectedRobotAddr() || DEFAULT_DOG_SERVER
  );
  const pendingTranscriptRef = useRef("");

  const [mapMode, setMapMode] = useState<MapMode>("view");
  const [navPlacementMode, setNavPlacementMode] =
    useState<NavPlacementMode>("goal");
  const [pendingPlacement, setPendingPlacement] = useState<{
    x: number;
    y: number;
  } | null>(null);

  const [showRobot, setShowRobot] = useState(true);
  const [showPath, setShowPath] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [slamDisplayAngle, setSlamDisplayAngle] = useState(0);

  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    setDogServer(getSelectedRobotAddr() || DEFAULT_DOG_SERVER);
    setRobotAddr(getSelectedRobotAddr() || DEFAULT_DOG_SERVER);
  }, []);

  useEffect(() => {
    setThemeMounted(true);
  }, []);

  const isDark = themeMounted && resolvedTheme === "dark";
  const lidarUrl = useMemo(() => getLidarUrl(dogServer), [dogServer]);

  useEffect(() => {
    if (!mapModalOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMapModalOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mapModalOpen]);

  const fetchRobotStatus = useCallback(async () => {
    try {
      const data = await RobotAPI.status();
      setRobotStatus(data);
      setConnected(Boolean(data.telemetry?.robot_connected));
    } catch {
      setConnected(false);
    }
  }, []);

  const syncBackendRobotAddr = useCallback(async (addr: string) => {
    const normalizedAddr = addr.trim();
    if (!normalizedAddr) {
      setConnected(false);
      setBackendSyncError("Thieu robot address.");
      return;
    }

    try {
      const data = await RobotAPI.connect(normalizedAddr);
      setConnected(Boolean(data.connected ?? data.ok));
      setBackendSyncError("");
    } catch (error) {
      setConnected(false);
      setBackendSyncError(
        error instanceof Error ? error.message : "Khong dong bo duoc robot address"
      );
    }
  }, []);

  const fetchSlamState = useCallback(async () => {
    try {
      const json = await RobotAPI.slamState();
      const data = json?.data ?? json ?? null;
      setSlamState(data);
      setSlamError("");
    } catch (error) {
      setSlamState(null);
      setSlamError(error instanceof Error ? error.message : "Khong lay duoc /state");
    }
  }, []);

  const fetchQrState = useCallback(async () => {
    try {
      const json = await RobotAPI.qrState();
      const data = json?.data ?? json ?? null;
      setQrState(data);
      setQrError("");
    } catch (error) {
      setQrState(null);
      setQrError(
        error instanceof Error ? error.message : "Khong lay duoc trang thai QR"
      );
    }
  }, []);

  const fetchQrPosition = useCallback(async () => {
    try {
      const json = await RobotAPI.qrPosition();
      const data = json?.data ?? json ?? null;
      setQrPosition(data);
      setQrPositionError("");
    } catch (error) {
      setQrPosition(null);
      setQrPositionError(
        error instanceof Error ? error.message : "Khong lay duoc vi tri QR"
      );
    }
  }, []);

  const fetchControlStatus = useCallback(async () => {
    try {
      const json = await RobotAPI.controlStatus();
      const data = json?.data ?? json ?? null;
      setControlStatus(data);
    } catch {
      setControlStatus(null);
    }
  }, []);

  const fetchPoints = useCallback(async () => {
    try {
      const json = await RobotAPI.points();
      const data = json?.data ?? json ?? {};
      setSavedPoints(data || {});
    } catch {
      setSavedPoints({});
    }
  }, []);

  const fetchPatrolStatus = useCallback(async () => {
    try {
      const data = (await RobotAPI.patrolStatus()) as PatrolStatusResponse;
      setPatrolRunning(Boolean(data?.running));
      setPatrolMission(data?.mission ?? null);
    } catch {
      setPatrolRunning(false);
      setPatrolMission(null);
    }
  }, []);

  useEffect(() => {
    fetchRobotStatus();
    fetchSlamState();
    fetchQrState();
    fetchQrPosition();
    fetchControlStatus();
    fetchPoints();
    fetchPatrolStatus();

    const timers = [
      setInterval(fetchRobotStatus, 3000),
      setInterval(fetchSlamState, 1500),
      setInterval(fetchQrState, 700),
      setInterval(fetchQrPosition, 700),
      setInterval(fetchControlStatus, 5000),
      setInterval(fetchPoints, 5000),
      setInterval(fetchPatrolStatus, 1500),
      setInterval(() => setMapReloadKey((value) => value + 1), 3000),
    ];

    return () => timers.forEach(clearInterval);
  }, [
    fetchRobotStatus,
    fetchSlamState,
    fetchQrState,
    fetchQrPosition,
    fetchControlStatus,
    fetchPoints,
    fetchPatrolStatus,
  ]);

  useEffect(() => {
    const normalizedAddr = dogServer.trim();
    setRobotAddr(normalizedAddr);
    void syncBackendRobotAddr(normalizedAddr);
  }, [dogServer, syncBackendRobotAddr]);

  const clearPath = useCallback(async () => {
    try {
      await RobotAPI.patrolStop();
    } catch { }

    try {
      await RobotAPI.clearNavigation();
    } catch { }

    setPendingPlacement(null);
    setPatrolRunning(false);
    setPatrolMission(null);
    await Promise.allSettled([fetchSlamState(), fetchPatrolStatus()]);
  }, [fetchSlamState, fetchPatrolStatus]);

  const handleToggleLidar = useCallback(async () => {
    if (lidarBusy) return;

    const running = Boolean(
      controlStatus?.lidar_running ?? controlStatus?.lidar?.running ?? false
    );
    const next = !running;

    try {
      setLidarBusy(true);
      setLidarError(null);
      if (next) {
        await RobotAPI.lidar("start", { mode: "live_map" });
      } else {
        await RobotAPI.lidar("stop");
      }
      setControlStatus((previous) => ({
        ...(previous || {}),
        lidar_running: next,
        lidar: {
          ...(previous?.lidar || {}),
          running: next,
        },
      }));
    } catch (error) {
      setLidarError(
        error instanceof Error ? error.message : "Khong dieu khien duoc LiDAR"
      );
    } finally {
      setLidarBusy(false);
      fetchControlStatus();
    }
  }, [controlStatus, fetchControlStatus, lidarBusy]);

  const handleStartStatic = useCallback(async (mapArg?: string) => {
    if (lidarBusy) return;
    try {
      setLidarBusy(true);
      setLidarError(null);
      const cleanedMapArg = String(mapArg || "").trim();
      await RobotAPI.lidar("start", {
        mode: "navigation",
        ...(cleanedMapArg ? { map_arg: cleanedMapArg } : {}),
      });
      
      setControlStatus((previous) => ({
        ...(previous || {}),
        lidar_running: true,
        lidar: { ...(previous?.lidar || {}), running: true },
      }));
    } catch (error) {
      setLidarError(error instanceof Error ? error.message : "Lá»—i khi báº­t Static Navigation");
    } finally {
      setLidarBusy(false);
      fetchControlStatus();
    }
  }, [lidarBusy, fetchControlStatus]);

  const handleStartNavigation = useCallback(async (mapName: string) => {
    if (lidarBusy) return;
    try {
      setLidarBusy(true);
      setLidarError(null);
      await RobotAPI.lidar("start", { mode: "navigation", map_name: mapName });
      
      setControlStatus((previous) => ({
        ...(previous || {}),
        lidar_running: true,
        lidar: { ...(previous?.lidar || {}), running: true },
      }));
    } catch (error) {
      setLidarError(error instanceof Error ? error.message : "Lá»—i khi báº­t Navigation");
    } finally {
      setLidarBusy(false);
      fetchControlStatus();
    }
  }, [lidarBusy, fetchControlStatus]);

  const handleResetLidar = useCallback(async () => {
    if (lidarBusy) return;
    try {
      setLidarBusy(true);
      setLidarError(null);
      await RobotAPI.lidarReset({ wait_seconds: 2.0, mode: "live_map" });
    } catch (error) {
      setLidarError(error instanceof Error ? error.message : "Lá»—i Reset LiDAR");
    } finally {
      setLidarBusy(false);
      fetchControlStatus();
    }
  }, [lidarBusy, fetchControlStatus]);

  const resetSlamView = useCallback(() => {
    setSlamDisplayAngle(0);
  }, []);

  const rotateSlamViewLeft = useCallback(() => {
    setSlamDisplayAngle((value) => value - 15);
  }, []);

  const rotateSlamViewRight = useCallback(() => {
    setSlamDisplayAngle((value) => value + 15);
  }, []);

  const handleSlamMapClick = useCallback(
    async (event: React.MouseEvent<HTMLImageElement>, isModal = false) => {
      if (mapMode !== "navigate") return;
      if (!slamState?.render_info) return;

      const image = isModal ? modalMapImgRef.current : mapImgRef.current;
      if (!image) return;

      const point = clientToWorldPoint(
        event.clientX,
        event.clientY,
        image,
        slamState.render_info
      );
      if (!point) return;

      if (!pendingPlacement) {
        setPendingPlacement({ x: point.x, y: point.y });
        return;
      }

      const yaw = Math.atan2(
        point.y - pendingPlacement.y,
        point.x - pendingPlacement.x
      );

      try {
        if (navPlacementMode === "goal") {
          await RobotAPI.manualGoal({
            x: pendingPlacement.x,
            y: pendingPlacement.y,
            yaw,
            addr: dogServer,
            route_name: "manual_map_goal",
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
        await fetchPatrolStatus();
      } catch { }
    },
    [mapMode, slamState, pendingPlacement, navPlacementMode, dogServer, fetchSlamState, fetchPatrolStatus]
  );

  const qrPreviewPoint = useMemo(() => {
    const pose = slamState?.pose;
    const qrText = qrPosition?.qr?.text?.trim();
    const qrForward = qrPosition?.position?.forward_z_m;
    const qrLateral = qrPosition?.position?.lateral_x_m;

    if (
      !pose?.ok ||
      !qrPosition?.detected ||
      !qrText ||
      typeof qrForward !== "number" ||
      typeof qrLateral !== "number"
    ) {
      return null;
    }

    const alreadySaved = Object.keys(savedPoints || {}).some(
      (name) => normalizePointName(name) === normalizePointName(qrText)
    );
    if (alreadySaved) return null;

    const yaw = pose.theta || 0;
    const worldX =
      pose.x + Math.cos(yaw) * qrForward + Math.sin(yaw) * qrLateral;
    const worldY =
      pose.y + Math.sin(yaw) * qrForward - Math.cos(yaw) * qrLateral;

    return {
      name: qrText,
      x: worldX,
      y: worldY,
    };
  }, [qrPosition, savedPoints, slamState?.pose]);

  const drawSlamOverlay = useCallback(() => {
    const drawGridLines = (
      ctx: CanvasRenderingContext2D,
      image: HTMLImageElement,
      renderInfo: SlamRenderInfo
    ) => {
      const stepMeters = 0.5;
      const widthM = renderInfo.width_cells * renderInfo.resolution;
      const heightM = renderInfo.height_cells * renderInfo.resolution;

      const startX = Math.floor(renderInfo.origin_x / stepMeters) * stepMeters;
      const endX = renderInfo.origin_x + widthM;
      const startY = Math.floor(renderInfo.origin_y / stepMeters) * stepMeters;
      const endY = renderInfo.origin_y + heightM;

      for (let x = startX; x <= endX + 1e-6; x += stepMeters) {
        const p1 = worldToCanvasPoint(x, renderInfo.origin_y, renderInfo, image);
        const p2 = worldToCanvasPoint(x, endY, renderInfo, image);
        if (!p1 || !p2) continue;
        const isMajor = Math.abs(x - Math.round(x)) < 1e-6;
        ctx.strokeStyle = isMajor
          ? "rgba(255,255,255,0.18)"
          : "rgba(255,255,255,0.08)";
        ctx.lineWidth = isMajor ? 1 : 0.5;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }

      for (let y = startY; y <= endY + 1e-6; y += stepMeters) {
        const p1 = worldToCanvasPoint(renderInfo.origin_x, y, renderInfo, image);
        const p2 = worldToCanvasPoint(endX, y, renderInfo, image);
        if (!p1 || !p2) continue;
        const isMajor = Math.abs(y - Math.round(y)) < 1e-6;
        ctx.strokeStyle = isMajor
          ? "rgba(255,255,255,0.18)"
          : "rgba(255,255,255,0.08)";
        ctx.lineWidth = isMajor ? 1 : 0.5;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }
    };

    const drawOn = (
      canvas: HTMLCanvasElement | null,
      image: HTMLImageElement | null
    ) => {
      const drawLabel = (
        ctx: CanvasRenderingContext2D,
        text: string,
        x: number,
        y: number
      ) => {
        ctx.save();
        ctx.font = "bold 13px Arial";
        ctx.textBaseline = "middle";
        ctx.lineWidth = 3;
        ctx.strokeStyle = "rgba(255, 255, 255, 0.95)";
        ctx.strokeText(text, x, y);
        ctx.fillStyle = "#0f172a";
        ctx.shadowColor = "rgba(255, 255, 255, 0.85)";
        ctx.shadowBlur = 4;
        ctx.fillText(text, x, y);
        ctx.restore();
      };

      if (!canvas || !image) return;

      const width = image.clientWidth;
      const height = image.clientHeight;
      if (!width || !height) return;

      canvas.width = width;
      canvas.height = height;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.clearRect(0, 0, width, height);

      if (!slamState?.render_info) return;
      const renderInfo = slamState.render_info;

      if (showGrid) {
        drawGridLines(ctx, image, renderInfo);
      }

      if (slamState.scan?.ok && slamState.scan.points?.length) {
        ctx.fillStyle = "rgba(0,255,120,0.85)";
        for (const p of slamState.scan.points) {
          const px = worldToCanvasPoint(p.x, p.y, renderInfo, image);
          if (!px) continue;
          ctx.fillRect(px.x - 1.5, px.y - 1.5, 3, 3);
        }
      }

      if (showPath && slamState.paths?.a_star?.length) {
        ctx.strokeStyle = "rgba(255,70,120,0.95)";
        ctx.lineWidth = 3;
        ctx.beginPath();
        let started = false;
        for (const p of slamState.paths.a_star) {
          const px = worldToCanvasPoint(p.x, p.y, renderInfo, image);
          if (!px) continue;
          if (!started) {
            ctx.moveTo(px.x, px.y);
            started = true;
          } else {
            ctx.lineTo(px.x, px.y);
          }
        }
        if (started) ctx.stroke();
      }

      for (const [name, marker] of Object.entries(savedPoints || {}) as Array<
        [string, { x: number; y: number; yaw?: number }]
      >) {
        const px = worldToCanvasPoint(marker.x, marker.y, renderInfo, image);
        if (!px) continue;

        ctx.strokeStyle = "#00ff9d";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(px.x, px.y, 10, 0, Math.PI * 2);
        ctx.stroke();

        ctx.fillStyle = "#00ff9d";
        ctx.beginPath();
        ctx.arc(px.x, px.y, 4, 0, Math.PI * 2);
        ctx.fill();

        drawLabel(ctx, name, px.x + 12, px.y - 16);
      }

      if (qrPreviewPoint) {
        const px = worldToCanvasPoint(
          qrPreviewPoint.x,
          qrPreviewPoint.y,
          renderInfo,
          image
        );
        if (px) {
          ctx.strokeStyle = "#f59e0b";
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.arc(px.x, px.y, 10, 0, Math.PI * 2);
          ctx.stroke();

          ctx.fillStyle = "#f97316";
          ctx.beginPath();
          ctx.arc(px.x, px.y, 4, 0, Math.PI * 2);
          ctx.fill();

          ctx.strokeStyle = "rgba(245, 158, 11, 0.9)";
          ctx.lineWidth = 2;
          ctx.setLineDash([6, 4]);
          ctx.beginPath();
          ctx.moveTo(px.x - 12, px.y);
          ctx.lineTo(px.x + 12, px.y);
          ctx.moveTo(px.x, px.y - 12);
          ctx.lineTo(px.x, px.y + 12);
          ctx.stroke();
          ctx.setLineDash([]);

          drawLabel(ctx, qrPreviewPoint.name, px.x + 12, px.y - 16);
        }
      }

      if (
        slamState.goal &&
        typeof slamState.goal.x === "number" &&
        typeof slamState.goal.y === "number"
      ) {
        const goalPx = worldToCanvasPoint(
          slamState.goal.x,
          slamState.goal.y,
          renderInfo,
          image
        );
        if (goalPx) {
          ctx.strokeStyle = "rgba(255,60,60,0.95)";
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.arc(goalPx.x, goalPx.y, 8, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      if (pendingPlacement) {
        const pendingPx = worldToCanvasPoint(
          pendingPlacement.x,
          pendingPlacement.y,
          renderInfo,
          image
        );
        if (pendingPx) {
          ctx.strokeStyle =
            navPlacementMode === "goal"
              ? "rgba(80,255,120,0.95)"
              : "rgba(255,180,0,0.95)";
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.arc(pendingPx.x, pendingPx.y, 10, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      if (showRobot && slamState.pose?.ok) {
        const robotPx = worldToCanvasPoint(
          slamState.pose.x,
          slamState.pose.y,
          renderInfo,
          image
        );
        if (robotPx) {
          ctx.fillStyle = "#00d9ff";
          ctx.beginPath();
          ctx.arc(robotPx.x, robotPx.y, 7, 0, Math.PI * 2);
          ctx.fill();

          const yaw = slamState.pose.theta || 0;
          const headPx = worldToCanvasPoint(
            slamState.pose.x + 0.22 * Math.cos(yaw),
            slamState.pose.y + 0.22 * Math.sin(yaw),
            renderInfo,
            image
          );
          if (headPx) {
            ctx.strokeStyle = "#ffe14d";
            ctx.lineWidth = 4;
            ctx.beginPath();
            ctx.moveTo(robotPx.x, robotPx.y);
            ctx.lineTo(headPx.x, headPx.y);
            ctx.stroke();
          }
        }
      }
    };

    drawOn(overlayRef.current, mapImgRef.current);
    drawOn(modalOverlayRef.current, modalMapImgRef.current);
  }, [
    slamState,
    savedPoints,
    qrPreviewPoint,
    pendingPlacement,
    navPlacementMode,
    showRobot,
    showPath,
    showGrid,
  ]);

  useEffect(() => {
    drawSlamOverlay();
  }, [drawSlamOverlay]);

  const createPointFromObstacle = async () => {
    const qrText = (qrState?.ok && qrState.items?.length
      ? qrState.items[0].text
      : null);
    const pointName = (qrText || "POINT").trim() || "POINT";

    if (savedPoints[pointName]) {
      window.alert(`Diem ${pointName} da ton tai.`);
      return;
    }

    try {
      setPointActionLoading(true);

      await RobotAPI.createPointFromObstacle({ name: pointName });

      await RobotAPI.logQRAttempt({
        name: pointName,
        success: true,
      }).catch(() => { });

      await fetchPoints();
      await fetchSlamState();
    } catch (error) {
      const body = (error as any)?.body || {};
      const reason = body?.reason === "no_obstacle" ? "no_obstacle" : "ros_error";
      if (reason === "no_obstacle") {
        window.alert("Chua co obstacle phia truoc de luu.");
      }
      await RobotAPI.logQRAttempt({
        name: pointName,
        success: false,
        reason,
      }).catch(() => { });
    } finally {
      setPointActionLoading(false);
    }
  };

  const deletePoint = async (name: string) => {
    try {
      setPointActionLoading(true);
      await RobotAPI.deletePoint(name);
      await fetchPoints();
    } finally {
      setPointActionLoading(false);
    }
  };

  const deleteLastPoint = async () => {
    const names = Object.keys(savedPoints || {}).sort();
    if (!names.length) return;
    await deletePoint(names[names.length - 1]);
  };

  const clearAllPoints = async () => {
    const names = Object.keys(savedPoints || {});
    if (!names.length) return;
    if (!window.confirm("Xoa tat ca diem da luu?")) return;

    for (const name of names) {
      await deletePoint(name);
    }
  };

  const goToPoint = async (name: string) => {
    try {
      setPointActionLoading(true);
      await RobotAPI.patrolStart({
        route_name: `point_${name}`,
        points: [name],
        wait_sec_per_point: 0,
        max_retry_per_point: 1,
        skip_on_fail: true,
      });
    } finally {
      await fetchPatrolStatus();
      setPointActionLoading(false);
    }
  };

  const startPatrolAll = async () => {
    const names = Object.keys(savedPoints || {}).sort();
    if (!names.length) return;

    try {
      setPointActionLoading(true);
      await RobotAPI.patrolStart({
        route_name: "saved_points_route",
        points: names,
        wait_sec_per_point: 3,
        max_retry_per_point: 1,
        skip_on_fail: true,
      });
    } finally {
      await fetchPatrolStatus();
      setPointActionLoading(false);
    }
  };

  const pickVietnameseFemaleVoice = useCallback((voices: SpeechSynthesisVoice[]) => {
    const vietnameseVoices = voices.filter((voice) =>
      voice.lang.toLowerCase().startsWith("vi") ||
      voice.name.toLowerCase().includes("vietnam") ||
      voice.name.toLowerCase().includes("tiếng việt") ||
      voice.name.toLowerCase().includes("tieng viet")
    );
    const preferredNames = [
      "hoaimy",
      "hoai my",
      "linh",
      "mai",
      "thao",
      "female",
      "woman",
      "natural",
      "online",
    ];

    return (
      vietnameseVoices.find((voice) => {
        const name = voice.name.toLowerCase();
        return preferredNames.some((keyword) => name.includes(keyword));
      }) ||
      vietnameseVoices[0] ||
      null
    );
  }, []);

  const playNeuralVietnameseTts = useCallback(async (text: string) => {
    const blob = await RobotAPI.voiceTts(text);
    const url = URL.createObjectURL(blob);
    try {
      const audio = new Audio(url);
      audio.preload = "auto";
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => resolve();
        audio.onerror = () => reject(new Error("Neural TTS audio failed"));
        const playPromise = audio.play();
        if (playPromise) {
          playPromise.catch(reject);
        }
      });
    } finally {
      URL.revokeObjectURL(url);
    }
  }, []);

  const speakWithSystemVietnamese = useCallback((text: string) => {
    const synth = window.speechSynthesis;
    if (!synth) return;

    const utterance = new SpeechSynthesisUtterance(text);
    const voice = pickVietnameseFemaleVoice(synth.getVoices());
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang || "vi-VN";
    } else {
      utterance.lang = "vi-VN";
    }
    utterance.rate = 0.92;
    utterance.pitch = voice ? 1.18 : 1;
    utterance.volume = 1;

    synth.cancel();
    synth.resume();
    synth.speak(utterance);
  }, [pickVietnameseFemaleVoice]);

  const speakReply = useCallback((text: string) => {
    if (typeof window === "undefined" || !text.trim()) return;

    void playNeuralVietnameseTts(text)
      .catch((error) => {
        console.warn("Neural Vietnamese TTS failed:", error);
        const synth = window.speechSynthesis;
        if (!synth) return;
        const voice = pickVietnameseFemaleVoice(synth.getVoices());
        if (voice) {
          speakWithSystemVietnamese(text);
        } else {
          setCommandError("Khong tim thay giong nu tieng Viet. Hay khoi dong lai backend de dung vi-VN-HoaiMyNeural.");
        }
      });

  }, [
    pickVietnameseFemaleVoice,
    playNeuralVietnameseTts,
    speakWithSystemVietnamese,
  ]);

  const sendVoiceCommand = useCallback(
    async (spokenText?: string) => {
      const text = (spokenText ?? commandText).trim();

      if (!text) {
        setCommandError("Khong nhan duoc noi dung lenh.");
        return;
      }

      const activeRobotAddr = robotAddr.trim() || dogServer.trim();
      if (!activeRobotAddr) {
        setCommandError("Thieu robot address.");
        speakReply("Em ch\u01b0a th\u1ea5y \u0111\u1ecba ch\u1ec9 robot. Anh vui l\u00f2ng k\u1ebft n\u1ed1i robot tr\u01b0\u1edbc r\u1ed3i n\u00f3i l\u1ea1i l\u1ec7nh gi\u00fap em.");
        return;
      }

      try {
        setIsSendingCommand(true);
        setCommandError("");
        setCommandResult(null);

        const result = await RobotAPI.textCommand(text, activeRobotAddr);
        setCommandResult(result);
        setBackendSyncError("");
        speakReply(
          result?.reply_text ||
          result?.result?.bridge_reply_text ||
          "Em \u0111\u00e3 nh\u1eadn l\u1ec7nh v\u00e0 g\u1eedi sang robot."
        );
        await Promise.allSettled([fetchPatrolStatus(), fetchSlamState()]);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Gui lenh that bai";
        setCommandError(message);
        speakReply(`Em ch\u01b0a th\u1ef1c hi\u1ec7n \u0111\u01b0\u1ee3c l\u1ec7nh n\u00e0y. L\u00fd do l\u00e0: ${message}`);
      } finally {
        setIsSendingCommand(false);
      }
    },
    [commandText, dogServer, fetchPatrolStatus, fetchSlamState, robotAddr, speakReply]
  );

  const startListening = async () => {
    const SpeechRecognition =
      typeof window !== "undefined"
        ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
        : null;

    if (!SpeechRecognition) {
      window.alert("Trinh duyet nay khong ho tro speech recognition.");
      return;
    }

    try {
      if (
        typeof window !== "undefined" &&
        !window.isSecureContext &&
        window.location.hostname !== "localhost" &&
        window.location.hostname !== "127.0.0.1"
      ) {
        throw new Error("Microphone chi hoat dong tren localhost hoac HTTPS.");
      }

      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Trinh duyet khong ho tro truy cap microphone.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());

      const recognition = new SpeechRecognition();
      recognition.lang = "vi-VN";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        pendingTranscriptRef.current = "";
        setIsListening(true);
        setCommandError("");
      };

      recognition.onresult = (event: any) => {
        const transcript = event?.results?.[0]?.[0]?.transcript || "";
        setCommandText(transcript);
        pendingTranscriptRef.current = transcript;
      };

      recognition.onerror = (event: any) => {
        const errorCode = event?.error || "";
        const errorMessage =
          errorCode === "audio-capture"
            ? "Khong lay duoc microphone. Hay kiem tra mic, quyen truy cap mic cua browser, va thu mo frontend bang localhost hoac HTTPS."
            : errorCode === "not-allowed"
              ? "Browser dang chan microphone. Hay cap quyen Microphone cho trang nay."
              : errorCode === "no-speech"
                ? "Khong nghe thay giong noi. Hay thu noi lai gan microphone hon."
                : errorCode || "Khong the nhan giong noi";
        setCommandError(errorMessage);
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
        const transcript = pendingTranscriptRef.current.trim();
        pendingTranscriptRef.current = "";
        if (transcript) {
          window.setTimeout(() => {
            void sendVoiceCommand(transcript);
          }, 250);
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (error) {
      setIsListening(false);
      const name = error instanceof DOMException ? error.name : "";
      const message =
        name === "NotAllowedError" || name === "SecurityError"
          ? "Browser dang chan microphone. Hay cap quyen Microphone cho trang nay."
          : name === "NotFoundError" || name === "DevicesNotFoundError"
            ? "Khong tim thay microphone tren may nay."
            : name === "NotReadableError" || name === "TrackStartError"
              ? "Microphone dang bi ung dung khac su dung hoac thiet bi khong san sang."
              : error instanceof Error
                ? error.message
                : "Khong the bat microphone";
      setCommandError(message);
    }
  };

  const stopListening = () => {
    try {
      recognitionRef.current?.stop?.();
    } catch { }
    setIsListening(false);
  };

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop?.();
      } catch { }
    };
  }, []);

  const slamMapSrc = RobotAPI.slamMapUrl(mapReloadKey);
  const lidarActive = Boolean(
    controlStatus?.lidar_running ||
    controlStatus?.lidar?.running ||
    slamState?.status?.lidar_running ||
    slamState?.status?.planner_ok === true ||
    slamState?.status?.slam_ok === true ||
    slamState?.pose?.ok === true ||
    slamState?.scan?.ok === true
  );
  const robotFps = robotStatus?.telemetry?.fps;
  const pointNames = Object.keys(savedPoints || {}).sort();
  const cameraTelemetryLive = Boolean(
    qrPosition?.timestamp ||
    qrState?.timestamp ||
    (qrState?.ok && qrState.items)
  );
  const activePatrolPointName =
    patrolMission?.points?.[patrolMission.current_index] ??
    patrolMission?.points?.[0] ??
    null;
  const obstacle = slamState?.nearest_obstacle_ahead ?? null;

  const planningHeadline =
    slamState?.status?.planner_ok === true
      ? "Planner is active"
      : slamState?.status?.slam_ok === false
        ? "SLAM is offline"
        : "Waiting for navigation data";

  const poseText = slamState?.pose
    ? `${slamState.pose.x.toFixed(2)}, ${slamState.pose.y.toFixed(2)}`
    : "No pose";

  const slamConnectionText =
    slamState?.status?.slam_ok !== undefined
      ? String(slamState.status.slam_ok)
      : "No data";

  const tfConnectionText =
    slamState?.status?.tf_ok !== undefined
      ? String(slamState.status.tf_ok)
      : "No data";

  const obstacleText = obstacle ? `${obstacle.dist.toFixed(2)} m` : "Clear";

  return (
    <div className="flex h-full min-h-screen bg-[var(--background)]">
      <div className="relative flex flex-1 flex-col gap-5 overflow-y-auto p-6">
        <h1 className="gradient-title text-center text-2xl">Autonomous Control</h1>

        <button onClick={() => setSidebarOpen((open) => !open)}
          className="cursor-pointer absolute right-4 top-5 hidden items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs font-semibold text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] lg:inline-flex"
        >
          {sidebarOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
          {sidebarOpen ? "Hide panel" : "Show panel"}
        </button>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <CameraPanel
            cameraReady={cameraReady}
            cameraError={cameraError}
            cameraTelemetryLive={cameraTelemetryLive}
            robotFps={robotFps}
            videoSrc={RobotAPI.qrVideoFeedUrl()}
            onLoad={() => {
              setCameraReady(true);
              setCameraError(false);
            }}
            onError={() => {
              setCameraReady(false);
              setCameraError(true);
            }}
          />

          <MapPanel
            mapMode={mapMode}
            slamDisplayAngle={slamDisplayAngle}
            slamMapSrc={slamMapSrc}
            lidarUrl={lidarUrl}
            lidarActive={lidarActive}
            lidarBusy={lidarBusy}
            lidarControlError={lidarError}
            isModalOpen={mapModalOpen}
            navPlacementMode={navPlacementMode}
            hasPendingPlacement={Boolean(pendingPlacement)}
            showRobot={showRobot}
            showPath={showPath}
            showGrid={showGrid}
            mapImgRef={mapImgRef}
            overlayRef={overlayRef}
            modalMapImgRef={modalMapImgRef}
            modalOverlayRef={modalOverlayRef}
            onSetMapMode={setMapMode}
            onOpenModal={() => setMapModalOpen(true)}
            onCloseModal={() => setMapModalOpen(false)}
            onSetNavPlacementMode={setNavPlacementMode}
            onCancelPlacement={() => setPendingPlacement(null)}
            onClearPath={clearPath}
            onToggleLidar={handleToggleLidar}
            onStartStatic={handleStartStatic}
            onToggleRobot={() => setShowRobot((v) => !v)}
            onTogglePath={() => setShowPath((v) => !v)}
            onToggleGrid={() => setShowGrid((v) => !v)}
            onResetView={resetSlamView}
            onRotateLeft={rotateSlamViewLeft}
            onRotateRight={rotateSlamViewRight}
            onSlamImageClick={(event, isModal) =>
              handleSlamMapClick(event, isModal)
            }
            drawSlamOverlay={drawSlamOverlay}
          />
        </div>

        
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <SavedPointsPanel
            isDark={isDark}
            pointNames={pointNames}
            savedPoints={savedPoints}
            pointActionLoading={pointActionLoading}
            patrolRunning={patrolRunning}
            activePatrolPointName={activePatrolPointName}
            onCreatePoint={createPointFromObstacle}
            onStartPatrol={startPatrolAll}
            onStopNavigation={clearPath}
            onDeleteLast={deleteLastPoint}
            onClearAll={clearAllPoints}
            onGoToPoint={goToPoint}
            onDeletePoint={deletePoint}
          />

          <VoiceCommandPanel
            isDark={isDark}
            commandText={commandText}
            isSendingCommand={isSendingCommand}
            commandResult={commandResult}
            commandError={commandError}
            isListening={isListening}
            onStartListening={startListening}
            onStopListening={stopListening}
          />
        </div>
      </div>

      {sidebarOpen ? (
        <SidebarPanel
          isDark={isDark}
          planningHeadline={planningHeadline}
          poseText={poseText}
          robotAddr={dogServer.trim()}
          backendConnected={connected}
          backendSyncError={backendSyncError}
          qrPosition={qrPosition}
          qrPositionError={qrPositionError}
          slamError={slamError}
          qrError={qrError}
          obstacleText={obstacleText}
          slamConnectionText={slamConnectionText}
          tfConnectionText={tfConnectionText}
        />
      ) : null}
    </div>
  );
}
