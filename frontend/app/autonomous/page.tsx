"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { RobotAPI } from "@/app/lib/robotApi";
import { DEFAULT_DOG_SERVER } from "@/app/lib/robotApi";
import { getSelectedRobotAddr } from "@/app/lib/selectedRobot";
import {
    Bot,
    Wifi,
    WifiOff,
    AlertTriangle,
    Mic,
    Square,
    Send,
    PanelRightClose,
    PanelRightOpen,
} from "lucide-react";

type SlamPoint = {
    x: number;
    y: number;
};

type SlamPose = {
    x: number;
    y: number;
    theta: number;
};

type SlamRenderInfo = {
    origin_x: number;
    origin_y: number;
    resolution: number;
    width_cells: number;
    height_cells: number;
};

type SlamStatus = {
    slam_ok?: boolean;
    tf_ok?: boolean;
    planner_ok?: boolean;
    map_age_sec?: number;
    pose_age_sec?: number;
    lidar_running?: boolean;
};

type SlamStateData = {
    pose?: SlamPose;
    scan?: {
        points?: SlamPoint[];
    };
    render_info?: SlamRenderInfo;
    status?: SlamStatus;
};

type RobotTelemetry = {
    robot_connected?: boolean;
    battery?: number;
    fps?: number;
    system?: {
        cpu_percent?: number;
        ram?: string;
        disk?: string;
        ip?: string;
        time?: string;
    };
};

type RobotStatusResponse = {
    name?: string;
    floor?: string;
    status_text?: string;
    water_level?: number;
    battery?: number;
    telemetry?: RobotTelemetry;
};

type ControlStatusResponse = {
    lidar_running?: boolean;
    lidar?: {
        running?: boolean;
    };
};

type QrItem = {
    text: string;
    qr_type: string;
    angle_deg: number;
    distance_m: number;
    lateral_x_m: number;
    forward_z_m: number;
    target_x_m: number;
    target_z_m: number;
    direction: string;
};

type QrStateData = {
    ok?: boolean;
    items?: QrItem[];
};

type QrPositionData = {
    detected?: boolean;
    qr?: {
        text?: string;
        type?: string;
        direction?: string;
    };
    position?: {
        angle_deg?: number;
        angle_rad?: number;
        distance_m?: number;
        lateral_x_m?: number;
        forward_z_m?: number;
    };
    target?: {
        x_m?: number;
        z_m?: number;
        distance_m?: number;
    };
    image?: {
        center_px?: { x?: number; y?: number };
        corners?: number[][];
    };
    render_hint?: {
        suggested_max_range_m?: number;
    };
    timestamp?: number;
};

type MarkerPoint = {
    x: number;
    y: number;
    yaw?: number;
};

type PointsResponse = Record<string, MarkerPoint>;

type ApiEnvelope<T> = {
    success?: boolean;
    robot_id?: string;
    data?: T;
    result?: T;
    error?: string;
    log?: string;
};

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

function normalizeAngle(a: number) {
    return Math.atan2(Math.sin(a), Math.cos(a));
}

function findNearestObstacleAhead(state: SlamStateData | null) {
    if (!state?.pose || !state?.scan?.points?.length) {
        return null;
    }

    const pose = state.pose;
    const yaw = pose.theta || 0;

    let best: { x: number; y: number; dist: number } | null = null;
    let bestDist = Infinity;

    for (const p of state.scan.points) {
        if (typeof p.x !== "number" || typeof p.y !== "number") continue;

        const dx = p.x - pose.x;
        const dy = p.y - pose.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (!isFinite(dist) || dist < 0.05) continue;

        const angle = Math.atan2(dy, dx);
        const diff = Math.abs(normalizeAngle(angle - yaw));

        if (diff <= 0.35 && dist < bestDist) {
            bestDist = dist;
            best = {
                x: p.x,
                y: p.y,
                dist,
            };
        }
    }

    return best;
}

function StatBlock({
    value,
    label,
}: {
    value: string;
    label: string;
}) {
    return (
        <div>
            <div className="text-[var(--foreground)] font-semibold text-base break-words">{value}</div>
            <div className="text-[var(--muted)] text-[11px] tracking-widest uppercase mt-0.5">
                {label}
            </div>
        </div>
    );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
    return (
        <h3 className="text-[var(--muted)] text-xs font-semibold uppercase tracking-widest mb-3">
            {children}
        </h3>
    );
}

function DarkCard({
    children,
    className = "",
}: {
    children: React.ReactNode;
    className?: string;
}) {
    return <div className={`bg-[var(--surface)] rounded-xl p-4 border border-[var(--border)] ${className}`}>{children}</div>;
}

