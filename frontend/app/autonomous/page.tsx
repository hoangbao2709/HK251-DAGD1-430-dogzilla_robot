"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RobotAPI } from "@/app/lib/robotApi";
import { DEFAULT_DOG_SERVER } from "@/app/lib/robotApi";
import {
    Bot,
    Wifi,
    WifiOff,
    AlertTriangle,
    Mic,
    Square,
    Send,
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
            <div className="text-white font-semibold text-base break-words">{value}</div>
            <div className="text-white/50 text-[11px] tracking-widest uppercase mt-0.5">
                {label}
            </div>
        </div>
    );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
    return (
        <h3 className="text-white/60 text-xs font-semibold uppercase tracking-widest mb-3">
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
    return <div className={`bg-[#0f0822] rounded-xl p-4 ${className}`}>{children}</div>;
}

function LidarMiniMap({ slamState }: { slamState: SlamStateData | null }) {
    const width = 420;
    const height = 176;

    const content = useMemo(() => {
        if (!slamState?.pose || !slamState?.render_info) {
            return null;
        }

        const renderInfo = slamState.render_info;
        const robot = mapToPixel(
            slamState.pose.x,
            slamState.pose.y,
            renderInfo,
            width,
            height
        );

        const points = (slamState.scan?.points || []).map((p, idx) => {
            const pt = mapToPixel(p.x, p.y, renderInfo, width, height);
            return (
                <circle
                    key={idx}
                    cx={pt.x}
                    cy={pt.y}
                    r="1.4"
                    fill="rgba(255,255,255,0.8)"
                />
            );
        });

        const headingLen = 20;
        const endX = robot.x + Math.cos(slamState.pose.theta || 0) * headingLen;
        const endY = robot.y - Math.sin(slamState.pose.theta || 0) * headingLen;

        return (
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
                <rect x="0" y="0" width={width} height={height} fill="#0b1020" />
                {points}
                <line
                    x1={robot.x}
                    y1={robot.y}
                    x2={endX}
                    y2={endY}
                    stroke="#facc15"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                />
                <circle cx={robot.x} cy={robot.y} r="5" fill="#22d3ee" />
                <circle
                    cx={robot.x}
                    cy={robot.y}
                    r="9"
                    fill="none"
                    stroke="rgba(34,211,238,0.4)"
                    strokeWidth="2"
                />
            </svg>
        );
    }, [slamState]);

    if (!content) {
        return (
            <div className="bg-[#0f0822] rounded-xl h-44 flex items-center justify-center border border-white/5">
                <span className="text-white/20 text-xs">No lidar data</span>
            </div>
        );
    }

    return (
        <div className="bg-[#0f0822] rounded-xl h-44 overflow-hidden border border-white/5">
            {content}
        </div>
    );
}

