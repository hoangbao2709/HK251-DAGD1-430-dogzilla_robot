// components/control/RemoteView.tsx
"use client";

import {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { useSearchParams } from "next/navigation";
import { HalfCircleJoystick } from "@/components/HalfCircleJoystick";
import HeaderControl from "@/components/header_control";
import MouselookPad from "@/components/MouselookPad";
import { useGamepadMove } from "@/app/lib/useGamepadMove";
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
  const searchParams = useSearchParams();
  const ipParam = searchParams.get("ip");
  const DOG_SERVER = ipParam || DEFAULT_DOG_SERVER;

  const isCheckingRef = useRef(false);

  const lidarUrl = useMemo(() => {
    try {
      const url = new URL(DOG_SERVER);
      const host = url.hostname;
      const port = url.port;

      const isCloudflare = host.endsWith("trycloudflare.com");
      if (isCloudflare) return `${url.origin.replace(/\/$/, "")}/lidar/`;

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
  }, [DOG_SERVER]);

  const [isRunning, setIsRunning] = useState(false);
  const [speed, setSpeed] = useState<"slow" | "normal" | "high">("normal");
  const [fps, setFps] = useState(30);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [stabilizing, setStabilizing] = useState(false);
  const [lefting, setLefting] = useState(false);
  const [righting, setRighting] = useState(false);
  const [mouseLook, setMouseLook] = useState(false);
  const [commandLog, setCommandLog] = useState<string[]>([]);
  const postureBtns = ["Lie_Down", "Stand_Up", "Sit_Down", "Squat", "Crawl"];
  const axisMotionBtns = [
    "Turn_Roll",
    "Turn_Pitch",
    "Turn_Yaw",
    "3_Axis",
    "Turn_Around",
  ];
  const behavior1 = ["Wave_Hand", "Handshake", "Pray", "Stretch", "Swing"];
  const behavior2 = ["Wave_Body", "Handshake", "Pee", "Play_Ball", "Mark_Time"];

  const hasResetBody = useRef(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isPortrait, setIsPortrait] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const appendLog = useCallback((line: string | undefined) => {
    if (!line) return;
    setCommandLog(prev => [line, ...prev].slice(0, 50)); // giữ 50 dòng gần nhất
  }, []);
  // body sliders
  const [sliders, setSliders] = useState<BodyState>({
    tx: 0,
    ty: 0,
    tz: 0,
    rx: 0,
    ry: 0,
    rz: 0,
  });
  const bodyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // joystick state
  const joyRef = useRef<{ vx: number; vy: number; active: boolean }>({
    vx: 0,
    vy: 0,
    active: false,
  });

  const maxV = 0.25;
  const maxSideV = 0.25;

  // ==== responsive ====
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

  // ==== ping lidar server ====
  useEffect(() => {
    if (!lidarUrl) {
      setIsRunning(false);
      return;
    }

    let stop = false;

    async function pingLidar() {
      try {
        const res = await fetch(lidarUrl, { cache: "no-store" });
        if (stop) return;
        setIsRunning(res.ok);
      } catch {
        if (stop) return;
        setIsRunning(false);
      }
    }

    pingLidar();
    const id = setInterval(pingLidar, 2000);

    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [lidarUrl]);

  // ==== connect Django -> Dogzilla + lấy stream_url ====
  useEffect(() => {
    let stop = false;
    let iv: ReturnType<typeof setInterval> | null = null;

    const checkAndConnect = async () => {
      if (stop) return;
      if (isCheckingRef.current) return;
      isCheckingRef.current = true;

      try {
        const res = await RobotAPI.connect(DOG_SERVER);
        if (stop) return;

        if (res?.connected) {
          setConnected(true);
          setConnectError(null);

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
          setConnected(false);
          setConnectError(
            res?.error || "Không kết nối được tới Dogzilla server"
          );
        }
      } catch (e: any) {
        console.error("Connect error:", e);
        if (!stop) {
          setConnected(false);
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
  }, [DOG_SERVER, onEmergencyStop, streamUrl]);

  // ==== poll fps từ /status (nếu backend có) ====
  useEffect(() => {
    let stop = false;
    const iv = setInterval(async () => {
      try {
        const s: any = await RobotAPI.status();
        if (!stop && typeof s?.fps === "number") {
          setFps(s.fps);
        }
      } catch {
        // ignore
      }
    }, 2000);

    return () => {
      stop = true;
      clearInterval(iv);
    };
  }, []);

  // ==== speed ====
  const changeSpeed = useCallback(async (m: "slow" | "normal" | "high") => {
    setSpeed(m);
    try {
      await RobotAPI.speed(m);
    } catch (e) {
      console.error("Speed error:", e);
    }
  }, []);

  // ==== lidar toggle ====
  const handleToggleLidar = useCallback(async () => {
    const next = !isRunning;
    try {
      await RobotAPI.lidar(next ? "start" : "stop");
      setIsRunning(next);
    } catch (e) {
      console.error("Lidar error:", e);
    }
  }, [isRunning]);

  // ==== stabilizing toggle ====
  const handleToggleStabilizing = useCallback(async () => {
    const next = !stabilizing;
    setStabilizing(next);
    try {
      await RobotAPI.stabilizingMode(next ? "on" : "off");
    } catch (e) {
      console.error("Stabilizing error:", e);
      setStabilizing((prev) => !prev);
    }
  }, [stabilizing]);

  // ==== joystick send loop ====
  useEffect(() => {
    const timer = setInterval(() => {
      const { vx, vy, active } = joyRef.current;
      if (!active) return;

      RobotAPI.move({ vx, vy, vz: 0, rx: 0, ry: 0, rz: 0 }).catch(() => {});
    }, 80);

    return () => clearInterval(timer);
  }, []);

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
    try {
      await RobotAPI.move({
        vx: 0,
        vy: 0,
        vz: 0,
        rx: 0,
        ry: 0,
        rz: 0,
      });
    } catch {
      /* ignore */
    }
  }, []);

  // ==== quay trái / phải + stop ====
  const stopMove = useCallback(() => {
    RobotAPI.move({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: 0 }).catch(() => {});
    setRighting(false);
    setLefting(false);
  }, []);

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
      }).catch(() => {});
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
      }).catch(() => {});
      setRighting(true);
      setLefting(false);
    }
  };

  // ==== body adjust ====
  const updateBody = useCallback((partial: Partial<BodyState>) => {
    setSliders((prev) => {
      const next = { ...prev, ...partial };
      if (bodyTimer.current) clearTimeout(bodyTimer.current);
      bodyTimer.current = setTimeout(() => {
        RobotAPI.body(next).catch(() => {});
      }, 150);
      return next;
    });
  }, []);

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
    RobotAPI.body(zero).catch(() => {});
  }, []);

  // gamepad điều khiển chung
  useGamepadMove();

  /* ========== MOBILE LAYOUT ========== */
  if (isMobile) {
    return (
      <section className="h-screen w-full bg-slate-50 text-slate-900 dark:bg-[#0c0520] dark:text-white relative">
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-40">
            <div
              className="absolute inset-0 bg-black/40"
              onClick={() => setMobileMenuOpen(false)}
            />
            <div className="absolute inset-y-0 right-0 w-72 max-w-[80%] bg-white border-l border-slate-200 dark:bg-slate-900 dark:border-white/10 p-4 flex flex-col gap-4 shadow-2xl">
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-semibold">Controls</div>
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  className="w-8 h-8 flex items-center justify-center rounded-full bg-black/5 dark:bg-white/10 text-lg leading-none"
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
                        label={s.charAt(0).toUpperCase() + s.slice(1)}
                        active={speed === s}
                        onClick={() => changeSpeed(s)}
                      />
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  <Btn
                    variant={isRunning ? "success" : "default"}
                    label={isRunning ? "Stop Lidar" : "Start Lidar"}
                    onClick={handleToggleLidar}
                  />
                  <Btn
                    variant={stabilizing ? "success" : "default"}
                    label={stabilizing ? "Stabilizing ON" : "Stabilizing OFF"}
                    onClick={handleToggleStabilizing}
                  />
                </div>

                <div className="border-t border-slate-200 dark:border-white/10 pt-3 mt-1">
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
                        bg-fuchsia-500/10 dark:bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-100
                        shadow-sm shadow-black/10 dark:shadow-black/40
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
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="w-9 h-9 rounded-full border border-slate-300 dark:border-white/20 bg-white/70 dark:bg-white/10 flex items-center justify-center text-lg leading-none active:scale-95"
              aria-label="Open control menu"
            >
              ☰
            </button>
          </div>

          {isPortrait && (
            <div className="rounded-xl bg-amber-100 dark:bg-amber-500/10 border border-amber-300 dark:border-amber-400/40 px-3 py-2 text-[11px] text-amber-700 dark:text-amber-200">
              For better control, please rotate your phone to{" "}
              <span className="font-semibold">landscape</span>.
            </div>
          )}

          <div className="flex-1">
            <div className="relative w-full h-full rounded-2xl border border-slate-200 dark:border-white/10 bg-black overflow-hidden">
              <img
                src={streamUrl || "/placeholder.svg?height=360&width=640"}
                alt="FPV"
                className="absolute inset-0 w-full h-full object-cover opacity-80 z-0"
              />
              <div className="absolute left-2 top-2 text-[11px] font-semibold text-green-500 dark:text-green-300 z-10">
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
                      className={`w-10 h-10 rounded-full bg-black/60 text-white text-lg flex items-center justify-center border border-white/20 ${
                        lefting ? "bg-cyan-600/70" : "hover:bg-white/20"
                      }`}
                    >
                      {"<"}
                    </button>

                    <button
                      onClick={stopMove}
                      className="w-12 h-12 rounded-full bg-red-600 text-white text-xs font-semibold flex items-center justify-center shadow-lg active:scale-95"
                    >
                      Stop
                    </button>

                    <button
                      onClick={turnRight}
                      className={`w-10 h-10 rounded-full bg-black/60 text-white text-lg flex items-center justify-center border border-white/20 ${
                        righting ? "bg-cyan-600/70" : "hover:bg-white/20"
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

  /* ========== DESKTOP LAYOUT ========== */
  return (
    <section className="min-h-screen w-full bg-slate-50 text-slate-900 dark:bg-[#0c0520] dark:text-white">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <HeaderControl
            mode={mode}
            onToggle={toggleMode}
            lidarUrl={lidarUrl}
            connected={connected}
            errorExternal={connectError}   
            commandLog={commandLog}  
          />


          <div className="relative overflow-hidden rounded-2xl border border-slate-200 dark:border-white/10 bg-black">
            <div className="absolute left-3 top-2 text-green-600 dark:text-green-300 text-xl font-bold drop-shadow z-10">
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
            <Panel title="Basic Postures">
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                {postureBtns.map((b) => (
                  <Btn
                    key={b}
                    label={b.replaceAll("_", " ")}
                    onClick={() => RobotAPI.posture(b)}
                    variant="default"
                  />
                ))}
              </div>
            </Panel>

            <Panel title="Axis Motion">
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                {axisMotionBtns.map((b) => (
                  <Btn
                    key={b}
                    label={b.replaceAll("_", " ")}
                    onClick={() => RobotAPI.behavior(b)}
                    variant="default"
                  />
                ))}
              </div>
            </Panel>
          </div>

          <div className="mt-6">
            <Panel title="Behavior Control">
              <div className="grid grid-cols-2 sm:grid-cols-10 gap-3">
                {[...behavior1, ...behavior2].map((b, i) => (
                  <Btn
                    key={`${b}-${i}`}
                    label={b.replaceAll("_", " ")}
                    onClick={() => RobotAPI.behavior(b)}
                    variant="default"
                  />
                ))}
              </div>
            </Panel>
          </div>
        </div>

        <div className="space-y-6">
          <div
            className={`rounded-2xl bg-white/80 border border-slate-200 dark:bg-white/5 dark:border-white/10 ${
              !isRunning ? "hidden" : ""
            }`}
          >
            <div className="text-sm mb-2 opacity-80">Lidar map</div>
            <div className="relative w-full pt-[100%] rounded-xl overflow-hidden border border-slate-200 dark:border-white/10 bg-black">
              <iframe
                src={lidarUrl}
                className="absolute inset-0 w-full h-full border-0"
              />
            </div>
          </div>

          <Panel title="Speed">
            <div className="flex gap-3">
              {(["slow", "normal", "high"] as const).map((s) => (
                <Chip
                  key={s}
                  label={s.charAt(0).toUpperCase() + s.slice(1)}
                  active={speed === s}
                  onClick={() => changeSpeed(s)}
                />
              ))}
            </div>
          </Panel>

          <Panel title="Move">
            <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-4 items-start">
              <div className="justify-self-center sm:justify-self-start cursor-pointer">
                <HalfCircleJoystick
                  width={260}
                  height={160}
                  rest="center"
                  onChange={onJoyChange}
                  onRelease={onJoyRelease}
                />
              </div>

              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-2">
                  <Btn
                    label="Turn left"
                    variant={lefting ? "success" : "default"}
                    onClick={turnLeft}
                  />
                  <Btn
                    label="Turn right"
                    variant={righting ? "success" : "default"}
                    onClick={turnRight}
                  />
                  <Btn variant="danger" label="Stop" onClick={stopMove} />
                  <Btn
                    variant={isRunning ? "success" : "danger"}
                    label={isRunning ? "Stop Lidar" : "Start Lidar"}
                    onClick={handleToggleLidar}
                  />
                  <Btn
                    variant={stabilizing ? "success" : "default"}
                    label={stabilizing ? "Stabilizing ON" : "Stabilizing OFF"}
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

          <Panel title="Body Adjustment">
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
                  bg-fuchsia-500/10 dark:bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-100
                  shadow-sm shadow-black/10 dark:shadow-black/40
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
    </section>
  );
}
