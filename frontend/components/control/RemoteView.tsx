"use client";

import {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { HalfCircleJoystick } from "@/components/HalfCircleJoystick";
import HeaderControl from "@/components/header_control";
import MouselookPad from "@/components/MouselookPad";
import { useGamepadMove } from "@/app/lib/useGamepadMove";
import {
  getSelectedRobotAddr,
  SELECTED_ROBOT_ADDR_EVENT,
} from "@/app/lib/selectedRobot";
import {
  RobotAPI,
  DEFAULT_DOG_SERVER,
  robotId,
} from "@/app/lib/robotApi";

import {
  Panel,
  Chip,
  Btn,
  SliderRow,
  MouseLookToggle,
} from "@/components/control/ControlUI";

type BodyState = {
  tx: number;
  ty: number;
  tz: number;
  rx: number;
  ry: number;
  rz: number;
};

export default function RemoteView({
  onEmergencyStop,
  mode,
  toggleMode,
}: {
  onEmergencyStop?: () => void;
  mode: "remote" | "fpv";
  toggleMode: () => void;
}) {
  const [dogServer, setDogServer] = useState(
    () => getSelectedRobotAddr() || DEFAULT_DOG_SERVER
  );

  const isCheckingRef = useRef(false);
  const lidarRunningRef = useRef(false);

  useEffect(() => {
    const syncSelectedRobot = () => {
      const nextAddr = getSelectedRobotAddr() || DEFAULT_DOG_SERVER;
      setDogServer((current) => (current === nextAddr ? current : nextAddr));
    };

    syncSelectedRobot();
    window.addEventListener(SELECTED_ROBOT_ADDR_EVENT, syncSelectedRobot);
    window.addEventListener("focus", syncSelectedRobot);
    window.addEventListener("pageshow", syncSelectedRobot);
    document.addEventListener("visibilitychange", syncSelectedRobot);

    return () => {
      window.removeEventListener(SELECTED_ROBOT_ADDR_EVENT, syncSelectedRobot);
      window.removeEventListener("focus", syncSelectedRobot);
      window.removeEventListener("pageshow", syncSelectedRobot);
      document.removeEventListener("visibilitychange", syncSelectedRobot);
    };
  }, []);

  const lidarUrl = useMemo(() => {
    try {
      const url = new URL(dogServer);
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
  }, [dogServer]);

  const [isRunning, setIsRunning] = useState(false);
  const [lidarBusy, setLidarBusy] = useState(false);
  const [lidarError, setLidarError] = useState<string | null>(null);
  const [lidarFrameLoaded, setLidarFrameLoaded] = useState(false);
  const [lidarFrameKey, setLidarFrameKey] = useState(0);
  const [speed, setSpeed] = useState<"slow" | "normal" | "high">("normal");
  const [speedBusy, setSpeedBusy] = useState(false);
  const [fps, setFps] = useState(30);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [stabilizing, setStabilizing] = useState(false);
  const [lefting, setLefting] = useState(false);
  const [righting, setRighting] = useState(false);
  const [mouseLook, setMouseLook] = useState(false);
  const [commandLog, setCommandLog] = useState<string[]>([]);
  const postureBtns = ["Lie_Down", "Stand_Up", "Crawl", "Squat", "Sit_Down"];
  const axisMotionBtns = [
    "Turn_Roll",
    "Turn_Pitch",
    "Turn_Yaw",
    "3_Axis",
    "Turn_Around",
  ];
  const behaviorBtns = [
    "Mark_Time",
    "Pee",
    "Wave_Hand",
    "Stretch",
    "Wave_Body",
    "Swing",
    "Pray",
    "Seek",
    "Handshake",
  ];

  const hasResetBody = useRef(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isPortrait, setIsPortrait] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const appendLog = useCallback((line: string | undefined) => {
    if (!line) return;
    setCommandLog(prev => [line, ...prev].slice(0, 50)); 
  }, []);
  const lastConnectionStateRef = useRef<boolean | null>(null);
  const [sliders, setSliders] = useState<BodyState>({
    tx: 0,
    ty: 0,
    tz: 0,
    rx: 0,
    ry: 0,
    rz: 0,
  });
  const bodyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const joyRef = useRef<{ vx: number; vy: number; active: boolean }>({
    vx: 0,
    vy: 0,
    active: false,
  });
  const joyLogRef = useRef<{ direction: string; timestamp: number }>({
    direction: "",
    timestamp: 0,
  });

  const maxV = 0.25;
  const maxSideV = 0.25;
  useEffect(() => {
    if (typeof window === "undefined") return;

    const update = () => {
      const { innerWidth, innerHeight } = window;
      const mobile = innerWidth < 1024;
      setIsMobile(mobile);
      setIsPortrait(innerHeight > innerWidth);
    };

    update();
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
    };
  }, []);
  useEffect(() => {
    if (!connected) {
      setIsRunning(false);
      setLidarFrameLoaded(false);
      return;
    }

    let stop = false;
    async function fetchControlStatus() {
      try {
        const res: any = await RobotAPI.controlStatus();
        if (stop) return;
        const data = res?.data ?? res ?? {};
        const running = Boolean(data?.lidar_running ?? data?.lidar?.running ?? false);
        const wasRunning = lidarRunningRef.current;
        lidarRunningRef.current = running;
        setIsRunning(running);
        if (running) {
          setLidarError(null);
          if (!wasRunning) {
            setLidarFrameLoaded(false);
            setLidarFrameKey((value) => value + 1);
          }
        } else {
          setLidarFrameLoaded(false);
        }
      } catch {
        if (stop) return;
        setIsRunning(false);
        setLidarFrameLoaded(false);
      } finally {
      }
    }

    fetchControlStatus();
    const id = setInterval(fetchControlStatus, 2500);

    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [connected]);
  useEffect(() => {
    setLidarFrameLoaded(false);
    setLidarFrameKey((value) => value + 1);
  }, [lidarUrl]);
  useEffect(() => {
    let stop = false;
    let iv: ReturnType<typeof setInterval> | null = null;

    const checkAndConnect = async () => {
      if (stop) return;
      if (isCheckingRef.current) return;
      isCheckingRef.current = true;

      try {
        const res = await RobotAPI.connect(dogServer);
        if (stop) return;

        if (res?.connected) {
          const wasConnected = lastConnectionStateRef.current;
          setConnected(true);
          setConnectError(null);
          if (wasConnected !== true) {
            appendLog(`[CONNECT] Connected to ${dogServer}`);
          }
          lastConnectionStateRef.current = true;
          if (!hasResetBody.current) {
            try {
              await resetBody();
            } catch (e) {
              console.error("resetBody error:", e);
            }
            hasResetBody.current = true;
          }

          if (!streamUrl) {
            try {
              const f = await RobotAPI.fpv();
              if (!stop) setStreamUrl(f?.stream_url || null);
            } catch (e) {
              console.error("FPV error:", e);
              if (!stop) {
                setConnectError("Không lấy được stream_url từ backend");
              }
            }
          }
        } else {
          const wasConnected = lastConnectionStateRef.current;
          setConnected(false);
          const msg = res?.error || "Không kết nối được tới Dogzilla server";
          if (wasConnected !== false) {
            appendLog(`[DISCONNECT] ${msg}`);
          }
          lastConnectionStateRef.current = false;
          setConnectError(
            res?.error || "Không kết nối được tới Dogzilla server"
          );
        }
      } catch (e: any) {
        console.error("Connect error:", e);
        if (!stop) {
          const wasConnected = lastConnectionStateRef.current;
          setConnected(false);
          if (wasConnected !== false) {
            appendLog(`[DISCONNECT] ${e?.message || "Lỗi kết nối"}`);
          }
          lastConnectionStateRef.current = false;
          setConnectError(e?.message || "Lỗi kết nối");
        }
      } finally {
        isCheckingRef.current = false;
      }
    };

    checkAndConnect();
    iv = setInterval(checkAndConnect, 2000);

    return () => {
      stop = true;
      if (iv) clearInterval(iv);
      onEmergencyStop?.();
    };
  }, [dogServer, onEmergencyStop, streamUrl]);
  useEffect(() => {
    let stop = false;
    const iv = setInterval(async () => {
      try {
        const s: any = await RobotAPI.status();
        if (!stop && typeof s?.fps === "number") {
          setFps(s.fps);
        }
      } catch {
      }
    }, 2000);

    return () => {
      stop = true;
      clearInterval(iv);
    };
  }, []);
  const changeSpeed = useCallback(
    async (m: "slow" | "normal" | "high") => {
      if (speedBusy || !connected || speed === m) return;

      const previousSpeed = speed;
      setSpeed(m);
      setSpeedBusy(true);
      try {
        const res: any = await RobotAPI.speed(m);
        appendLog(res?.log || `[SPEED] → ${m.toUpperCase()}`);
      } catch (e: any) {
        console.error("Speed error:", e);
        setSpeed(previousSpeed);
        appendLog(`[SPEED ERROR] ${e?.message || String(e)}`);
      } finally {
        setSpeedBusy(false);
      }
    },
    [appendLog, connected, speed, speedBusy]
  );

  const runPostureCommand = useCallback(
    async (name: string) => {
      appendLog(`[POSTURE] ${name}`);
      try {
        const res: any = await RobotAPI.posture(name);
        appendLog(res?.log || `[POSTURE] -> ${name}`);
      } catch (e: any) {
        appendLog(`[POSTURE ERROR] ${name}: ${e?.message || String(e)}`);
      }
    },
    [appendLog]
  );

  const runBehaviorCommand = useCallback(
    async (name: string, group: "AXIS" | "BEHAVIOR") => {
      appendLog(`[${group}] ${name}`);
      try {
        const res: any = await RobotAPI.behavior(name);
        appendLog(res?.log || `[${group}] -> ${name}`);
      } catch (e: any) {
        appendLog(`[${group} ERROR] ${name}: ${e?.message || String(e)}`);
      }
    },
    [appendLog]
  );
  const handleToggleLidar = useCallback(async () => {
    if (lidarBusy) return;

    const next = !isRunning;
    try {
      setLidarBusy(true);
      setLidarError(null);
      const res: any = await RobotAPI.lidar(next ? "start" : "stop");
      appendLog(
        res?.log || `[LIDAR] ${next ? "start" : "stop"} (frontend toggle)`
      );
      setIsRunning(next);
      lidarRunningRef.current = next;
      if (next) {
        setLidarFrameLoaded(false);
        window.setTimeout(() => {
          setLidarFrameKey((value) => value + 1);
        }, 700);
      }
      if (!next) {
        setLidarFrameLoaded(false);
      }
    } catch (e: any) {
      console.error("Lidar error:", e);
      setLidarError(e?.message || "Không điều khiển được LiDAR");
      appendLog(`[LIDAR ERROR] ${e?.message || String(e)}`);
    } finally {
      setLidarBusy(false);
    }
  }, [isRunning, lidarBusy, appendLog]);
  const handleToggleStabilizing = useCallback(async () => {
    const next = !stabilizing;
    setStabilizing(next);
    try {
      const res: any = await RobotAPI.stabilizingMode(next ? "on" : "off");
      appendLog(
        res?.log ||
          `[STABILIZING] ${next ? "ON" : "OFF"} (stabilizing_mode command)`
      );
    } catch (e: any) {
      console.error("Stabilizing error:", e);
      appendLog(`[STABILIZING ERROR] ${e?.message || String(e)}`);
      setStabilizing((prev) => !prev);
    }
  }, [stabilizing, appendLog]);
  useEffect(() => {
    let isRequesting = false;
    const timer = setInterval(async () => {
      const { vx, vy, active } = joyRef.current;
      if (!active) return;
      if (isRequesting) return;

      isRequesting = true;
      try {
        const direction =
          Math.abs(vx) >= Math.abs(vy)
            ? vx >= 0
              ? "forward"
              : "back"
            : vy >= 0
            ? "right"
            : "left";
        const now = Date.now();
        const shouldLog =
          joyLogRef.current.direction !== direction ||
          now - joyLogRef.current.timestamp >= 1000;
        const res: any = await RobotAPI.move({ vx, vy, vz: 0, rx: 0, ry: 0, rz: 0 });

        if (shouldLog) {
          appendLog(
            res?.log ||
              `[MOVE] joystick ${direction} vx=${vx.toFixed(2)}, vy=${vy.toFixed(2)}`
          );
          joyLogRef.current = { direction, timestamp: now };
        }
      } catch (e: any) {
        const now = Date.now();
        if (now - joyLogRef.current.timestamp >= 1000) {
          appendLog(`[MOVE ERROR] joystick: ${e?.message || String(e)}`);
          joyLogRef.current = { direction: "error", timestamp: now };
        }
      } finally {
        isRequesting = false;
      }
    }, 80);

    return () => clearInterval(timer);
  }, [appendLog]);

  const onJoyChange = useCallback(
    ({ angleDeg, power }: { angleDeg: number; power: number }) => {
      const rad = (angleDeg * Math.PI) / 180;
      const forward = Math.cos(rad) * power;
      const strafe = Math.sin(rad) * power;

      const vx = forward * maxV;
      const vy = strafe * maxSideV;

      joyRef.current = { vx, vy, active: power > 0.01 };
    },
    []
  );

  const onJoyRelease = useCallback(async () => {
    joyRef.current = { vx: 0, vy: 0, active: false };
    joyLogRef.current = { direction: "", timestamp: 0 };
    try {
      const res: any = await RobotAPI.move({
        vx: 0,
        vy: 0,
        vz: 0,
        rx: 0,
        ry: 0,
        rz: 0,
      });
      appendLog(res?.log || "[MOVE] joystick stop");
    } catch (e: any) {
      appendLog(`[MOVE ERROR] joystick stop: ${e?.message || String(e)}`);
    }
  }, [appendLog]);
  const stopMove = useCallback(() => {
    RobotAPI.move({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: 0 })
      .then((res: any) => {
        appendLog(res?.log || "[MOVE] stop");
      })
      .catch((e: any) => {
        appendLog(`[MOVE ERROR] stop: ${e?.message || String(e)}`);
      });
    setRighting(false);
    setLefting(false);
  }, [appendLog]);

  const turnLeft = () => {
    if (lefting) {
      stopMove();
    } else {
      RobotAPI.move({
        vx: 0,
        vy: 0,
        vz: 0,
        rx: 0,
        ry: 0,
        rz: +0.8,
      })
        .then((res: any) => {
          appendLog(res?.log || "[MOVE] turn left (rz=+0.8)");
        })
        .catch((e: any) => {
          appendLog(`[MOVE ERROR] left: ${e?.message || String(e)}`);
        });

      setLefting(true);
      setRighting(false);
    }
  };

  const turnRight = () => {
    if (righting) {
      stopMove();
    } else {
      RobotAPI.move({
        vx: 0,
        vy: 0,
        vz: 0,
        rx: 0,
        ry: 0,
        rz: -0.8,
      })
        .then((res: any) => {
          appendLog(res?.log || "[MOVE] turn right (rz=-0.8)");
        })
        .catch((e: any) => {
          appendLog(`[MOVE ERROR] right: ${e?.message || String(e)}`);
        });

      setRighting(true);
      setLefting(false);
    }
  };
  const updateBody = useCallback(
    (partial: Partial<BodyState>) => {
      setSliders((prev) => {
        const next = { ...prev, ...partial };

        if (bodyTimer.current) clearTimeout(bodyTimer.current);

        bodyTimer.current = setTimeout(async () => {
          try {
            const res: any = await RobotAPI.body(next);
            const msg =
              res?.log ||
              `[BODY] tx=${next.tx}, ty=${next.ty}, tz=${next.tz}, rx=${next.rx}, ry=${next.ry}, rz=${next.rz}`;
            appendLog(msg);
          } catch (e: any) {
            appendLog(`[BODY ERROR] ${e?.message || String(e)}`);
          }
        }, 150);

        return next;
      });
    },
    [appendLog]
  );


  const resetBody = useCallback(() => {
    const zero: BodyState = {
      tx: 0,
      ty: 0,
      tz: 0,
      rx: 0,
      ry: 0,
      rz: 0,
    };

    if (bodyTimer.current) clearTimeout(bodyTimer.current);
    setSliders(zero);

    RobotAPI.body(zero)
      .then((res: any) => {
        appendLog(res?.log || "[BODY] reset to center");
      })
      .catch((e: any) => {
        appendLog(`[BODY ERROR] reset: ${e?.message || String(e)}`);
      });
  }, [appendLog]);
  useGamepadMove();

  const lidarButtonLabel = lidarBusy
    ? isRunning
      ? "Stopping LiDAR..."
      : "Starting LiDAR..."
    : isRunning
    ? "Stop Lidar"
    : "Start Lidar";
  const lidarFrameSrc = lidarUrl
    ? `${lidarUrl}${lidarUrl.includes("?") ? "&" : "?"}t=${lidarFrameKey}`
    : "";
  if (isMobile) {
    return (
      <section className="h-screen w-full bg-[var(--background)] text-[var(--foreground)] relative">
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-40">
            <div
              className="absolute inset-0 bg-[rgba(0,0,0,0.35)]"
              onClick={() => setMobileMenuOpen(false)}
            />
            <div className="absolute inset-y-0 right-0 w-72 max-w-[80%] bg-[var(--surface)] border-l border-[var(--border)] p-4 flex flex-col gap-4 shadow-2xl">
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-semibold">Controls</div>
                <button onClick={() => setMobileMenuOpen(false)}
                  className="cursor-pointer w-8 h-8 flex items-center justify-center rounded-full bg-[var(--surface-2)] text-[var(--foreground)] text-lg leading-none"
                >
                  ×
                </button>
              </div>

              <div className="text-[11px] text-emerald-700 dark:text-emerald-300 mb-1">
                {connected ? "Robot connected" : "Not connected"}
              </div>

              <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                <div>
                  <div className="text-xs mb-1 opacity-80">Speed</div>
                  <div className="flex gap-2 flex-wrap">
                    {(["slow", "normal", "high"] as const).map((s) => (
                      <Chip
                        key={s}
                        label={
                          speedBusy && speed === s
                            ? `${s.charAt(0).toUpperCase() + s.slice(1)}...`
                            : s.charAt(0).toUpperCase() + s.slice(1)
                        }
                        active={speed === s}
                        disabled={speedBusy || !connected}
                        onClick={() => changeSpeed(s)}
                      />
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  <Btn
                    variant={isRunning ? "success" : "default"}
                    label={lidarButtonLabel}
                    onClick={handleToggleLidar}
                  />
                  <Btn
                    variant={stabilizing ? "success" : "default"}
                    label={stabilizing ? "Stabilizing ON" : "Stabilizing OFF"}
                    onClick={handleToggleStabilizing}
                  />
                </div>

                <div className="border-t border-[var(--border)] pt-3 mt-1">
                  <div className="text-xs mb-2 opacity-80">
                    Body Adjustment
                  </div>
                  <SliderRow
                    label="Translation_X"
                    value={sliders.tx}
                    onChange={(v) => updateBody({ tx: v })}
                  />
                  <SliderRow
                    label="Translation_Y"
                    value={sliders.ty}
                    onChange={(v) => updateBody({ ty: v })}
                  />
                  <SliderRow
                    label="Translation_Z"
                    value={sliders.tz}
                    onChange={(v) => updateBody({ tz: v })}
                  />
                  <SliderRow
                    label="Rotation_X"
                    value={sliders.rx}
                    onChange={(v) => updateBody({ rx: v })}
                  />
                  <SliderRow
                    label="Rotation_Y"
                    value={sliders.ry}
                    onChange={(v) => updateBody({ ry: v })}
                  />
                  <SliderRow
                    label="Rotation_Z"
                    value={sliders.rz}
                    onChange={(v) => updateBody({ rz: v })}
                  />

                  <div className="mt-3 flex justify-end">
                    <button
                      onClick={resetBody}
                      className="
                        px-3 py-1.5 text-xs rounded-lg cursor-pointer font-semibold
                        border border-fuchsia-400/70
                        bg-fuchsia-500/10 text-fuchsia-700
                        shadow-sm shadow-black/10
                        transition-all duration-200
                        hover:bg-fuchsia-500
                        hover:text-[#0c0520]
                        hover:border-fuchsia-200
                        hover:shadow-xl hover:shadow-fuchsia-500/60
                        hover:-translate-y-0.5 hover:scale-105
                        active:scale-95 active:translate-y-0
                      "
                    >
                      Reset body to center
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="mx-auto max-w-4xl h-full flex flex-col px-3 py-2 space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-xs opacity-70">
              {connected ? "Connected" : "Disconnected"}
              {connectError && (
                <span className="text-rose-500 dark:text-rose-300 ml-1">
                  ({connectError})
                </span>
              )}
            </div>
            <button onClick={() => setMobileMenuOpen(true)}
            className="cursor-pointer w-9 h-9 rounded-full border border-[var(--border)] bg-[var(--surface)] flex items-center justify-center text-lg leading-none text-[var(--foreground)] active:scale-95"
              aria-label="Open control menu"
            >
              ☰
            </button>
          </div>

          {isPortrait && (
            <div className="rounded-xl bg-amber-100/80 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-400/40 px-3 py-2 text-[11px] text-amber-800 dark:text-amber-200">
              For better control, please rotate your phone to{" "}
              <span className="font-semibold">landscape</span>.
            </div>
          )}

          <div className="flex-1">
            <div className="relative w-full h-full rounded-2xl border border-[var(--border)] bg-[var(--surface-elev)] overflow-hidden">
              <img
                src={streamUrl || "/placeholder.svg?height=360&width=640"}
                alt="FPV"
                className="absolute inset-0 w-full h-full object-cover opacity-80 z-0"
              />
              <div className="absolute left-2 top-2 text-[11px] font-semibold text-emerald-500 dark:text-emerald-300 z-10">
                FPS:{fps}
              </div>

              <div className="absolute inset-x-3 bottom-3 z-20">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex-shrink-0">
                    <HalfCircleJoystick
                      width={160}
                      height={100}
                      rest="center"
                      onChange={onJoyChange}
                      onRelease={onJoyRelease}
                    />
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={turnLeft}
                      className={`cursor-pointer w-10 h-10 rounded-full bg-[var(--surface-2)] text-[var(--foreground)] text-lg flex items-center justify-center border border-[var(--border)] ${
                        lefting ? "bg-cyan-600/70 text-white" : "hover:bg-[var(--surface)]"
                      }`}
                    >
                      {"<"}
                    </button>

                    <button
                      onClick={stopMove}
                      className="cursor-pointer w-12 h-12 rounded-full bg-rose-500 text-white text-xs font-semibold flex items-center justify-center shadow-lg active:scale-95"
                    >
                      Stop
                    </button>

                    <button
                      onClick={turnRight}
                      className={`cursor-pointer w-10 h-10 rounded-full bg-[var(--surface-2)] text-[var(--foreground)] text-lg flex items-center justify-center border border-[var(--border)] ${
                        righting ? "bg-cyan-600/70 text-white" : "hover:bg-[var(--surface)]"
                      }`}
                    >
                      {">"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  }
  return (
    <section className="min-h-screen w-full bg-[var(--background)] text-[var(--foreground)]">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <HeaderControl
            mode={mode}
            onToggle={toggleMode}
            lidarUrl={lidarUrl}
            lidarActive={isRunning}
            connected={connected}
            errorExternal={connectError}   
            commandLog={commandLog}  
          />


          <div className="relative overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-elev)]">
            <div className="absolute left-3 top-2 text-emerald-600 dark:text-emerald-300 text-xl font-bold drop-shadow z-10">
              FPS:{fps}
            </div>
            <img
              src={streamUrl || "/placeholder.svg?height=360&width=640"}
              alt="FPV"
              className="w-full aspect-video object-cover opacity-80"
            />

            <MouselookPad robotId={robotId} enabled={mouseLook} />
          </div>

          <div className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Panel title="Basic Postures" tone="pink">
              <div className="grid grid-cols-[repeat(5,minmax(0,1fr))] gap-2">
                {postureBtns.map((b) => (
                  <Btn
                    key={b}
                    label={b.replaceAll("_", " ")}
                    onClick={() => runPostureCommand(b)}
                    variant="default"
                    tone="pink"
                    className="w-full"
                  />
                ))}
              </div>
            </Panel>

            <Panel title="Axis Motion" tone="cyan">
              <div className="grid grid-cols-[repeat(5,minmax(0,1fr))] gap-2">
                {axisMotionBtns.map((b) => (
                  <Btn
                    key={b}
                    label={b.replaceAll("_", " ")}
                    onClick={() => runBehaviorCommand(b, "AXIS")}
                    variant="default"
                    tone="cyan"
                    className="w-full"
                  />
                ))}
              </div>
            </Panel>
          </div>

          <div className="mt-6">
            <Panel title="Behavior Control" tone="emerald">
              <div className="grid grid-cols-5 gap-2 xl:grid-cols-9">
                {behaviorBtns.map((b) => (
                  <Btn
                    key={b}
                    label={b.replaceAll("_", " ")}
                    onClick={() => runBehaviorCommand(b, "BEHAVIOR")}
                    variant="default"
                    tone="emerald"
                    className="w-full whitespace-nowrap"
                  />
                ))}
              </div>
            </Panel>
          </div>
        </div>

        <div className="flex flex-col gap-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:pr-1">
          <div className="order-1">
            <Panel title="Move" tone="cyan">
              <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-4 items-start">
                <div className="justify-self-center sm:justify-self-start cursor-pointer">
                  <HalfCircleJoystick
                    width={220}
                    height={140}
                    rest="center"
                    onChange={onJoyChange}
                    onRelease={onJoyRelease}
                  />
                </div>

                <div className="flex flex-col gap-3">
                  <div className="grid grid-cols-2 gap-2">
                    <Btn label="Turn left" variant={lefting ? "success" : "default"} tone="cyan" onClick={turnLeft} />
                    <Btn label="Turn right" variant={righting ? "success" : "default"} tone="cyan" onClick={turnRight} />
                    <Btn variant="danger" label="Stop" onClick={stopMove} />
                    <Btn
                      variant={isRunning ? "success" : "danger"}
                      label={lidarButtonLabel}
                      onClick={handleToggleLidar}
                    />
                    <Btn
                      variant={stabilizing ? "success" : "default"}
                      label={stabilizing ? "Stabilizing ON" : "Stabilizing OFF"}
                      tone="violet"
                      onClick={handleToggleStabilizing}
                    />
                    <MouseLookToggle
                      variant={mouseLook ? "success" : "default"}
                      on={mouseLook}
                      onToggle={() => setMouseLook((prev) => !prev)}
                    />
                  </div>
                </div>
              </div>
            </Panel>
          </div>

          <div className="order-2">
            <Panel title="Speed" tone="violet">
              <div className="flex gap-3">
                {(["slow", "normal", "high"] as const).map((s) => (
                  <Chip
                    key={s}
                    label={
                      speedBusy && speed === s
                        ? `${s.charAt(0).toUpperCase() + s.slice(1)}...`
                        : s.charAt(0).toUpperCase() + s.slice(1)
                    }
                    active={speed === s}
                    disabled={speedBusy || !connected}
                    onClick={() => changeSpeed(s)}
                  />
                ))}
              </div>
            </Panel>
          </div>

          <div className="order-3 rounded-2xl bg-[var(--surface)] border border-[var(--border)] p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="text-sm text-[var(--foreground)]/80">Lidar map</div>
              <div
                className={`text-[11px] font-medium ${
                  lidarError
                    ? "text-rose-400"
                    : isRunning
                    ? "text-emerald-500"
                    : "text-[var(--muted)]"
                }`}
              >
                {lidarError
                  ? "LiDAR error"
                  : isRunning
                  ? lidarFrameLoaded
                    ? "Live"
                    : "Loading..."
                  : "Offline"}
              </div>
            </div>

            <div
              className={`relative w-full rounded-xl overflow-hidden border border-[var(--border)] bg-[var(--surface-elev)] transition-[height] duration-300 ${
                isRunning || lidarError ? "h-80 xl:h-96" : "h-28"
              }`}
            >
              {isRunning && lidarFrameSrc ? (
                <iframe
                  key={lidarFrameSrc}
                  src={lidarFrameSrc}
                  title="LiDAR map"
                  className={`absolute inset-0 w-full h-full border-0 transition-opacity duration-300 ${
                    lidarFrameLoaded ? "opacity-100" : "opacity-0"
                  }`}
                  onLoad={() => {
                    setLidarFrameLoaded(true);
                    setLidarError(null);
                  }}
                  onError={() => {
                    setLidarFrameLoaded(false);
                    setLidarError(`Cannot load ${lidarUrl}`);
                  }}
                />
              ) : null}

              <div
                className={`absolute inset-0 flex items-center justify-center text-xs transition-opacity duration-300 ${
                  isRunning && lidarFrameLoaded ? "opacity-0 pointer-events-none" : "opacity-100"
                }`}
              >
                <div
                  className={`rounded-xl border border-[var(--border)] bg-[var(--surface)] text-center text-[var(--foreground)]/70 ${
                    isRunning || lidarError ? "px-4 py-3" : "px-3 py-2"
                  }`}
                >
                  {lidarError
                    ? `LiDAR error: ${lidarError}`
                    : isRunning
                    ? "Waiting for LiDAR stream..."
                    : "LiDAR is currently off"}
                </div>
              </div>
            </div>
          </div>

          <div className="order-4">
            <Panel title="Body Adjustment" tone="pink">
              <SliderRow
                label="Translation_X"
                value={sliders.tx}
                onChange={(v) => updateBody({ tx: v })}
              />
              <SliderRow
                label="Translation_Y"
                value={sliders.ty}
                onChange={(v) => updateBody({ ty: v })}
              />
              <SliderRow
                label="Translation_Z"
                value={sliders.tz}
                onChange={(v) => updateBody({ tz: v })}
              />
              <SliderRow
                label="Rotation_X"
                value={sliders.rx}
                onChange={(v) => updateBody({ rx: v })}
              />
              <SliderRow
                label="Rotation_Y"
                value={sliders.ry}
                onChange={(v) => updateBody({ ry: v })}
              />
              <SliderRow
                label="Rotation_Z"
                value={sliders.rz}
                onChange={(v) => updateBody({ rz: v })}
              />

              <div className="mt-3 flex justify-end">
                    <button
                      onClick={resetBody}
                      className="
                    px-3 py-1.5 text-xs rounded-lg cursor-pointer font-semibold
                    border border-fuchsia-400/70
                    bg-fuchsia-500/10 text-fuchsia-700
                    shadow-sm shadow-black/10
                    transition-all duration-200
                    hover:bg-fuchsia-500
                    hover:text-[#0c0520]
                    hover:border-fuchsia-200
                    hover:shadow-xl hover:shadow-fuchsia-500/60
                    hover:-translate-y-0.5 hover:scale-105
                    active:scale-95 active:translate-y-0
                  "
                    >
                      Reset body to center
                    </button>
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </section>
  );
}
