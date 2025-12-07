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

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/control";
const DEFAULT_DOG_SERVER =
  process.env.NEXT_PUBLIC_DOGZILLA_BASE || "http://127.0.0.1:9000";

const robotId = "robot-a";

async function api<T = any>(path: string, init?: RequestInit): Promise<T | null> {
  if (!API_BASE) {
    return null;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  return res.json();
}

const RobotAPI = {
  connect: (addr: string) =>
    api(`/api/robots/${robotId}/connect/`, {
      method: "POST",
      body: JSON.stringify({ addr }),
    }),
  status: () => api(`/api/robots/${robotId}/status/`),
  fpv: () => api(`/api/robots/${robotId}/fpv/`),
  speed: (mode: "slow" | "normal" | "high") =>
    api(`/api/robots/${robotId}/command/speed/`, {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),
  move: (cmd: {
    vx: number;
    vy: number;
    vz: number;
    rx: number;
    ry: number;
    rz: number;
  }) => {
    console.log("MOVE CMD:", cmd);
    return api(`/api/robots/${robotId}/command/move/`, {
      method: "POST",
      body: JSON.stringify(cmd),
    });
  },
  lidar: (action: "start" | "stop") =>
    api(`/api/robots/${robotId}/command/lidar/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  posture: (name: string) =>
    api(`/api/robots/${robotId}/command/posture/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  behavior: (name: string) =>
    api(`/api/robots/${robotId}/command/behavior/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  body: (sl: {
    tx: number;
    ty: number;
    tz: number;
    rx: number;
    ry: number;
    rz: number;
  }) =>
    api(`/api/robots/${robotId}/command/body_adjust/`, {
      method: "POST",
      body: JSON.stringify(sl),
    }),
  stabilizingMode: (action: "on" | "off" | "toggle") =>
    api(`/api/robots/${robotId}/command/stabilizing_mode/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
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
  const ipParam = searchParams.get("ip"); // /control?ip=...
  const DOG_SERVER = ipParam || DEFAULT_DOG_SERVER;
  const isCheckingRef = useRef(false);
  const lidarUrl = useMemo(() => {
    try {
      const url = new URL(DOG_SERVER);
      const host = url.hostname;
      const port = url.port;

      const isCloudflare = host.endsWith("trycloudflare.com");

      if (isCloudflare) {
        return `${url.origin.replace(/\/$/, "")}/lidar/`;
      }

      if (port === "9000" || port === "") {
        return `${url.protocol}//${host}:8080`;
      }

      if (port === "9002") {
        return `${url.protocol}//${host}:9002/lidar/`;
      }

      return `${url.origin.replace(/\/$/, "")}/lidar/`;
    } catch (e) {
      return "";
    }
  }, [DOG_SERVER]);
  const [isRunning, setIsRunning] = useState(false);

  const [lidarFrameLoaded, setLidarFrameLoaded] = useState(false);
  const [speed, setSpeed] = useState<"slow" | "normal" | "high">("normal");
  const [fps, setFps] = useState(30);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [stabilizing, setStabilizing] = useState(false);
  const [lefting, setLefting] = useState(false);
  const [righting, setRighting] = useState(false);
  const [mouseLook, setMouseLook] = useState(false);

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
    useEffect(() => {
    if (typeof window === "undefined") return;

    const update = () => {
      const { innerWidth, innerHeight } = window;
      const mobile = innerWidth < 1024;     // tuỳ ngưỡng, 1024 = dưới tablet ngang
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
    // Không có URL -> chắc chắn không chạy
    if (!lidarUrl) {
      setIsRunning(false);
      return;
    }

    let stop = false;

    async function pingLidar() {
      try {
        const res = await fetch(lidarUrl, { cache: "no-store" });
        if (stop) return;

        // Nếu HTTP trả về 200 OK thì coi là đang chạy
        setIsRunning(res.ok);
      } catch (e) {
        if (stop) return;
        // Lỗi network / server down -> coi như Lidar không chạy
        setIsRunning(false);
      }
    }

    // Ping ngay 1 lần
    pingLidar();
    // Và lặp lại mỗi 2 giây
    const id = setInterval(pingLidar, 2000);

    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [lidarUrl]);
  useEffect(() => {
    if (!isRunning) {
      setLidarFrameLoaded(false);
    }
  }, [isRunning]);

  // ====== Kết nối Django -> Dogzilla Flask server + lấy stream_url ======
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
          // Backend trả về connected = false
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

    // gọi ngay lần đầu
    checkAndConnect();

    iv = setInterval(() => {
      checkAndConnect();
    }, 2000);

    return () => {
      stop = true;
      if (iv) clearInterval(iv);
      onEmergencyStop?.();
    };
  }, [DOG_SERVER, onEmergencyStop, streamUrl]);
  console.log("streamUrl", streamUrl);
  const changeSpeed = useCallback(async (m: "slow" | "normal" | "high") => {
    setSpeed(m);
    try {
      await RobotAPI.speed(m);
    } catch (e) {
      console.error("Speed error:", e);
    }
  }, []);

  /* ====== LIDAR TOGGLE ====== */
  const handleToggleLidar = useCallback(async () => {
    const next = !isRunning;
    try {
      await RobotAPI.lidar(next ? "start" : "stop");
      setIsRunning(next);
    } catch (e) {
      console.error("Lidar error:", e);
    }
  }, [isRunning]);

  /* ====== STABILIZING TOGGLE ====== */
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

  useEffect(() => {
    if (!isRunning) {
      setLidarFrameLoaded(false);
      return;
    }

    const t = setTimeout(() => {
      setLidarFrameLoaded(true);
    }, 1500);

    return () => clearTimeout(t);
  }, [isRunning]);

  // ===== JOYSTICK MOVE (giữ nguyên như cũ) =====
  const joyRef = useRef<{ vx: number; vy: number; active: boolean }>({
    vx: 0,
    vy: 0,
    active: false,
  });

  const maxV = 0.25;   // tốc độ tiến/lùi
  const maxSideV = 0.25; // tốc độ đi ngang (tuỳ bạn chỉnh)

  useEffect(() => {
    const timer = setInterval(() => {
      const { vx, vy, active } = joyRef.current;
      if (!active) return;

      RobotAPI.move({
        vx,
        vy,   // ĐI NGANG NẰM Ở ĐÂY
        vz: 0,
        rx: 0,
        ry: 0,
        rz: 0, // joystick này không xoay
      });
    }, 80); // 80–100ms tuỳ bạn

    return () => clearInterval(timer);
  }, []);


  const onJoyChange = useCallback(
    ({ angleDeg, power }: { angleDeg: number; power: number }) => {
      const rad = (angleDeg * Math.PI) / 180;

      // forward = tiến/lùi, strafe = đi ngang
      const forward = Math.cos(rad) * power; // -1..1 (lên/xuống)
      const strafe = Math.sin(rad) * power; // -1..1 (trái/phải)

      const vx = forward * maxV;      // tiến (+) / lùi (-)
      const vy = strafe * maxSideV;   // phải (+) / trái (-) (tuỳ bạn)

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


  const turnLeft = () => {
    if (lefting) {
      // đang quay trái → bấm lại để stop
      stopMove();
    } else {
      RobotAPI.move({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: +0.8 });
      setLefting(true);
      setRighting(false);
    }
  };

  const turnRight = () => {
    if (righting) {
      // đang quay phải → bấm lại để stop
      stopMove();
    } else {
      RobotAPI.move({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: -0.8 });
      setRighting(true);
      setLefting(false);
    }
  };

 const stopMove = () => {
    RobotAPI.move({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: 0 });
    setRighting(false);
    setLefting(false);
  };

  type BodyState = {
    tx: number;
    ty: number;
    tz: number;
    rx: number;
    ry: number;
    rz: number;
  };

  const [sliders, setSliders] = useState<BodyState>({
    tx: 0,
    ty: 0,
    tz: 0,
    rx: 0,
    ry: 0,
    rz: 0,
  });

  const bodyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const updateBody = useCallback((partial: Partial<BodyState>) => {
    setSliders((prev) => {
      const next = { ...prev, ...partial };
      console.log("BODY NEXT:", next);
      if (bodyTimer.current) clearTimeout(bodyTimer.current);
      bodyTimer.current = setTimeout(() => {
        RobotAPI.body(next).catch(() => {
          /* ignore */
        });
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
    RobotAPI.body(zero).catch(() => {
      /* ignore */
    });
  }, []);

  if (isMobile) {
    return (
      <section className="h-screen w-full bg-[#0c0520] text-white">
        <div className="mx-auto max-w-4xl h-full flex flex-col px-3 py-2 space-y-2">
          {isPortrait && (
            <div className="rounded-xl bg-amber-500/10 border border-amber-400/40 px-3 py-2 text-[11px] text-amber-200">
              For better control, please rotate your phone to{" "}
              <span className="font-semibold">landscape</span>.
            </div>
          )}

          <div className="flex-1">
            <div className="relative w-full h-full rounded-2xl border border-white/10 bg-black overflow-hidden">
              {/* VIDEO luôn nằm dưới cùng */}
              <img
                src={streamUrl || "/placeholder.svg?height=360&width=640"}
                alt="FPV"
                className="absolute inset-0 w-full h-full object-cover opacity-80 z-0"
              />

              {/* FPS overlay */}
              <div className="absolute left-2 top-2 text-[11px] font-semibold text-green-300 z-10">
                FPS:{fps}
              </div>

              {/* Joystick + nút điều khiển, luôn nằm trên video */}
              <div className="absolute inset-x-3 bottom-3 z-20">
                <div className="flex items-center justify-between gap-4">
                  {/* Joystick bên trái */}
                  <div className="flex-shrink-0">
                    <HalfCircleJoystick
                      width={160}
                      height={100}
                      rest="center"
                      onChange={onJoyChange}
                      onRelease={onJoyRelease}
                    />
                  </div>

                  {/* Cụm nút bên phải: <  Stop  > */}
                  <div className="flex items-center gap-3">
                    <button
                      onClick={turnLeft}
                      className={`w-10 h-10 rounded-full bg-black/60 text-white text-lg flex items-center justify-center border border-white/20
                        ${lefting ? "bg-cyan-600/70" : "hover:bg-white/20"}`}
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
                      className={`w-10 h-10 rounded-full bg-black/60 text-white text-lg flex items-center justify-center border border-white/20
                        ${righting ? "bg-cyan-600/70" : "hover:bg-white/20"}`}
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
    <section className="min-h-screen w-full bg-[#0c0520] text-white">
      {/* Trạng thái connect */}
      <div className={`text-sm`}>

        {(!DEFAULT_DOG_SERVER || DEFAULT_DOG_SERVER.trim() === "") && (
          <div className="text-xs text-rose-400 mt-1">
            Error: Dogzilla server address is empty.
          </div>
        )}

        {(connectError && DEFAULT_DOG_SERVER) && (
          <div className="text-xs text-rose-400 mt-1">
            Error: {connectError}
          </div>
        )}
      </div>


      {/* Main content row */}
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* FPV video + behaviors */}
        <div className="lg:col-span-2">
          <HeaderControl mode={mode} onToggle={toggleMode} lidarUrl={lidarUrl} connected={connected} />

          <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-black">
            <div className="absolute left-3 top-2 text-green-300 text-xl font-bold drop-shadow z-10">
              FPS:{fps}
            </div>
            <img
              src={streamUrl || "/placeholder.svg?height=360&width=640"}
              alt="FPV"
              className="w-full aspect-video object-cover opacity-80"
            />

            {/* Overlay mouselook chỉ trong khung FPV */}
            <MouselookPad robotId={robotId} enabled={mouseLook} />
          </div>


          {/* Bottom control grids */}
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

        {/* Right control panel */}
        <div className="space-y-6">
          {/* Lidar map */}
          <div
            className={`rounded-2xl bg-white/5 border border-white/10 ${!isRunning ? "hidden" : ""
              }`}
          >
            <div className="text-sm mb-2 opacity-80">Lidar map</div>

            {/* Container giữ tỷ lệ VUÔNG + full width */}
            <div className="relative w-full pt-[100%] rounded-xl overflow-hidden border border-white/10 bg-black">
              <iframe
                src={lidarUrl}
                className="absolute inset-0 w-full h-full border-0"
              />
            </div>
          </div>


          {/* Speed */}
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

          {/* Move */}
          <Panel title="Move">
            <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-4 items-start">
              {/* Joystick */}
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
                  <Btn label="Turn left" variant={lefting ? "success" : "default"} onClick={turnLeft} />
                  <Btn label="Turn right" variant={righting ? "success" : "default"} onClick={turnRight} />
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
                    variant={stabilizing ? "success" : "default"}
                    on={mouseLook}
                    onToggle={() => setMouseLook((prev) => !prev)}
                  />
                </div>




              </div>
            </div>
          </Panel>

          {/* Body Adjustment */}
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

            {/* Nút reset về giữa */}
            <div className="mt-3 flex justify-end">
              <button
                onClick={resetBody}
                className="
                  px-3 py-1.5 text-xs rounded-lg cursor-pointer font-semibold
                  border border-fuchsia-400/70
                  bg-fuchsia-500/15 text-fuchsia-100
                  shadow-sm shadow-black/40
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

/* ========== UI HELPERS ========== */

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl bg-white/5 border border-white/10 p-4">
      <div className="text-sm mb-3 opacity-80">{title}</div>
      {children}
    </div>
  );
}

function Chip({
  label,
  active,
  onClick,
}: {
  label: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-1 rounded-xl text-sm border transition cursor-pointer
      ${active
          ? "bg-indigo-500/30 border-indigo-400/40"
          : "bg-white/5 border-white/10 hover:bg-white/10"
        }`}
    >
      {label}
    </button>
  );
}

function Btn({
  label,
  variant = "default",
  onClick,
}: {
  label: string;
  variant: string;
  onClick?: () => void;
}) {
  const base =
    "px-4 py-2 text-sm rounded-xl border font-medium cursor-pointer " +
    "transition-all duration-200 transform select-none";

  let styles = "";

  if (variant === "danger") {
    styles = [
      "bg-rose-600/70 border-rose-400 text-white",
      "hover:!bg-rose-400 hover:!border-rose-200 hover:!text-white",
      "hover:shadow-xl hover:shadow-rose-500/50",
      "hover:-translate-y-0.5 hover:scale-[1.05]",
      "active:scale-95 active:translate-y-0",
    ].join(" ");
  } else if (variant === "success") {
    styles = [
      "bg-emerald-600/70 border-emerald-400 text-white",
      "hover:!bg-emerald-400 hover:!border-emerald-200 hover:!text-white",
      "hover:shadow-xl hover:shadow-emerald-500/50",
      "hover:-translate-y-0.5 hover:scale-[1.05]",
      "active:scale-95 active:translate-y-0",
    ].join(" ");
  } else {
    styles = [
      "bg-white/10 border-white/20 text-white",
      "hover:!bg-fuchsia-500 hover:!text-[#0c0520] hover:!border-fuchsia-200",
      "hover:shadow-xl hover:shadow-fuchsia-500/50",
      "hover:-translate-y-0.5 hover:scale-[1.07]",
      "active:scale-95 active:translate-y-0",
    ].join(" ");
  }

  return (
    <button onClick={onClick} className={`${base} ${styles}`}>
      {label}
    </button>
  );
}




function SliderRow({
  label,
  value,
  onChange,
  min = -100,
  max = 100,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
}) {
  return (
    <div className="mb-3">
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="opacity-75">{label}</span>
        <span className="font-mono opacity-70">
          <span className="text-fuchsia-300 text-[20px]">{value}</span>
        </span>
      </div>
      <div className="flex">
        -100
        <input
          type="range"
          min={min}
          max={max}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full mx-2 accent-fuchsia-400 cursor-pointer "
        />
        100
      </div>

    </div>
  );
}


function MouseLookToggle({
  on,
  onToggle,
  variant = "default",
}: {
  on: boolean;
  onToggle: () => void;
  variant: string,
}) {
    const handleClick = () => {
    if (on) {
      // sắp tắt → gửi lệnh dừng xoay
      RobotAPI.move({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: 0 });
    }
    onToggle();
  };
  return (
    <Btn
      label={on ? "Mouse Look ON" : "Mouse Look OFF"}
      variant={on ? "success" : "default"}
      onClick={onToggle}
    />
  );
}