export default function AutonomousControlPage() {
    const [connected, setConnected] = useState(false);
    const [robotStatus, setRobotStatus] = useState<RobotStatusResponse | null>(null);

    const [slamState, setSlamState] = useState<SlamStateData | null>(null);
    const [slamLoading, setSlamLoading] = useState(true);
    const [slamError, setSlamError] = useState("");

    const [qrState, setQrState] = useState<QrStateData | null>(null);
    const [qrError, setQrError] = useState("");

    const [cameraError, setCameraError] = useState(false);
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

    const recognitionRef = useRef<any>(null);
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

    const fetchPoints = useCallback(async () => {
        try {
            const json = await RobotAPI.points();
            const data = json?.data ?? json ?? {};
            setSavedPoints(data || {});
        } catch {
            setSavedPoints({});
        }
    }, []);

    useEffect(() => {
        let active = true;

        const load = async () => {
            if (!active) return;
            await Promise.all([
                fetchRobotStatus(),
                fetchSlamState(),
                fetchQrState(),
                fetchPoints(),
            ]);
        };

        load();

        const statusTimer = setInterval(fetchRobotStatus, 3000);
        const slamTimer = setInterval(fetchSlamState, 700);
        const qrTimer = setInterval(fetchQrState, 700);
        const pointsTimer = setInterval(fetchPoints, 2500);
        const mapTimer = setInterval(() => {
            setMapReloadKey((v) => v + 1);
        }, 1000);

        return () => {
            active = false;
            clearInterval(statusTimer);
            clearInterval(slamTimer);
            clearInterval(qrTimer);
            clearInterval(pointsTimer);
            clearInterval(mapTimer);
        };
    }, [fetchPoints, fetchQrState, fetchRobotStatus, fetchSlamState]);

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

    const sensorMetrics = [
        {
            label: "Motor",
            value:
                robotStatus?.telemetry?.system?.cpu_percent !== undefined
                    ? `${robotStatus.telemetry.system.cpu_percent}%`
                    : "No data",
        },
        {
            label: "Speech",
            value: connected ? "Online" : "Offline",
        },
        {
            label: "Vision",
            value: cameraError ? "Unavailable" : "Online",
        },
        {
            label: "Water",
            value: robotWaterLevel,
        },
        {
            label: "Speed",
            value: robotFps !== undefined ? `${robotFps} FPS` : "No data",
        },
        {
            label: "Sensor",
            value:
                slamState?.status?.slam_ok !== undefined
                    ? slamState.status.slam_ok
                        ? "OK"
                        : "Fail"
                    : "No data",
        },
        {
            label: "Battery",
            value: robotBattery !== undefined ? `${robotBattery}%` : "No data",
        },
    ];

    const qrItems = qrState?.items || [];
    const pointNames = Object.keys(savedPoints || {}).sort();
    const obstacle = findNearestObstacleAhead(slamState);

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
        <div className="flex h-full min-h-screen bg-[#160626]">
            <div className="flex-1 flex flex-col p-6 gap-5 overflow-y-auto">
                <h1 className="gradient-title text-center text-2xl">Autonomous Control</h1>

                <DarkCard>
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-gradient-to-br from-pink-500/30 to-purple-600/30 border border-pink-500/20">
                                <Bot size={28} className="text-green-400" />
                            </div>
                            <span className="text-white text-xl font-bold">{robotName}</span>
                        </div>

                        <button
                            onClick={() => setConnected((c) => !c)}
                            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-semibold transition-all duration-200 cursor-pointer ${connected
                                ? "bg-red-500 hover:bg-red-600 text-white"
                                : "bg-green-600 hover:bg-green-700 text-white"
                                }`}
                        >
                            {connected ? (
                                <>
                                    <WifiOff size={14} />
                                    Disconnect
                                </>
                            ) : (
                                <>
                                    <Wifi size={14} />
                                    Connect
                                </>
                            )}
                        </button>
                    </div>

                    <p className="text-white/50 text-xs mb-4 uppercase tracking-widest">
                        Robot Details
                    </p>

                    <div className="grid grid-cols-3 gap-y-5 gap-x-8">
                        <StatBlock value={robotLocation} label="Location" />
                        <StatBlock value={cleaningProgress} label="Path Planning" />
                        <StatBlock value={robotFloor} label="Floor" />
                        <StatBlock value={robotStatusText} label="Status" />
                        <StatBlock value={robotWaterLevel} label="Water Level" />
                        <StatBlock
                            value={robotBattery !== undefined ? `${robotBattery}%` : "No data"}
                            label="Battery"
                        />
                    </div>
                </DarkCard>
                <DarkCard>
                    <div className="flex items-center justify-between mb-3">
                        <SectionLabel>Voice navigation command</SectionLabel>
                        <span className="text-white/40 text-xs">
                            Ví dụ: đi đến điểm A, đi đến điểm A B C, dừng điều hướng
                        </span>
                    </div>

                    <div className="grid grid-cols-1 gap-3">
                        <div>
                            <label className="block text-white/60 text-xs mb-2 uppercase tracking-widest">
                                Robot address
                            </label>
                            <input
                                value={robotAddr}
                                onChange={(e) => setRobotAddr(e.target.value)}
                                placeholder="http://100.95.128.237:9000"
                                className="w-full rounded-xl bg-[#0b1020] border border-white/10 px-4 py-3 text-white outline-none"
                            />
                        </div>

                        <div>
                            <label className="block text-white/60 text-xs mb-2 uppercase tracking-widest">
                                Command
                            </label>
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
                                className="w-full min-h-[100px] rounded-xl bg-[#0b1020] border border-white/10 px-4 py-3 text-white outline-none resize-none"
                            />
                        </div>

                        <div className="flex flex-wrap gap-2">
                            {!isListening ? (
                                <button
                                    onClick={startListening}
                                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500 text-black font-semibold"
                                >
                                    <Mic size={16} />
                                    Start mic
                                </button>
                            ) : (
                                <button
                                    onClick={stopListening}
                                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-red-500 text-white font-semibold"
                                >
                                    <Square size={16} />
                                    Stop mic
                                </button>
                            )}

                            <button
                                onClick={sendVoiceCommand}
                                disabled={isSendingCommand}
                                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 text-black font-semibold disabled:opacity-50"
                            >
                                <Send size={16} />
                                {isSendingCommand ? "Sending..." : "Send command"}
                            </button>

                            <button
                                onClick={() => setCommandText("hãy cho robot đi đến điểm A")}
                                className="px-3 py-2 rounded-xl bg-white/10 text-white text-sm"
                            >
                                Đi đến A
                            </button>

                            <button
                                onClick={() => setCommandText("hãy cho robot đi đến điểm A, B, C")}
                                className="px-3 py-2 rounded-xl bg-white/10 text-white text-sm"
                            >
                                Đi A, B, C
                            </button>

                            <button
                                onClick={() => setCommandText("dừng điều hướng")}
                                className="px-3 py-2 rounded-xl bg-white/10 text-white text-sm"
                            >
                                Stop
                            </button>
                        </div>

                        {commandError ? (
                            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                                {commandError}
                            </div>
                        ) : null}

                        {commandResult ? (
                            <div className="rounded-xl border border-white/10 bg-[#0b1020] px-4 py-3 text-xs text-white/80 space-y-2">
                                <div>
                                    <span className="text-white font-semibold">Input:</span>{" "}
                                    {commandResult.input_text || commandText}
                                </div>

                                {commandResult.result?.tool ? (
                                    <div>
                                        <span className="text-white font-semibold">Tool:</span>{" "}
                                        {commandResult.result.tool}
                                    </div>
                                ) : null}

                                {commandResult.result?.arguments ? (
                                    <div>
                                        <span className="text-white font-semibold">Arguments:</span>{" "}
                                        <pre className="mt-1 whitespace-pre-wrap text-white/70">
                                            {JSON.stringify(commandResult.result.arguments, null, 2)}
                                        </pre>
                                    </div>
                                ) : null}

                                {commandResult.result?.content?.length ? (
                                    <div>
                                        <span className="text-white font-semibold">Response:</span>
                                        <pre className="mt-1 whitespace-pre-wrap text-white/70">
                                            {JSON.stringify(commandResult.result.content, null, 2)}
                                        </pre>
                                    </div>
                                ) : null}

                                {commandResult.log ? (
                                    <div>
                                        <span className="text-white font-semibold">Log:</span>{" "}
                                        <div className="mt-1 text-white/60">{commandResult.log}</div>
                                    </div>
                                ) : null}
                            </div>
                        ) : null}
                    </div>
                </DarkCard>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <SectionLabel>Camera QR scan</SectionLabel>
                        <div className="bg-[#0f0822] rounded-xl overflow-hidden border border-white/5 relative">
                            <img
                                src={RobotAPI.qrVideoFeedUrl()}
                                alt="QR video feed"
                                className="w-[800px] h-[800px] object-cover bg-black"
                                onError={() => setCameraError(true)}
                                onLoad={() => setCameraError(false)}
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
                        <SectionLabel>SLAM map overlay</SectionLabel>
                        <div className="bg-[#0f0822] rounded-xl overflow-hidden border border-white/5 relative">
                            <img
                                ref={mapImgRef}
                                src={RobotAPI.slamMapUrl(mapReloadKey)}
                                alt="SLAM map"
                                className="w-[800px] w-[800px] object-contain bg-black"
                                onLoad={() => drawSlamOverlay()}
                            />
                            <canvas
                                ref={overlayRef}
                                className="absolute left-0 top-0 pointer-events-none"
                            />
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <SectionLabel>Lidar mini map</SectionLabel>
                        {slamLoading ? (
                            <div className="bg-[#0f0822] rounded-xl h-44 flex items-center justify-center border border-white/5">
                                <span className="text-white/20 text-xs">Loading lidar...</span>
                            </div>
                        ) : (
                            <LidarMiniMap slamState={slamState} />
                        )}
                        {slamError ? (
                            <p className="text-red-300/80 text-xs mt-2">{slamError}</p>
                        ) : null}
                    </div>

                    <div>
                        <SectionLabel>Path planning</SectionLabel>
                        <div className="bg-[#0f0822] rounded-xl h-44 border border-white/5 p-4 text-xs text-white/70 flex flex-col justify-center gap-2">
                            <div>
                                slam_ok:{" "}
                                <span className="text-white">
                                    {slamState?.status?.slam_ok !== undefined
                                        ? String(slamState.status.slam_ok)
                                        : "No data"}
                                </span>
                            </div>
                            <div>
                                tf_ok:{" "}
                                <span className="text-white">
                                    {slamState?.status?.tf_ok !== undefined
                                        ? String(slamState.status.tf_ok)
                                        : "No data"}
                                </span>
                            </div>
                            <div>
                                planner_ok:{" "}
                                <span className="text-white">
                                    {slamState?.status?.planner_ok !== undefined
                                        ? String(slamState.status.planner_ok)
                                        : "No data"}
                                </span>
                            </div>
                            <div>
                                pose:{" "}
                                <span className="text-white">
                                    {slamState?.pose
                                        ? `${slamState.pose.x.toFixed(2)}, ${slamState.pose.y.toFixed(
                                            2
                                        )}, ${slamState.pose.theta.toFixed(2)}`
                                        : "No data"}
                                </span>
                            </div>
                            <div>
                                obstacle ahead:{" "}
                                <span className="text-white">
                                    {obstacle ? `${obstacle.dist.toFixed(2)} m` : "Not found"}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                <DarkCard>
                    <div className="flex items-center justify-between mb-3">
                        <SectionLabel>Saved points</SectionLabel>
                        <div className="flex flex-wrap gap-2">
                            <button
                                onClick={createPointFromObstacle}
                                disabled={pointActionLoading}
                                className="px-3 py-2 rounded-lg bg-emerald-500 text-black text-sm font-semibold disabled:opacity-50"
                            >
                                Save point
                            </button>
                            <button
                                onClick={deleteLastPoint}
                                disabled={pointActionLoading || pointNames.length === 0}
                                className="px-3 py-2 rounded-lg bg-red-500 text-white text-sm font-semibold disabled:opacity-50"
                            >
                                Delete last
                            </button>
                            <button
                                onClick={clearAllPoints}
                                disabled={pointActionLoading || pointNames.length === 0}
                                className="px-3 py-2 rounded-lg bg-yellow-400 text-black text-sm font-semibold disabled:opacity-50"
                            >
                                Clear all
                            </button>
                        </div>
                    </div>

                    {pointNames.length === 0 ? (
                        <span className="text-white/30 text-sm">No saved points</span>
                    ) : (
                        <div className="grid grid-cols-2 gap-3">
                            {pointNames.map((name) => {
                                const point = savedPoints[name];
                                return (
                                    <div
                                        key={name}
                                        className="rounded-xl border border-white/10 bg-white/5 p-3"
                                    >
                                        <div className="text-white font-semibold mb-1">{name}</div>
                                        <div className="text-white/70 text-xs leading-6">
                                            x: {Number(point.x).toFixed(3)}
                                            <br />
                                            y: {Number(point.y).toFixed(3)}
                                            <br />
                                            yaw: {Number(point.yaw || 0).toFixed(3)}
                                        </div>

                                        <div className="flex gap-2 mt-3">
                                            <button
                                                onClick={() => goToPoint(name)}
                                                disabled={pointActionLoading}
                                                className="px-3 py-2 rounded-lg bg-emerald-500 text-black text-xs font-semibold disabled:opacity-50"
                                            >
                                                Go to
                                            </button>
                                            <button
                                                onClick={() => deletePoint(name)}
                                                disabled={pointActionLoading}
                                                className="px-3 py-2 rounded-lg bg-red-500 text-white text-xs font-semibold disabled:opacity-50"
                                            >
                                                Delete
                                            </button>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </DarkCard>
            </div>

            <div className="w-80 shrink-0 bg-[#1A0F28] border-l border-white/10 flex flex-col gap-5 p-5 overflow-y-auto">
                <div>
                    <SectionLabel>Sensor metrics</SectionLabel>
                    <div className="space-y-2">
                        {sensorMetrics.map(({ label, value }) => (
                            <div key={label} className="flex items-center justify-between py-1">
                                <span className="text-white/70 text-sm">{label}</span>
                                <span className="text-white font-semibold text-sm">{value}</span>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="border-t border-white/10" />

                <div>
                    <SectionLabel>QR detections</SectionLabel>
                    <DarkCard className="min-h-[180px]">
                        {qrItems.length === 0 ? (
                            <span className="text-white/20 text-xs">
                                {qrError || "No QR detected"}
                            </span>
                        ) : (
                            <ul className="space-y-3">
                                {qrItems.map((item, i) => (
                                    <li key={`${item.text}-${i}`} className="text-xs text-white/75 leading-6">
                                        <div className="text-white font-semibold">{item.text}</div>
                                        <div>Type: {item.qr_type}</div>
                                        <div>Angle: {item.angle_deg.toFixed(2)}°</div>
                                        <div>Distance: {item.distance_m.toFixed(3)} m</div>
                                        <div>
                                            Target: {item.target_x_m.toFixed(3)}, {item.target_z_m.toFixed(3)}
                                        </div>
                                        <div>Direction: {item.direction}</div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </DarkCard>
                </div>

                <div>
                    <SectionLabel>Error log</SectionLabel>
                    <DarkCard className="min-h-[100px] flex items-start gap-2">
                        <AlertTriangle size={14} className="text-white/20 mt-0.5 shrink-0" />
                        <span className="text-white/20 text-xs">
                            {slamError || qrError || "No errors recorded"}
                        </span>
                    </DarkCard>
                </div>

                <div>
                    <SectionLabel>Connection</SectionLabel>
                    <DarkCard className="space-y-2 text-xs text-white/70">
                        <div className="flex items-center justify-between">
                            <span>Robot</span>
                            <span className="text-white">{robotConnected}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span>SLAM</span>
                            <span className="text-white">
                                {slamState?.status?.slam_ok !== undefined
                                    ? String(slamState.status.slam_ok)
                                    : "No data"}
                            </span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span>TF</span>
                            <span className="text-white">
                                {slamState?.status?.tf_ok !== undefined
                                    ? String(slamState.status.tf_ok)
                                    : "No data"}
                            </span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span>Planner</span>
                            <span className="text-white">
                                {slamState?.status?.planner_ok !== undefined
                                    ? String(slamState.status.planner_ok)
                                    : "No data"}
                            </span>
                        </div>
                    </DarkCard>
                </div>
            </div>
        </div>
    );
}