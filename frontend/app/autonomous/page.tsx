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
  PointsResponse,
  QrPositionData,
  QrStateData,
  RobotStatusResponse,
  SlamRenderInfo,
  SlamStateData,
} from "./types";

function getSlamBaseUrl(server: string) {
  try {
    const url = new URL(server);
    return `${url.protocol}//${url.hostname}:8080`;
  } catch {
    return "";
  }
}

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

function normalizeAngle(angle: number) {
  return Math.atan2(Math.sin(angle), Math.cos(angle));
}

function findNearestObstacleAhead(state: SlamStateData | null) {
  if (!state?.pose || !state?.scan?.points?.length) return null;

  const pose = state.pose;
  const yaw = pose.theta || 0;

  let best: { x: number; y: number; dist: number } | null = null;
  let bestDist = Infinity;

  for (const point of state.scan.points) {
    const dx = point.x - pose.x;
    const dy = point.y - pose.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (!isFinite(dist) || dist < 0.05) continue;

    const angle = Math.atan2(dy, dx);
    const diff = Math.abs(normalizeAngle(angle - yaw));

    if (diff <= 0.35 && dist < bestDist) {
      bestDist = dist;
      best = { x: point.x, y: point.y, dist };
    }
  }

  return best;
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

  const [cameraError, setCameraError] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [mapReloadKey, setMapReloadKey] = useState(0);
  const [mapModalOpen, setMapModalOpen] = useState(false);

  const [savedPoints, setSavedPoints] = useState<PointsResponse>({});
  const [pointActionLoading, setPointActionLoading] = useState(false);

  const mapImgRef = useRef<HTMLImageElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const modalMapImgRef = useRef<HTMLImageElement | null>(null);
  const modalOverlayRef = useRef<HTMLCanvasElement | null>(null);

  const [robotAddr, setRobotAddr] = useState(
    () => getSelectedRobotAddr() || DEFAULT_DOG_SERVER
  );
  const [commandText, setCommandText] = useState("");
  const [isSendingCommand, setIsSendingCommand] = useState(false);
  const [commandResult, setCommandResult] = useState<any | null>(null);
  const [commandError, setCommandError] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [dogServer, setDogServer] = useState(
    () => getSelectedRobotAddr() || DEFAULT_DOG_SERVER
  );

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
  const slamBaseUrl = useMemo(() => getSlamBaseUrl(dogServer), [dogServer]);
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

  const fetchSlamState = useCallback(async () => {
    if (!slamBaseUrl) return;

    try {
      const res = await fetch(`${slamBaseUrl}/state`, { cache: "no-store" });
      if (!res.ok) throw new Error("Khong lay duoc /state");
      const data = await res.json();
      setSlamState(data);
      setSlamError("");
    } catch (error) {
      setSlamState(null);
      setSlamError(error instanceof Error ? error.message : "Khong lay duoc /state");
    }
  }, [slamBaseUrl]);

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
    if (!slamBaseUrl) return;

    try {
      const res = await fetch(`${slamBaseUrl}/points`, { cache: "no-store" });
      if (!res.ok) throw new Error("Khong lay duoc /points");
      const data = await res.json();
      setSavedPoints(data || {});
    } catch {
      setSavedPoints({});
    }
  }, [slamBaseUrl]);

  useEffect(() => {
    fetchRobotStatus();
    fetchSlamState();
    fetchQrState();
    fetchQrPosition();
    fetchControlStatus();
    fetchPoints();

    const timers = [
      setInterval(fetchRobotStatus, 3000),
      setInterval(fetchSlamState, 700),
      setInterval(fetchQrState, 700),
      setInterval(fetchQrPosition, 700),
      setInterval(fetchControlStatus, 3000),
      setInterval(fetchPoints, 2500),
      setInterval(() => setMapReloadKey((value) => value + 1), 1000),
    ];

    return () => timers.forEach(clearInterval);
  }, [
    fetchRobotStatus,
    fetchSlamState,
    fetchQrState,
    fetchQrPosition,
    fetchControlStatus,
    fetchPoints,
  ]);

  const clearPath = useCallback(async () => {
    if (!slamBaseUrl) return;
    try {
      await fetch(`${slamBaseUrl}/clear_path`);
      setPendingPlacement(null);
      await fetchSlamState();
    } catch { }
  }, [slamBaseUrl, fetchSlamState]);

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
        const endpoint =
          navPlacementMode === "goal" ? "set_goal_pose" : "set_initial_pose";

        await fetch(
          `${slamBaseUrl}/${endpoint}?x=${encodeURIComponent(
            pendingPlacement.x
          )}&y=${encodeURIComponent(pendingPlacement.y)}&yaw=${encodeURIComponent(
            yaw
          )}`
        );

        setPendingPlacement(null);
        await fetchSlamState();
      } catch { }
    },
    [mapMode, slamState, pendingPlacement, navPlacementMode, slamBaseUrl, fetchSlamState]
  );

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

        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 13px Arial";
        ctx.fillText(name, px.x + 8, px.y - 8);
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
    const obstacle = findNearestObstacleAhead(slamState);
    const qrText = (qrState?.ok && qrState.items?.length
      ? qrState.items[0].text
      : null);
    const pointName = (qrText || "POINT").trim() || "POINT";

    // CASE 1: Không có obstacle → Attempt thất bại
    if (!obstacle || !slamBaseUrl) {
      window.alert("Chua co obstacle phia truoc de luu.");
      await RobotAPI.logQRAttempt({
        name: pointName,
        success: false,
        reason: "no_obstacle",
      }).catch(() => { });
      return;
    }

    // CASE 2: Point đã tồn tại → không tính Attempt
    if (savedPoints[pointName]) {
      window.alert(`Diem ${pointName} da ton tai.`);
      return;
    }

    try {
      setPointActionLoading(true);

      // Lưu vào ROS
      await fetch(`${slamBaseUrl}/points`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: pointName, x: obstacle.x, y: obstacle.y, yaw: 0.0 }),
      });

      // CASE 3: Lưu ROS thành công → Attempt + Success
      await RobotAPI.logQRAttempt({
        name: pointName,
        success: true,
      }).catch(() => { });

      await fetchPoints();
    } catch {
      // CASE 4: Lưu ROS thất bại → Attempt không thành công
      await RobotAPI.logQRAttempt({
        name: pointName,
        success: false,
        reason: "ros_error",
      }).catch(() => { });
    } finally {
      setPointActionLoading(false);
    }
  };

  const deletePoint = async (name: string) => {
    if (!slamBaseUrl) return;
    try {
      setPointActionLoading(true);
      await fetch(`${slamBaseUrl}/delete_point`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
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
      setPointActionLoading(false);
    }
  };

  const startListening = () => {
    const SpeechRecognition =
      typeof window !== "undefined"
        ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
        : null;

    if (!SpeechRecognition) {
      window.alert("Trinh duyet nay khong ho tro speech recognition.");
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = "vi-VN";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setIsListening(true);
        setCommandError("");
      };

      recognition.onresult = (event: any) => {
        const transcript = event?.results?.[0]?.[0]?.transcript || "";
        setCommandText(transcript);
      };

      recognition.onerror = (event: any) => {
        setCommandError(event?.error || "Khong the nhan giong noi");
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (error) {
      setIsListening(false);
      setCommandError(
        error instanceof Error ? error.message : "Khong the bat microphone"
      );
    }
  };

  const stopListening = () => {
    try {
      recognitionRef.current?.stop?.();
    } catch { }
    setIsListening(false);
  };

  const sendVoiceCommand = async () => {
    const text = commandText.trim();

    if (!text) {
      setCommandError("Vui long nhap hoac doc lenh.");
      return;
    }

    if (!robotAddr.trim()) {
      setCommandError("Thieu robot address.");
      return;
    }

    try {
      setIsSendingCommand(true);
      setCommandError("");
      setCommandResult(null);

      const result = await RobotAPI.textCommand(text, robotAddr.trim());
      setCommandResult(result);
    } catch (error) {
      setCommandError(error instanceof Error ? error.message : "Gui lenh that bai");
    } finally {
      setIsSendingCommand(false);
    }
  };

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop?.();
      } catch { }
    };
  }, []);

  const slamMapSrc = `${slamBaseUrl}/map.png?v=${mapReloadKey}`;
  const lidarActive = Boolean(
    controlStatus?.lidar_running ?? controlStatus?.lidar?.running ?? false
  );
  const robotFps = robotStatus?.telemetry?.fps;
  const pointNames = Object.keys(savedPoints || {}).sort();
  const obstacle = findNearestObstacleAhead(slamState);

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
            onCreatePoint={createPointFromObstacle}
            onStartPatrol={startPatrolAll}
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
            onCommandTextChange={setCommandText}
            onStartListening={startListening}
            onStopListening={stopListening}
            onSendVoiceCommand={sendVoiceCommand}
          />
        </div>
      </div>

      {sidebarOpen ? (
        <SidebarPanel
          isDark={isDark}
          planningHeadline={planningHeadline}
          poseText={poseText}
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
