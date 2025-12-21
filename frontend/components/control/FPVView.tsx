"use client";

import React, { useEffect, useRef, useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import { RobotAPI, DEFAULT_DOG_SERVER } from "@/app/lib/robotApi";
import { Panel, Btn, SliderRow } from "@/components/control/ControlUI";
import { useGamepadMove } from "@/app/lib/useGamepadMove";

export default function FPVView({
  fps = 30,
  onEmergencyStop,
}: {
  fps?: number;
  onEmergencyStop?: () => void;
}) {
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

  const [stabilizingOn, setStabilizingOn] = useState(false);
  const [lidarRunning, setLidarRunning] = useState(false);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  const searchParams = useSearchParams();
  const ipParam = searchParams.get("ip");
  const DOG_SERVER = ipParam || DEFAULT_DOG_SERVER;
  const hasResetBody = useRef(false);

  /* ===== BODY ADJUST ===== */

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

  useEffect(
    () => () => {
      if (bodyTimer.current) clearTimeout(bodyTimer.current);
    },
    []
  );

  /* ===== CONNECT + FPV ===== */

  useEffect(() => {
    let stop = false;

    (async () => {
      try {
        const res = await RobotAPI.connect(DOG_SERVER);
        if (stop) return;

        if (res?.connected) {
          setConnected(true);
          setConnectError(null);
          if (!hasResetBody.current) {
            resetBody();
            hasResetBody.current = true;
          }
          try {
            const f = await RobotAPI.fpv();
            if (!stop) setStreamUrl(f?.stream_url || null);
          } catch (e) {
            console.error("FPV error:", e);
            if (!stop) setConnectError("Không lấy được stream_url từ backend");
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
      }
    })();

    const iv = setInterval(async () => {
      try {
        // có thể poll status nếu cần
      } catch {}
    }, 2000);

    return () => {
      stop = true;
      clearInterval(iv);
      onEmergencyStop?.();
    };
  }, [DOG_SERVER, onEmergencyStop, resetBody]);

  /* ===== HANDLERS toggle từ nút & gamepad ===== */

  const toggleLidar = useCallback(() => {
    setLidarRunning((prev) => {
      const next = !prev;
      RobotAPI.lidar(next ? "start" : "stop").catch(() => {});
      return next;
    });
  }, []);

  const toggleStabilizing = useCallback(() => {
    setStabilizingOn((prev) => {
      const next = !prev;
      RobotAPI.stabilizingMode("toggle").catch(() => {});
      return next;
    });
  }, []);

  // DÙNG HOOK GAMEPAD: di chuyển + dùng B0/B2 để gọi 2 callback trên
  useGamepadMove({
    onToggleLidar: toggleLidar,
    onToggleStabilizing: toggleStabilizing,
  });

  /* ===== UI ===== */

  return (
    <div className="space-y-6">
      {/* FPV video */}
      <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-black shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
        <div className="absolute left-3 top-2 text-green-300 text-xl font-bold drop-shadow">
          FPS: {fps}
        </div>
        <img
          src={streamUrl || "/placeholder.svg?height=360&width=640"}
          alt="FPV"
          className="w-full aspect-[16/7] object-cover"
        />
      </div>

      {/* Body + behavior */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
        {/* LEFT — Body */}
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

        {/* RIGHT — postures & behaviors */}
        <div className="flex flex-col gap-6">
          <Panel title="Basic Postures">
            <div className="grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-3">
              {postureBtns.map((b) => (
                <Btn
                  key={b}
                  label={b.replaceAll("_", " ")}
                  onClick={() => RobotAPI.posture(b)}
                />
              ))}
            </div>
          </Panel>

          <Panel title="Axis Motion">
            <div className="grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-3">
              {axisMotionBtns.map((b) => (
                <Btn
                  key={b}
                  label={b.replaceAll("_", " ")}
                  onClick={() => RobotAPI.behavior(b)}
                />
              ))}
            </div>
          </Panel>

          <Panel title="Behavior Control">
            <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-3">
              {[...behavior1, ...behavior2].map((b, i) => (
                <Btn
                  key={`${b}-${i}`}
                  label={b.replaceAll("_", " ")}
                  onClick={() => RobotAPI.behavior(b)}
                />
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