function TopDownQrView({ data }: { data: QrPositionData | null }) {
    const width = 260;
    const height = 260;
    const padding = 18;
    const baselineY = height - 18;

    const rangeM = useMemo(() => {
        const candidates = [
            data?.render_hint?.suggested_max_range_m,
            data?.position?.distance_m,
            data?.target?.distance_m,
            data?.position?.forward_z_m,
            data?.target?.z_m,
        ].filter((value): value is number => typeof value === "number" && isFinite(value));

        if (candidates.length === 0) return 3;
        const farthest = Math.max(...candidates);
        return Math.min(Math.max(farthest + 0.5, 2), 4);
    }, [data]);

    const toX = useCallback(
        (meters: number) => width / 2 + (meters / rangeM) * ((width / 2) - padding),
        [rangeM]
    );

    const toY = useCallback(
        (meters: number) => baselineY - (meters / rangeM) * (baselineY - padding),
        [baselineY, rangeM]
    );

    const qrPoint =
        typeof data?.position?.lateral_x_m === "number" &&
            typeof data?.position?.forward_z_m === "number"
            ? {
                x: toX(data.position.lateral_x_m),
                y: toY(data.position.forward_z_m),
            }
            : null;

    const targetPoint =
        typeof data?.target?.x_m === "number" && typeof data?.target?.z_m === "number"
            ? {
                x: toX(data.target.x_m),
                y: toY(data.target.z_m),
            }
            : null;

    return (
        <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-elev)] shadow-[inset_0_0_0_1px_rgba(80,140,255,0.06)]">
            <svg viewBox={`0 0 ${width} ${height}`} className="h-[220px] w-full">
                <rect x="0" y="0" width={width} height={height} fill="#081321" />

                {Array.from({ length: 6 }).map((_, row) => {
                    const y = padding + ((height - padding * 2) / 5) * row;
                    return (
                        <line
                            key={`row-${row}`}
                            x1="0"
                            y1={y}
                            x2={width}
                            y2={y}
                            stroke="rgba(59,130,246,0.12)"
                            strokeWidth="1"
                        />
                    );
                })}

                {Array.from({ length: 6 }).map((_, col) => {
                    const x = padding + ((width - padding * 2) / 5) * col;
                    return (
                        <line
                            key={`col-${col}`}
                            x1={x}
                            y1="0"
                            x2={x}
                            y2={height}
                            stroke="rgba(59,130,246,0.12)"
                            strokeWidth="1"
                        />
                    );
                })}

                <line
                    x1={width / 2}
                    y1={padding}
                    x2={width / 2}
                    y2={baselineY}
                    stroke="#f8dc53"
                    strokeWidth="2.5"
                    strokeOpacity="0.95"
                />

                {targetPoint ? (
                    <>
                        <line
                            x1={width / 2}
                            y1={baselineY}
                            x2={targetPoint.x}
                            y2={targetPoint.y}
                            stroke="rgba(34,211,238,0.75)"
                            strokeDasharray="5 5"
                        />
                        <circle cx={targetPoint.x} cy={targetPoint.y} r="6" fill="#22d3ee" />
                    </>
                ) : null}

                {qrPoint ? (
                    <>
                        <line
                            x1={width / 2}
                            y1={baselineY}
                            x2={qrPoint.x}
                            y2={qrPoint.y}
                            stroke="rgba(255,122,69,0.9)"
                            strokeWidth="2"
                        />
                        <circle cx={qrPoint.x} cy={qrPoint.y} r="7" fill="#ff7a45" />
                        <text
                            x={qrPoint.x}
                            y={Math.max(qrPoint.y - 10, 18)}
                            textAnchor="middle"
                            fill="#ffd560"
                            fontSize="10"
                            fontWeight="700"
                        >
                            {data?.qr?.text || "QR"}
                        </text>
                    </>
                ) : (
                    <text
                        x={width / 2}
                        y="34"
                        textAnchor="middle"
                        fill="#ff7f7f"
                        fontSize="11"
                        fontWeight="700"
                    >
                        QR NOT FOUND
                    </text>
                )}

                <circle cx={width / 2} cy={baselineY} r="10" fill="#22d3ee" />
                <circle
                    cx={width / 2}
                    cy={baselineY}
                    r="16"
                    fill="none"
                    stroke="rgba(34,211,238,0.45)"
                    strokeWidth="2"
                />
            </svg>
        </div>
    );
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

    const [savedPoints, setSavedPoints] = useState<PointsResponse>({});
    const [pointActionLoading, setPointActionLoading] = useState(false);

    const mapImgRef = useRef<HTMLImageElement | null>(null);
    const overlayRef = useRef<HTMLCanvasElement | null>(null);

    const [robotAddr, setRobotAddr] = useState(DEFAULT_DOG_SERVER);
    const [commandText, setCommandText] = useState("");
    const [isSendingCommand, setIsSendingCommand] = useState(false);
    const [commandResult, setCommandResult] = useState<any | null>(null);
    const [commandError, setCommandError] = useState("");
    const [isListening, setIsListening] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [mapViewMode, setMapViewMode] = useState<"lidar" | "slam">("lidar");
    const [lidarBusy, setLidarBusy] = useState(false);
    const [lidarEnabled, setLidarEnabled] = useState(false);
    const [lidarCommandError, setLidarCommandError] = useState("");

    const recognitionRef = useRef<any>(null);
    const hasAutoStartedLidarRef = useRef(false);

    useEffect(() => {
        setThemeMounted(true);
    }, []);

    const isDark = themeMounted && resolvedTheme === "dark";

    useEffect(() => {
        const selectedAddr = getSelectedRobotAddr();
        if (selectedAddr) {
            setRobotAddr(selectedAddr);
        }
    }, []);

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
                error instanceof Error ? error.message : "Không lấy được dữ liệu lidar"
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
                error instanceof Error ? error.message : "Không lấy được trạng thái QR"
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
                error instanceof Error ? error.message : "Không lấy được vị trí QR"
            );
        }
    }, []);

    const fetchControlStatus = useCallback(async () => {
        try {
            const json = await RobotAPI.controlStatus();
            const data = json?.data ?? json ?? null;
            setControlStatus(data);

            const running = Boolean(
                data?.lidar_running ?? data?.lidar?.running ?? false
            );
            setLidarEnabled(running);
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

    const handleLidarToggle = useCallback(async (nextEnabled: boolean) => {
        if (lidarBusy) return;

        try {
            setLidarBusy(true);
            setLidarCommandError("");
            await RobotAPI.lidar(nextEnabled ? "start" : "stop");
            setLidarEnabled(nextEnabled);
            if (nextEnabled) {
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
    }, [fetchSlamState, lidarBusy]);

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
            setMapReloadKey((v) => v + 1);
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
    }, [fetchControlStatus, fetchPoints, fetchQrPosition, fetchQrState, fetchRobotStatus, fetchSlamState]);

    useEffect(() => {
        if (!connected || !controlStatus || hasAutoStartedLidarRef.current) {
            return;
        }

        const running = Boolean(
            controlStatus.lidar_running ?? controlStatus.lidar?.running ?? false
        );
        hasAutoStartedLidarRef.current = true;
        if (!running) {
            handleLidarToggle(true);
        } else {
            setLidarEnabled(true);
        }
    }, [connected, controlStatus, handleLidarToggle]);

    const drawSlamOverlay = useCallback(() => {
        const canvas = overlayRef.current;
        const img = mapImgRef.current;

        if (!canvas || !img) return;

        const rect = img.getBoundingClientRect();
        if (!rect.width || !rect.height) return;

        canvas.width = rect.width;
        canvas.height = rect.height;
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;

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
            const pt = mapToPixel(
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
            ctx.arc(pt.x, pt.y, 16, 0, Math.PI * 2);
            ctx.stroke();

            ctx.fillStyle = "#00ff9d";
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 8, 0, Math.PI * 2);
            ctx.fill();
            ctx.shadowBlur = 0;

            ctx.fillStyle = "#ffffff";
            ctx.font = "bold 14px Arial";
            ctx.fillText(name, pt.x + 14, pt.y - 8);
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
        const len = 52;
        const endX = robot.x + Math.cos(yaw) * len;
        const endY = robot.y - Math.sin(yaw) * len;

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
            const obsPx = mapToPixel(
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
            ctx.lineTo(obsPx.x, obsPx.y);
            ctx.stroke();
            ctx.shadowBlur = 0;

            ctx.fillStyle = "#ff2d78";
            ctx.beginPath();
            ctx.arc(obsPx.x, obsPx.y, 9, 0, Math.PI * 2);
            ctx.fill();

            ctx.strokeStyle = "rgba(255,255,255,0.5)";
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(obsPx.x, obsPx.y, 17, 0, Math.PI * 2);
            ctx.stroke();

            const currentQrText = qrState?.ok && qrState.items?.length
                ? qrState.items[0].text
                : "NO_QR";

            ctx.fillStyle = "#ffea00";
            ctx.strokeStyle = "rgba(60,0,20,0.95)";
            ctx.lineWidth = 3;
            ctx.font = "bold 15px Arial";
            ctx.strokeText(currentQrText, obsPx.x + 14, obsPx.y - 9);
            ctx.fillText(currentQrText, obsPx.x + 14, obsPx.y - 9);
        }
    }, [qrState, savedPoints, slamState]);

    useEffect(() => {
        drawSlamOverlay();
    }, [drawSlamOverlay]);

    useEffect(() => {
        const onResize = () => drawSlamOverlay();
        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
    }, [drawSlamOverlay]);

    const createPointFromObstacle = async () => {
        const obstacle = findNearestObstacleAhead(slamState);
        if (!obstacle) {
            window.alert("Chưa có obstacle phía trước để lưu.");
            return;
        }

        const defaultName =
            qrState?.ok && qrState.items?.length ? qrState.items[0].text : "POINT";

        const name = window.prompt("Tên điểm cần lưu:", defaultName)?.trim();
        if (!name) return;

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
            window.alert(`Đã lưu điểm ${name}`);
        } catch (error) {
            window.alert(error instanceof Error ? error.message : "Lưu điểm thất bại");
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
            window.alert(error instanceof Error ? error.message : "Xóa điểm thất bại");
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

        if (!window.confirm("Xóa tất cả điểm đã lưu?")) return;

        try {
            setPointActionLoading(true);
            for (const name of names) {
                await RobotAPI.deletePoint(name);
            }
            await fetchPoints();
            drawSlamOverlay();
        } catch (error) {
            window.alert(error instanceof Error ? error.message : "Xóa tất cả điểm thất bại");
        } finally {
            setPointActionLoading(false);
        }
    };

    const goToPoint = async (name: string) => {
        try {
            setPointActionLoading(true);
            await RobotAPI.goToPoint(name);
            window.alert(`Đã gửi lệnh đi tới điểm ${name}`);
        } catch (error) {
            window.alert(error instanceof Error ? error.message : "Đi tới điểm thất bại");
        } finally {
            setPointActionLoading(false);
        }
    };
    const robotName = robotStatus?.name || "Robot A";
    const robotConnected = connected ? "Connected" : "Disconnected";
    const robotBattery = robotStatus?.telemetry?.battery ?? robotStatus?.battery;
    const robotFps = robotStatus?.telemetry?.fps;
    const robotFloor = robotStatus?.floor || "1st";
    const robotStatusText = robotStatus?.status_text || "Resting";
    const robotWaterLevel =
        robotStatus?.water_level !== undefined ? `${robotStatus.water_level}%` : "50%";

    const robotLocation =
        slamState?.pose != null
            ? `${slamState.pose.x.toFixed(3)}, ${slamState.pose.y.toFixed(3)}`
            : "No pose";

    const cleaningProgress =
        slamState?.status?.planner_ok !== undefined
            ? slamState.status.planner_ok
                ? "Planning active"
                : "Planner inactive"
            : "No data";

    const statusCards = [
        {
            label: "Robot",
            value: robotConnected,
        },
        {
            label: "Vision",
            value: cameraError ? "Unavailable" : "Online",
        },
        {
            label: "Battery",
            value: robotBattery !== undefined ? `${robotBattery}%` : "No data",
        },
        {
            label: "Planner",
            value:
                slamState?.status?.planner_ok !== undefined
                    ? slamState.status.planner_ok
                        ? "Active"
                        : "Idle"
                    : "No data",
        },
    ];

    const pointNames = Object.keys(savedPoints || {}).sort();
    const obstacle = findNearestObstacleAhead(slamState);
    const planningCards = [
        {
            label: "SLAM",
            value:
                slamState?.status?.slam_ok !== undefined
                    ? slamState.status.slam_ok
                        ? "Ready"
                        : "Offline"
                    : "No data",
        },
        {
            label: "TF",
            value:
                slamState?.status?.tf_ok !== undefined
                    ? slamState.status.tf_ok
                        ? "Synced"
                        : "Missing"
                    : "No data",
        },
        {
            label: "Planner",
            value:
                slamState?.status?.planner_ok !== undefined
                    ? slamState.status.planner_ok
                        ? "Active"
                        : "Idle"
                    : "No data",
        },
        {
            label: "Obstacle",
            value: obstacle ? `${obstacle.dist.toFixed(2)} m` : "Clear",
        },
    ];
    const quickCommands = [
        { label: "Đi đến A", value: "hãy cho robot đi đến điểm A" },
        { label: "Đi A, B, C", value: "hãy cho robot đi đến điểm A, B, C" },
        { label: "Stop", value: "dừng điều hướng" },
    ];

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
    const savedButtonClass = isDark
        ? "flex-1 rounded-full bg-[#10b981] px-3 py-2 text-xs font-semibold text-white"
        : "flex-1 rounded-full bg-[#10b981] px-3 py-2 text-xs font-semibold text-white";

    const voiceShellClass = isDark
        ? "space-y-5 bg-[#0f0822] shadow-[0_18px_40px_rgba(0,194,255,0.08)]"
        : "space-y-5 bg-[#fffdfd] shadow-[0_18px_40px_rgba(0,194,255,0.08)]";
    const voiceHeaderClass = isDark
        ? "flex flex-col gap-3 rounded-2xl border border-white/10 bg-[#18223b] px-4 py-3 lg:flex-row lg:items-end lg:justify-between"
        : "flex flex-col gap-3 rounded-2xl border border-[#d8cbff] bg-[#eef7ff] px-4 py-3 lg:flex-row lg:items-end lg:justify-between";
    const quickCommandClass = isDark
        ? "rounded-full border border-white/10 bg-[#26163b] px-3 py-1.5 text-xs font-medium text-white/80 transition hover:bg-[#322049] hover:text-white"
        : "rounded-full border border-[#d6c7ff] bg-[#f7f3ff] px-3 py-1.5 text-xs font-medium text-[#4c3b73] transition hover:bg-[#eef7ff] hover:text-[#1f1640]";
    const voicePanelClass = isDark
        ? "rounded-2xl border border-white/10 bg-[#160a28] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
        : "rounded-2xl border border-[#dacfff] bg-[#ffffff] p-4 shadow-[0_10px_24px_rgba(124,77,255,0.06)]";
    const voiceTextareaClass = isDark
        ? "min-h-[160px] w-full resize-none rounded-2xl border border-white/10 bg-[#12071f] px-4 py-4 text-base leading-6 text-white outline-none placeholder:text-white/35"
        : "min-h-[160px] w-full resize-none rounded-2xl border border-[#d8cbff] bg-[#fffdfd] px-4 py-4 text-base leading-6 text-[#1f1640] outline-none placeholder:text-[#9f96b8]";
    const voiceResultClass = isDark
        ? "rounded-2xl border border-white/10 bg-[#160a28] px-4 py-3"
        : "rounded-2xl border border-[#dacfff] bg-[#ffffff] px-4 py-3";
    const actionCardClass = isDark
        ? "rounded-2xl border border-white/10 bg-[#160a28] p-4"
        : "rounded-2xl border border-[#d8cbff] bg-[#ffffff] p-4";
    const quickPanelClass = isDark
        ? "rounded-2xl border border-white/10 bg-[#160a28] p-4"
        : "rounded-2xl border border-[#d8cbff] bg-[#ffffff] p-4";
    const sidebarShellClass = isDark
        ? "w-80 shrink-0 bg-[#0f0822] border-l border-white/10 flex flex-col gap-5 p-5 overflow-y-auto"
        : "w-80 shrink-0 bg-[#fffdfd] border-l border-[#dacfff] flex flex-col gap-5 p-5 overflow-y-auto";
    const sidebarCardClass = isDark
        ? "rounded-2xl bg-[#160a28] border border-white/10"
        : "rounded-2xl bg-[#ffffff] border border-[#dacfff]";
    const sidebarMiniCardClass = isDark
        ? "rounded-xl bg-[#241139] px-3 py-2"
        : "rounded-xl bg-[#f7f3ff] px-3 py-2";
    const sidebarLabelClass = isDark
        ? "text-[10px] uppercase tracking-[0.22em] text-white/55"
        : "text-[10px] uppercase tracking-[0.22em] text-[#705d94]";
    const sidebarValueClass = isDark
        ? "mt-2 text-sm font-semibold text-white"
        : "mt-2 text-sm font-semibold text-[#1f1640]";
    const sidebarMutedClass = isDark ? "text-white/55" : "text-[#705d94]";
    const lidarUrl = useMemo(() => {
        try {
            const url = new URL(robotAddr.trim() || DEFAULT_DOG_SERVER);
            const host = url.hostname;
            const port = url.port;

            if (host.endsWith("trycloudflare.com")) {
                return `${url.origin.replace(/\/$/, "")}/lidar/`;
            }

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

    const startListening = () => {
        const SpeechRecognition =
            typeof window !== "undefined"
                ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
                : null;

        if (!SpeechRecognition) {
            window.alert("Trình duyệt này không hỗ trợ speech recognition.");
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
                console.log("VOICE TRANSCRIPT =", transcript);
                setCommandText(transcript);
            };

            recognition.onerror = (event: any) => {
                setCommandError(event?.error || "Không thể nhận giọng nói");
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
                error instanceof Error ? error.message : "Không thể bật microphone"
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
            setCommandError("Vui lòng nhập hoặc đọc lệnh.");
            return;
        }

        if (!robotAddr.trim()) {
            setCommandError("Thiếu robot address.");
            return;
        }
        console.log("SEND VOICE COMMAND", {
            addr: robotAddr.trim(),
            text: commandText.trim(),
        });
        try {
            setIsSendingCommand(true);
            setCommandError("");
            setCommandResult(null);

            const result = await RobotAPI.textCommand(text, robotAddr.trim());
            setCommandResult(result);
        } catch (error) {
            setCommandError(
                error instanceof Error ? error.message : "Gửi lệnh thất bại"
            );
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
    return (
        <div className="flex h-full min-h-screen bg-[var(--background)]">
            <div className="relative flex-1 flex flex-col p-6 gap-5 overflow-y-auto">
                <h1 className="gradient-title text-center text-2xl">Autonomous Control</h1>

                <button
                    onClick={() => setSidebarOpen((open) => !open)}
                    className="absolute right-4 top-5 hidden lg:inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs font-semibold text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                >
                    {sidebarOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
                    {sidebarOpen ? "Hide panel" : "Show panel"}
                </button>

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                    <div>
                        <SectionLabel>Camera QR scan</SectionLabel>
                        <div className="bg-[var(--surface)] rounded-xl overflow-hidden border border-[var(--border)] relative min-h-[360px] xl:min-h-[560px]">
                            {!cameraReady ? (
                                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[linear-gradient(180deg,var(--surface),var(--surface-2))] px-4 text-center">
                                    <div className="h-16 w-16 rounded-full border border-[var(--border)] bg-[var(--surface-elev)] flex items-center justify-center shadow-sm">
                                        <Bot size={28} className="text-[var(--accent)]" />
                                    </div>
                                    <div>
                                        <p className="text-sm font-semibold text-[var(--foreground)]">
                                            Waiting for QR camera stream
                                        </p>
                                        <p className="mt-1 text-xs text-[var(--muted)]">
                                            The frame will appear here once the robot camera is available.
                                        </p>
                                    </div>
                                    <div className="mt-2 h-1.5 w-48 overflow-hidden rounded-full bg-[rgba(23,19,39,0.10)] dark:bg-white/10">
                                        <div className="h-full w-1/3 animate-pulse rounded-full bg-gradient-to-r from-[#FD749B] via-[#7C4DFF] to-[#00C2FF]" />
                                    </div>
                                </div>
                            ) : null}
                            <img
                                src={RobotAPI.qrVideoFeedUrl()}
                                alt="QR video feed"
                                className={`block h-auto w-full bg-[var(--surface-elev)] transition-opacity duration-300 ${
                                    cameraReady ? "opacity-100" : "opacity-0"
                                }`}
                                onLoad={() => {
                                    setCameraReady(true);
                                    setCameraError(false);
                                }}
                                onError={() => {
                                    setCameraReady(false);
                                    setCameraError(true);
                                }}
                            />
                            <span className="absolute top-3 left-4 text-green-400 font-mono font-bold text-sm tracking-wider">
                                FPS:{robotFps ?? "--"}
                            </span>
                        </div>
                        {cameraError ? (
                            <p className="text-red-300/80 text-xs mt-2">
                                Không tải được camera QR stream
                            </p>
                        ) : null}
                    </div>

                    <div>
                        <div className="space-y-4">
                            <div>
                                <div className="mb-3 flex items-center justify-between gap-3">
                                    <SectionLabel>SLAM map overlay</SectionLabel>
                                    <div className="flex flex-wrap items-center justify-end gap-2">
                                        <button
                                            onClick={() => handleLidarToggle(!lidarEnabled)}
                                            disabled={lidarBusy}
                                            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
                                                lidarEnabled
                                                    ? "bg-red-500 text-white hover:bg-red-400"
                                                    : "bg-emerald-500 text-black hover:bg-emerald-400"
                                            }`}
                                        >
                                            {lidarBusy
                                                ? lidarEnabled
                                                    ? "Stopping..."
                                                    : "Starting..."
                                                : lidarEnabled
                                                    ? "Stop LiDAR"
                                                    : "Start LiDAR"}
                                        </button>
                                        <div className="flex rounded-xl border border-[var(--border)] bg-[var(--surface)] p-1 text-xs">
                                            <button
                                                onClick={() => setMapViewMode("lidar")}
                                                className={`rounded-lg px-3 py-1.5 transition ${
                                                    mapViewMode === "lidar"
                                                        ? "bg-cyan-400 text-black font-semibold"
                                                        : "text-[var(--muted)]"
                                                }`}
                                            >
                                                LiDAR view
                                            </button>
                                            <button
                                                onClick={() => setMapViewMode("slam")}
                                                className={`rounded-lg px-3 py-1.5 transition ${
                                                    mapViewMode === "slam"
                                                        ? "bg-cyan-400 text-black font-semibold"
                                                        : "text-[var(--muted)]"
                                                }`}
                                            >
                                                SLAM overlay
                                            </button>
                                        </div>
                                    </div>
                                </div>
                                {lidarCommandError ? (
                                    <p className="mb-3 text-xs text-red-300/80">{lidarCommandError}</p>
                                ) : null}
                                <div className="bg-[var(--surface)] rounded-xl overflow-hidden border border-[var(--border)] relative aspect-square">
                                    {mapViewMode === "lidar" ? (
                                        lidarUrl ? (
                                            <iframe
                                                src={lidarUrl}
                                                title="LiDAR map"
                                                className="absolute inset-0 h-full w-full border-0 bg-[var(--surface-elev)]"
                                            />
                                        ) : (
                                            <div className="absolute inset-0 flex items-center justify-center bg-[var(--surface-elev)] text-xs text-[var(--muted)]">
                                                LiDAR URL unavailable
                                            </div>
                                        )
                                    ) : (
                                        <>
                                            <img
                                                ref={mapImgRef}
                                                src={RobotAPI.slamMapUrl(mapReloadKey)}
                                                alt="SLAM map"
                                                className="h-full w-full object-contain bg-[var(--surface-elev)]"
                                                onLoad={() => drawSlamOverlay()}
                                            />
                                            <canvas
                                                ref={overlayRef}
                                                className="absolute left-0 top-0 pointer-events-none"
                                            />
                                        </>
                                    )}

                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    <DarkCard className={savedShellClass}>
                        <div className={savedHeaderClass}>
                            <SectionLabel>Saved points</SectionLabel>
                            <div className="flex flex-wrap gap-2">
                                <button
                                    onClick={createPointFromObstacle}
                                    disabled={pointActionLoading}
                                    className="rounded-full bg-[#10b981] px-4 py-2 text-sm font-semibold text-white shadow-[0_10px_20px_rgba(11,183,111,0.22)] transition hover:bg-[#0ea56f] disabled:opacity-50"
                                >
                                    Save point
                                </button>
                                <button
                                    onClick={deleteLastPoint}
                                    disabled={pointActionLoading || pointNames.length === 0}
                                    className="rounded-full bg-[#ff5574] px-4 py-2 text-sm font-semibold text-white shadow-[0_10px_20px_rgba(255,59,87,0.18)] transition hover:bg-[#f43f5e] disabled:opacity-50"
                                >
                                    Delete last
                                </button>
                                <button
                                    onClick={clearAllPoints}
                                    disabled={pointActionLoading || pointNames.length === 0}
                                    className="rounded-full bg-[#f6c94c] px-4 py-2 text-sm font-semibold text-[#4a3200] shadow-[0_10px_20px_rgba(255,191,31,0.16)] transition hover:bg-[#eab308] disabled:opacity-50"
                                >
                                    Clear all
                                </button>
                            </div>
                        </div>

                        {pointNames.length === 0 ? (
                            <div className={savedEmptyClass}>
                                No saved points
                            </div>
                        ) : (
                        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
                            {pointNames.map((name) => {
                                const point = savedPoints[name];
                                return (
                                    <div
                                        key={name}
                                        className={savedPointCardClass}
                                    >
                                        <div className="space-y-4">
                                            <div>
                                                <div className={isDark ? "text-lg font-semibold text-white" : "text-lg font-semibold text-[#24163f]"}>{name}</div>
                                            </div>

                                            <div className="grid grid-cols-3 gap-3 text-xs text-[var(--muted)]">
                                                <div className={`${savedStatClass} ${savedStatFill} ${savedStatTone.x}`}>
                                                    <div className="text-[10px] uppercase tracking-widest text-[var(--muted-2)]">X</div>
                                                    <div className={isDark ? "mt-1 text-sm font-semibold text-white" : "mt-1 text-sm font-semibold text-[#1f1640]"}>
                                                        {Number(point.x).toFixed(3)}
                                                    </div>
                                                </div>
                                                <div className={`${savedStatClass} ${savedStatFill} ${savedStatTone.y}`}>
                                                    <div className="text-[10px] uppercase tracking-widest text-[var(--muted-2)]">Y</div>
                                                    <div className={isDark ? "mt-1 text-sm font-semibold text-white" : "mt-1 text-sm font-semibold text-[#1f1640]"}>
                                                        {Number(point.y).toFixed(3)}
                                                    </div>
                                                </div>
                                                <div className={`${savedStatClass} ${savedStatFill} ${savedStatTone.yaw}`}>
                                                    <div className="text-[10px] uppercase tracking-widest text-[var(--muted-2)]">Yaw</div>
                                                    <div className={isDark ? "mt-1 text-sm font-semibold text-white" : "mt-1 text-sm font-semibold text-[#1f1640]"}>
                                                        {Number(point.yaw || 0).toFixed(3)}
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => goToPoint(name)}
                                                    disabled={pointActionLoading}
                                                    className={savedButtonClass}
                                                >
                                                    Go to
                                                </button>
                                                <button
                                                    onClick={() => deletePoint(name)}
                                                    disabled={pointActionLoading}
                                                    className="flex-1 rounded-full bg-[#ff5574] px-3 py-2 text-xs font-semibold text-white shadow-[0_8px_18px_rgba(255,55,88,0.16)] transition hover:bg-[#f43f5e] disabled:opacity-50"
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

                    <DarkCard className={voiceShellClass}>
                        <div className={voiceHeaderClass}>
                            <div className="space-y-1">
                                <SectionLabel>Voice navigation command</SectionLabel>
                                <p className="max-w-2xl text-sm text-[#594d76] dark:text-[var(--muted)]">
                                    Gõ hoặc đọc lệnh điều hướng. `Enter` để gửi, `Shift+Enter` để xuống dòng.
                                </p>
                            </div>
                        </div>

                        <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
                            <div className="space-y-3">
                                <div className={voicePanelClass}>
                                    <div className="mb-2 flex items-center justify-between gap-3">
                                        <label className={isDark ? "text-xs uppercase tracking-[0.22em] text-white/55" : "text-xs uppercase tracking-[0.22em] text-[#705d94]"}>
                                            Command
                                        </label>
                                        <span
                                            className={`text-[11px] font-medium ${
                                                isListening ? "text-cyan-600 dark:text-cyan-400" : isDark ? "text-white/45" : "text-[#8d84a8]"
                                            }`}
                                        >
                                            {isListening ? "Listening" : "Idle"}
                                        </span>
                                    </div>

                                    <textarea
                                        value={commandText}
                                        onChange={(e) => setCommandText(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter" && !e.shiftKey) {
                                                e.preventDefault();
                                                sendVoiceCommand();
                                            }
                                        }}
                                        placeholder="Hãy cho robot đi đến điểm A"
                                        className={voiceTextareaClass}
                                    />

                                    <div className="mt-4 flex flex-col gap-3 border-t border-[var(--border)] pt-4 sm:flex-row sm:items-center sm:justify-between">
                                        <div className={isDark ? "text-xs text-white/55" : "text-xs text-[#6c6090]"}>
                                            {commandText.trim().length
                                                ? `${commandText.trim().length} chars`
                                                : "No command yet"}
                                        </div>
                                        <button
                                            onClick={sendVoiceCommand}
                                            disabled={isSendingCommand}
                                            className="inline-flex items-center justify-center gap-2 rounded-full bg-[#10b981] px-4 py-2.5 text-sm font-semibold text-white shadow-[0_10px_20px_rgba(11,183,111,0.2)] transition hover:bg-[#0ea56f] disabled:cursor-not-allowed disabled:opacity-50"
                                        >
                                            <Send size={16} />
                                            {isSendingCommand ? "Sending..." : "Send command"}
                                        </button>
                                    </div>
                                </div>

                                {commandError ? (
                                    <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-200">
                                        {commandError}
                                    </div>
                                ) : null}

                                <div className={voiceResultClass}>
                                    <div className={isDark ? "mb-2 text-[10px] uppercase tracking-[0.22em] text-white/55" : "mb-2 text-[10px] uppercase tracking-[0.22em] text-[#705d94]"}>
                                        Result
                                    </div>
                                    {commandResult ? (
                                        <div className={isDark ? "space-y-2 text-sm text-white/80" : "space-y-2 text-sm text-[#483b61]"}>
                                            <div className="flex items-start justify-between gap-3">
                                                <span className={isDark ? "text-white/55" : "text-[#7a6f95]"}>Input</span>
                                                <span className={isDark ? "text-right text-white" : "text-right text-[#1f1640]"}>
                                                    {commandResult.input_text || commandText || "—"}
                                                </span>
                                            </div>
                                            {commandResult.result?.tool ? (
                                                <div className="flex items-start justify-between gap-3">
                                                      <span className={isDark ? "text-white/55" : "text-[#7a6f95]"}>Tool</span>
                                                      <span className={isDark ? "text-right text-white" : "text-right text-[#1f1640]"}>
                                                        {commandResult.result.tool}
                                                    </span>
                                                </div>
                                            ) : null}
                                            {commandResult.result?.arguments ? (
                                                <pre className={isDark ? "mt-2 overflow-auto rounded-xl bg-[#241139] p-3 text-xs text-white/65" : "mt-2 overflow-auto rounded-xl bg-[#f6f2ff] p-3 text-xs text-[#62577f]"}>
                                                    {JSON.stringify(commandResult.result.arguments, null, 2)}
                                                </pre>
                                            ) : null}
                                        </div>
                                    ) : (
                                        <div className={isDark ? "text-sm text-white/45" : "text-sm text-[#8d84a8]"}>
                                            No command sent yet.
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div className="space-y-3">
                                <div className={actionCardClass}>
                                    <div className={isDark ? "mb-3 text-[10px] uppercase tracking-[0.22em] text-white/55" : "mb-3 text-[10px] uppercase tracking-[0.22em] text-[#705d94]"}>
                                        Actions
                                    </div>
                                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
                                        {!isListening ? (
                                            <button
                                                onClick={startListening}
                                                className="inline-flex items-center justify-center gap-2 rounded-full bg-[#06b6d4] px-4 py-3 font-semibold text-white shadow-[0_10px_20px_rgba(12,164,214,0.18)] transition hover:bg-[#0891b2]"
                                            >
                                                <Mic size={16} />
                                                Start mic
                                            </button>
                                        ) : (
                                            <button
                                                onClick={stopListening}
                                                className="inline-flex items-center justify-center gap-2 rounded-full bg-[#ff5574] px-4 py-3 font-semibold text-white shadow-[0_10px_20px_rgba(255,55,88,0.16)] transition hover:bg-[#f43f5e]"
                                            >
                                                <Square size={16} />
                                                Stop mic
                                            </button>
                                        )}

                                        <button
                                            onClick={sendVoiceCommand}
                                            disabled={isSendingCommand}
                                            className="inline-flex items-center justify-center gap-2 rounded-full bg-[#10b981] px-4 py-3 font-semibold text-white shadow-[0_10px_20px_rgba(11,183,111,0.2)] transition hover:bg-[#0ea56f] disabled:cursor-not-allowed disabled:opacity-50"
                                        >
                                            <Send size={16} />
                                            {isSendingCommand ? "Sending..." : "Send"}
                                        </button>
                                    </div>
                                </div>

                                <div className={quickPanelClass}>
                                    <div className={isDark ? "mb-3 text-[10px] uppercase tracking-[0.22em] text-white/55" : "mb-3 text-[10px] uppercase tracking-[0.22em] text-[#705d94]"}>
                                        Quick commands
                                    </div>
                                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
                                        {quickCommands.map((command) => (
                                            <button
                                                key={command.label}
                                                onClick={() => setCommandText(command.value)}
                                                className={quickCommandClass}
                                            >
                                                {command.label}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </DarkCard>
                </div>
            </div>

            {sidebarOpen ? (
                <div className={sidebarShellClass}>
                <div>
                    <SectionLabel>Path planning</SectionLabel>
                    <DarkCard className={`space-y-4 ${sidebarCardClass}`}>
                        <div className="flex items-center justify-between">
                            <span className={sidebarLabelClass}>
                                Overview
                            </span>
                            <span className={`rounded-full border border-[var(--border)] px-3 py-1 text-[11px] ${isDark ? "bg-[#26163b] text-white/70" : "bg-[#f7f3ff] text-[#705d94]"}`}>
                                {slamState?.pose
                                    ? `${slamState.pose.x.toFixed(2)}, ${slamState.pose.y.toFixed(2)}`
                                    : "No pose"}
                            </span>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            {planningCards.map(({ label, value }) => (
                                <div key={label} className={`${sidebarMiniCardClass} border border-[var(--border)]`}>
                                    <div className={sidebarLabelClass}>
                                        {label}
                                    </div>
                                    <div className={sidebarValueClass}>{value}</div>
                                </div>
                            ))}
                        </div>
                    </DarkCard>
                </div>

                <div>
                    <SectionLabel>Status</SectionLabel>
                    <DarkCard className={`grid grid-cols-2 gap-3 ${sidebarCardClass}`}>
                        {statusCards.map(({ label, value }) => (
                            <div key={label} className={`${sidebarMiniCardClass}`}>
                                <div className={sidebarLabelClass}>
                                    {label}
                                </div>
                                <div className={isDark ? "mt-1 text-sm font-semibold text-white" : "mt-1 text-sm font-semibold text-[#1f1640]"}>
                                    {value}
                                </div>
                            </div>
                        ))}
                    </DarkCard>
                </div>

                <div>
                    <SectionLabel>QR detections</SectionLabel>
                    <DarkCard className={`p-3 ${sidebarCardClass}`}>
                        {qrPositionError && !qrPosition ? (
                            <span className={`text-xs ${sidebarMutedClass}`}>{qrPositionError}</span>
                        ) : (
                            <TopDownQrView data={qrPosition} />
                        )}
                    </DarkCard>
                </div>

                <div>
                    <SectionLabel>Issues</SectionLabel>
                    <DarkCard className={`flex items-start gap-2 px-3 py-3 ${sidebarCardClass}`}>
                        <AlertTriangle size={14} className={`mt-0.5 shrink-0 ${isDark ? "text-white/45" : "text-[#705d94]"}`} />
                        <span className={`text-xs ${sidebarMutedClass}`}>
                            {slamError || qrPositionError || qrError || "No errors recorded"}
                        </span>
                    </DarkCard>
                </div>

                <div>
                    <SectionLabel>Connection</SectionLabel>
                    <DarkCard className={`space-y-2 text-xs ${isDark ? "text-white/70" : "text-[#4c3b73]"} ${sidebarCardClass}`}>
                        <div className="flex items-center justify-between">
                            <span>SLAM</span>
                            <span className={isDark ? "text-white" : "text-[#1f1640]"}>
                                {slamState?.status?.slam_ok !== undefined
                                    ? String(slamState.status.slam_ok)
                                    : "No data"}
                            </span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span>TF</span>
                            <span className={isDark ? "text-white" : "text-[#1f1640]"}>
                                {slamState?.status?.tf_ok !== undefined
                                    ? String(slamState.status.tf_ok)
                                    : "No data"}
                            </span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span>Obstacle</span>
                            <span className={isDark ? "text-white" : "text-[#1f1640]"}>
                                {obstacle ? `${obstacle.dist.toFixed(2)} m` : "Clear"}
                            </span>
                        </div>
                    </DarkCard>
                </div>
                </div>
            ) : null}
        </div>
    );
}
