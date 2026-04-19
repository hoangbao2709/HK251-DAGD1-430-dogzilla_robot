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
    MapViewMode,
    PointsResponse,
    QrPositionData,
    QrStateData,
    RobotStatusResponse,
    SlamRenderInfo,
    SlamStateData,
} from "./types";

function radToDeg(rad: number) {
    return (rad * 180) / Math.PI;
}

function mapToPixel(
    x: number,
    y: number,
    renderInfo: SlamRenderInfo,
    width: number,
    height: number
) {
    const pxCells = (x - renderInfo.origin_x) / renderInfo.resolution;
    const pyCells =
        renderInfo.height_cells - (y - renderInfo.origin_y) / renderInfo.resolution;

    const scaleX = width / renderInfo.width_cells;
    const scaleY = height / renderInfo.height_cells;

    return {
        x: pxCells * scaleX,
        y: pyCells * scaleY,
    };
}

function normalizeAngle(angle: number) {
    return Math.atan2(Math.sin(angle), Math.cos(angle));
}

function findNearestObstacleAhead(state: SlamStateData | null) {
    if (!state?.pose || !state?.scan?.points?.length) {
        return null;
    }

    const pose = state.pose;
    const yaw = pose.theta || 0;

    let best: { x: number; y: number; dist: number } | null = null;
    let bestDist = Infinity;

    for (const point of state.scan.points) {
        if (typeof point.x !== "number" || typeof point.y !== "number") continue;

        const dx = point.x - pose.x;
        const dy = point.y - pose.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (!isFinite(dist) || dist < 0.05) continue;

        const angle = Math.atan2(dy, dx);
        const diff = Math.abs(normalizeAngle(angle - yaw));

        if (diff <= 0.35 && dist < bestDist) {
            bestDist = dist;
            best = {
                x: point.x,
                y: point.y,
                dist,
            };
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
    const [slamLoading, setSlamLoading] = useState(true);
    const [slamError, setSlamError] = useState("");

    const [qrState, setQrState] = useState<QrStateData | null>(null);
    const [qrError, setQrError] = useState("");
    const [qrPosition, setQrPosition] = useState<QrPositionData | null>(null);
    const [qrPositionError, setQrPositionError] = useState("");
    const [controlStatus, setControlStatus] = useState<ControlStatusResponse | null>(null);

    const [cameraError, setCameraError] = useState(false);
    const [cameraReady, setCameraReady] = useState(false);
    const [mapReloadKey, setMapReloadKey] = useState(0);
    const [mapModalOpen, setMapModalOpen] = useState(false);
    const [lidarFrameNonce, setLidarFrameNonce] = useState(0);

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
    const [mapViewMode, setMapViewMode] = useState<MapViewMode>("lidar");
    const [lidarBusy, setLidarBusy] = useState(false);
    const [lidarEnabled, setLidarEnabled] = useState(false);
    const [lidarStatusReady, setLidarStatusReady] = useState(false);
    const [lidarCommandError, setLidarCommandError] = useState("");
    const [slamDisplayAngle, setSlamDisplayAngle] = useState(0);

    const recognitionRef = useRef<any>(null);
    const lastLidarRunningRef = useRef(false);
    const lidarPollInFlightRef = useRef(false);
    const lidarFailureCountRef = useRef(0);

    useEffect(() => {
        setThemeMounted(true);
    }, []);

    const isDark = themeMounted && resolvedTheme === "dark";

    useEffect(() => {
        setRobotAddr(getSelectedRobotAddr() || DEFAULT_DOG_SERVER);
    }, []);

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
        try {
            const json = await RobotAPI.slamState();
            const data = json?.data ?? json ?? null;
            setSlamState(data);
            setSlamError("");
        } catch (error) {
            setSlamState(null);
            setSlamError(
                error instanceof Error ? error.message : "Khong lay duoc du lieu lidar"
            );
        } finally {
            setSlamLoading(false);
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

            const running = Boolean(data?.lidar_running ?? data?.lidar?.running ?? false);
            return running;
        } catch {
            setControlStatus(null);
            return false;
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

    const handleLidarToggle = useCallback(
        async (nextEnabled: boolean) => {
            if (lidarBusy) return;

            try {
                setLidarBusy(true);
                setLidarCommandError("");
                await RobotAPI.lidar(nextEnabled ? "start" : "stop");
                lidarFailureCountRef.current = 0;
                setLidarEnabled(nextEnabled);
                setLidarStatusReady(true);

                if (nextEnabled) {
                    setLidarFrameNonce((value) => value + 1);
                    fetchSlamState();
                } else {
                    setSlamState(null);
                }
            } catch (error) {
                setLidarCommandError(
                    error instanceof Error ? error.message : "LiDAR command failed"
                );
            } finally {
                setLidarBusy(false);
            }
        },
        [fetchSlamState, lidarBusy]
    );

    const resetSlamView = useCallback(() => {
        setSlamDisplayAngle(0);
    }, []);

    const rotateSlamView = useCallback((deltaDeg: number) => {
        setSlamDisplayAngle((value) => value + deltaDeg);
    }, []);

    const autoAlignSlamView = useCallback(() => {
        const yaw = slamState?.pose?.theta;
        if (typeof yaw !== "number" || !isFinite(yaw)) {
            return;
        }

        setSlamDisplayAngle(radToDeg(yaw) - 90);
    }, [slamState]);

    useEffect(() => {
        let active = true;

        const load = async () => {
            if (!active) return;
            await Promise.all([
                fetchRobotStatus(),
                fetchControlStatus(),
                fetchSlamState(),
                fetchQrState(),
                fetchQrPosition(),
                fetchPoints(),
            ]);
        };

        load();

        const statusTimer = setInterval(fetchRobotStatus, 3000);
        const controlStatusTimer = setInterval(fetchControlStatus, 3000);
        const slamTimer = setInterval(fetchSlamState, 700);
        const qrTimer = setInterval(fetchQrState, 700);
        const qrPositionTimer = setInterval(fetchQrPosition, 700);
        const pointsTimer = setInterval(fetchPoints, 2500);
        const mapTimer = setInterval(() => {
            setMapReloadKey((value) => value + 1);
        }, 1000);

        return () => {
            active = false;
            clearInterval(statusTimer);
            clearInterval(controlStatusTimer);
            clearInterval(slamTimer);
            clearInterval(qrTimer);
            clearInterval(qrPositionTimer);
            clearInterval(pointsTimer);
            clearInterval(mapTimer);
        };
    }, [
        fetchControlStatus,
        fetchPoints,
        fetchQrPosition,
        fetchQrState,
        fetchRobotStatus,
        fetchSlamState,
    ]);

    const drawSlamOverlay = useCallback(() => {
        const drawToCanvas = (
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

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            if (!slamState?.pose || !slamState?.render_info) {
                ctx.fillStyle = "rgba(255,216,77,0.95)";
                ctx.font = "bold 16px Arial";
                ctx.fillText("Waiting for /slam/state ...", 18, 28);
                return;
            }

            const renderInfo = slamState.render_info;
            const robot = mapToPixel(
                slamState.pose.x,
                slamState.pose.y,
                renderInfo,
                canvas.width,
                canvas.height
            );

            for (const [name, marker] of Object.entries(savedPoints || {})) {
                const point = mapToPixel(
                    marker.x,
                    marker.y,
                    renderInfo,
                    canvas.width,
                    canvas.height
                );

                ctx.shadowColor = "rgba(0,255,157,0.35)";
                ctx.shadowBlur = 14;
                ctx.strokeStyle = "#00ff9d";
                ctx.lineWidth = 3;
                ctx.beginPath();
                ctx.arc(point.x, point.y, 16, 0, Math.PI * 2);
                ctx.stroke();

                ctx.fillStyle = "#00ff9d";
                ctx.beginPath();
                ctx.arc(point.x, point.y, 8, 0, Math.PI * 2);
                ctx.fill();
                ctx.shadowBlur = 0;

                ctx.fillStyle = "#ffffff";
                ctx.font = "bold 14px Arial";
                ctx.fillText(name, point.x + 14, point.y - 8);
            }

            ctx.fillStyle = "#00d9ff";
            ctx.beginPath();
            ctx.arc(robot.x, robot.y, 8, 0, Math.PI * 2);
            ctx.fill();

            ctx.strokeStyle = "rgba(0,217,255,0.48)";
            ctx.lineWidth = 3;
            ctx.shadowColor = "rgba(0,217,255,0.28)";
            ctx.shadowBlur = 12;
            ctx.beginPath();
            ctx.arc(robot.x, robot.y, 16, 0, Math.PI * 2);
            ctx.stroke();
            ctx.shadowBlur = 0;

            const yaw = slamState.pose.theta || 0;
            const length = 52;
            const endX = robot.x + Math.cos(yaw) * length;
            const endY = robot.y - Math.sin(yaw) * length;

            ctx.strokeStyle = "#ffe14d";
            ctx.lineWidth = 4;
            ctx.beginPath();
            ctx.moveTo(robot.x, robot.y);
            ctx.lineTo(endX, endY);
            ctx.stroke();

            ctx.fillStyle = "#00e5ff";
            ctx.strokeStyle = "rgba(0,40,60,0.95)";
            ctx.lineWidth = 3;
            ctx.font = "bold 15px Arial";
            ctx.strokeText("ROBOT", robot.x + 14, robot.y - 10);
            ctx.fillText("ROBOT", robot.x + 14, robot.y - 10);

            const obstacle = findNearestObstacleAhead(slamState);
            if (obstacle) {
                const obstaclePx = mapToPixel(
                    obstacle.x,
                    obstacle.y,
                    renderInfo,
                    canvas.width,
                    canvas.height
                );

                ctx.strokeStyle = "rgba(255,58,98,0.72)";
                ctx.lineWidth = 3;
                ctx.shadowColor = "rgba(255,58,98,0.32)";
                ctx.shadowBlur = 12;
                ctx.beginPath();
                ctx.moveTo(robot.x, robot.y);
                ctx.lineTo(obstaclePx.x, obstaclePx.y);
                ctx.stroke();
                ctx.shadowBlur = 0;

                ctx.fillStyle = "#ff2d78";
                ctx.beginPath();
                ctx.arc(obstaclePx.x, obstaclePx.y, 9, 0, Math.PI * 2);
                ctx.fill();

                ctx.strokeStyle = "rgba(255,255,255,0.5)";
                ctx.lineWidth = 3;
                ctx.beginPath();
                ctx.arc(obstaclePx.x, obstaclePx.y, 17, 0, Math.PI * 2);
                ctx.stroke();

                const currentQrText =
                    qrState?.ok && qrState.items?.length ? qrState.items[0].text : "NO_QR";

                ctx.fillStyle = "#ffea00";
                ctx.strokeStyle = "rgba(60,0,20,0.95)";
                ctx.lineWidth = 3;
                ctx.font = "bold 15px Arial";
                ctx.strokeText(currentQrText, obstaclePx.x + 14, obstaclePx.y - 9);
                ctx.fillText(currentQrText, obstaclePx.x + 14, obstaclePx.y - 9);
            }
        };

        drawToCanvas(overlayRef.current, mapImgRef.current);
        drawToCanvas(modalOverlayRef.current, modalMapImgRef.current);
    }, [qrState, savedPoints, slamState]);

    useEffect(() => {
        drawSlamOverlay();
    }, [drawSlamOverlay]);

    useEffect(() => {
        const onResize = () => drawSlamOverlay();
        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
    }, [drawSlamOverlay]);

    useEffect(() => {
        if (!mapModalOpen) return;

        const frame = window.requestAnimationFrame(() => {
            drawSlamOverlay();
        });

        return () => window.cancelAnimationFrame(frame);
    }, [drawSlamOverlay, mapModalOpen]);

    useEffect(() => {
        const isRunning = Boolean(
            controlStatus?.lidar_running ?? controlStatus?.lidar?.running ?? false
        );

        if (isRunning && !lastLidarRunningRef.current) {
            setLidarFrameNonce((value) => value + 1);
        }

        lastLidarRunningRef.current = isRunning;
    }, [controlStatus]);

    const createPointFromObstacle = async () => {
        const obstacle = findNearestObstacleAhead(slamState);
        if (!obstacle) {
            window.alert("Chua co obstacle phia truoc de luu.");
            return;
        }

        const name =
            (qrState?.ok && qrState.items?.length ? qrState.items[0].text : "POINT").trim() || "POINT";
        if (savedPoints[name]) {
            window.alert(`Diem ${name} da ton tai, khong the luu trung.`);
            return;
        }

        try {
            setPointActionLoading(true);
            await RobotAPI.createPoint({
                name,
                x: obstacle.x,
                y: obstacle.y,
                yaw: 0.0,
            });
            await fetchPoints();
            drawSlamOverlay();
            window.alert(`Da luu diem ${name}`);
        } catch (error) {
            window.alert(error instanceof Error ? error.message : "Luu diem that bai");
        } finally {
            setPointActionLoading(false);
        }
    };

    const deletePoint = async (name: string) => {
        try {
            setPointActionLoading(true);
            await RobotAPI.deletePoint(name);
            await fetchPoints();
            drawSlamOverlay();
        } catch (error) {
            window.alert(error instanceof Error ? error.message : "Xoa diem that bai");
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

        try {
            setPointActionLoading(true);
            for (const name of names) {
                await RobotAPI.deletePoint(name);
            }
            await fetchPoints();
            drawSlamOverlay();
        } catch (error) {
            window.alert(error instanceof Error ? error.message : "Xoa tat ca diem that bai");
        } finally {
            setPointActionLoading(false);
        }
    };

    const goToPoint = async (name: string) => {
        try {
            setPointActionLoading(true);
            await RobotAPI.goToPoint(name);
            window.alert(`Da gui lenh di toi diem ${name}`);
        } catch (error) {
            window.alert(error instanceof Error ? error.message : "Di toi diem that bai");
        } finally {
            setPointActionLoading(false);
        }
    };

    const robotFps = robotStatus?.telemetry?.fps;

    const pointNames = Object.keys(savedPoints || {}).sort();
    const obstacle = findNearestObstacleAhead(slamState);
    const planningHeadline =
        slamState?.status?.planner_ok === true
            ? "Planner is active"
            : slamState?.status?.slam_ok === false
              ? "SLAM is offline"
              : "Waiting for navigation data";
    const lidarUrl = useMemo(() => {
        try {
            const url = new URL(robotAddr.trim() || DEFAULT_DOG_SERVER);
            const host = url.hostname;
            const port = url.port;

            if (port === "9000" || port === "") {
                return `${url.protocol}//${host}:8080`;
            }

            if (port === "8080") {
                return url.origin.replace(/\/$/, "");
            }

            if (port === "9002") {
                return `${url.protocol}//${host}:9002/lidar/`;
            }

            return `${url.origin.replace(/\/$/, "")}/lidar/`;
        } catch {
            return "";
        }
    }, [robotAddr]);

    const lidarFrameUrl = useMemo(() => {
        if (!lidarUrl) return "";
        const separator = lidarUrl.includes("?") ? "&" : "?";
        return `${lidarUrl}${separator}frame=${lidarFrameNonce}`;
    }, [lidarFrameNonce, lidarUrl]);

    useEffect(() => {
        if (!connected || !lidarUrl) {
            setLidarEnabled(false);
            setLidarStatusReady(true);
            return;
        }

        let stop = false;

        const pingLidar = async () => {
            if (lidarPollInFlightRef.current) return;
            lidarPollInFlightRef.current = true;

            try {
                const res = await fetch(lidarUrl, { cache: "no-store" });
                if (stop) return;

                if (res.ok) {
                    lidarFailureCountRef.current = 0;
                    setLidarEnabled(true);
                    setLidarStatusReady(true);
                    setLidarCommandError("");
                } else {
                    throw new Error(`LiDAR HTTP ${res.status}`);
                }
            } catch {
                if (stop) return;

                lidarFailureCountRef.current += 1;
                setLidarStatusReady(true);

                if (lidarFailureCountRef.current >= 2) {
                    setLidarEnabled(false);
                }
            } finally {
                lidarPollInFlightRef.current = false;
            }
        };

        pingLidar();
        const timer = setInterval(pingLidar, 2500);

        return () => {
            stop = true;
            clearInterval(timer);
            lidarPollInFlightRef.current = false;
        };
    }, [connected, lidarUrl]);

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

    const slamMapSrc = RobotAPI.slamMapUrl(mapReloadKey);
    const poseText = slamState?.pose
        ? `${slamState.pose.x.toFixed(2)}, ${slamState.pose.y.toFixed(2)}`
        : "No pose";
    const slamConnectionText =
        slamState?.status?.slam_ok !== undefined ? String(slamState.status.slam_ok) : "No data";
    const tfConnectionText =
        slamState?.status?.tf_ok !== undefined ? String(slamState.status.tf_ok) : "No data";
    const obstacleText = obstacle ? `${obstacle.dist.toFixed(2)} m` : "Clear";

    return (
        <div className="flex h-full min-h-screen bg-[var(--background)]">
            <div className="relative flex flex-1 flex-col gap-5 overflow-y-auto p-6">
                <h1 className="gradient-title text-center text-2xl">Autonomous Control</h1>

                <button
                    onClick={() => setSidebarOpen((open) => !open)}
                    className="absolute right-4 top-5 hidden items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs font-semibold text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--foreground)] lg:inline-flex"
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
                        mapViewMode={mapViewMode}
                        lidarBusy={lidarBusy}
                        lidarEnabled={lidarEnabled}
                        lidarStatusReady={lidarStatusReady}
                        lidarCommandError={lidarCommandError}
                        lidarFrameUrl={lidarFrameUrl}
                        slamDisplayAngle={slamDisplayAngle}
                        slamMapSrc={slamMapSrc}
                        isModalOpen={mapModalOpen}
                        mapImgRef={mapImgRef}
                        overlayRef={overlayRef}
                        modalMapImgRef={modalMapImgRef}
                        modalOverlayRef={modalOverlayRef}
                        onToggleLidar={() => handleLidarToggle(!lidarEnabled)}
                        onSetMapViewMode={(mode) => setMapViewMode(mode)}
                        onOpenModal={() => setMapModalOpen(true)}
                        onCloseModal={() => setMapModalOpen(false)}
                        onResetSlamView={resetSlamView}
                        onRotateSlamView={rotateSlamView}
                        onAutoAlignSlamView={autoAlignSlamView}
                        onSetSlamDisplayAngle={setSlamDisplayAngle}
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
