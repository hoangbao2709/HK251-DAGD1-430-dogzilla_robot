// app/lib/useGamepadMove.ts
"use client";

import { useEffect, useRef } from "react";
import { RobotAPI } from "@/app/lib/robotApi";

type GamepadSnapshot = {
  connected: boolean;
  axes: number[];
  buttons: boolean[];
};

const DEADZONE = 0.2;
const SEND_INTERVAL = 80; // ms
const MAX_V = 0.4; // m/s
const MAX_W = 1.2; // rad/s

type Options = {
  /** callback khi B0 (A) được nhấn – dùng để toggle LiDAR */
  onToggleLidar?: () => void;
  /** callback khi B2 (X) được nhấn – dùng để toggle stabilizing */
  onToggleStabilizing?: () => void;
};

/**
 * Đọc tay cầm và gửi lệnh move cho robot.
 * - Left stick: tiến/lùi + đi ngang
 * - B1 / B3: quay trái / quay phải
 * - Nếu truyền callback: B0 toggle LiDAR, B2 toggle stabilizing
 */
export function useGamepadMove(opts: Options = {}) {
  const { onToggleLidar, onToggleStabilizing } = opts;

  const padRef = useRef<GamepadSnapshot>({
    connected: false,
    axes: [],
    buttons: [],
  });

  const lastMoveRef = useRef<{ vx: number; vy: number; rz: number }>({
    vx: 0,
    vy: 0,
    rz: 0,
  });

  const lastButtonsRef = useRef<boolean[]>([]);
  const loggedMappingRef = useRef(false);

  // Read gamepad state bằng requestAnimationFrame
  useEffect(() => {
    if (typeof window === "undefined") return;
    const nav: any = navigator;
    if (!nav.getGamepads) {
      console.warn("Browser không hỗ trợ Gamepad API");
      return;
    }

    let rafId: number | null = null;

    const loop = () => {
      const pads = nav.getGamepads() as (Gamepad | null)[];
      const gp = pads[0];

      if (gp) {
        padRef.current = {
          connected: true,
          axes: gp.axes.slice(),
          buttons: gp.buttons.map((b) => b.pressed),
        };

        if (!loggedMappingRef.current) {
          console.log("[Gamepad] axes sample:", gp.axes);
          console.log(
            "[Gamepad] buttons sample:",
            gp.buttons.map((b) => b.pressed)
          );
          loggedMappingRef.current = true;
        }
      } else {
        padRef.current = { connected: false, axes: [], buttons: [] };
      }

      rafId = requestAnimationFrame(loop);
    };

    const handleConnect = (e: GamepadEvent) => {
      console.log("Gamepad connected:", e.gamepad.id);
      if (rafId == null) {
        rafId = requestAnimationFrame(loop);
      }
    };

    const handleDisconnect = (e: GamepadEvent) => {
      console.log("Gamepad disconnected:", e.gamepad.id);
      padRef.current = { connected: false, axes: [], buttons: [] };
    };

    window.addEventListener("gamepadconnected", handleConnect);
    window.addEventListener("gamepaddisconnected", handleDisconnect);

    // nếu tay cầm đã cắm sẵn khi load trang
    const pads = nav.getGamepads() as (Gamepad | null)[];
    if (pads[0]) {
      rafId = requestAnimationFrame(loop);
    }

    return () => {
      window.removeEventListener("gamepadconnected", handleConnect);
      window.removeEventListener("gamepaddisconnected", handleDisconnect);
      if (rafId != null) cancelAnimationFrame(rafId);
    };
  }, []);

  // Map gamepad → move + callback nút B0/B2
  useEffect(() => {
    const timer = setInterval(() => {
      const snap = padRef.current;
      if (!snap.connected) return;

      const axes = snap.axes;
      const buttons = snap.buttons;
      const lastButtons = lastButtonsRef.current;

      // ===== LEFT STICK: move =====
      // Axis 0 = left X (strafe), Axis 1 = left Y (forward/back)
      const axLX = axes[0] ?? 0;
      const axLY = axes[1] ?? 0;

      let fwd = -axLY; // lên = tiến
      let strafe = axLX; // trái / phải

      if (Math.abs(fwd) < DEADZONE) fwd = 0;
      if (Math.abs(strafe) < DEADZONE) strafe = 0;

      const vx = fwd * MAX_V;
      const vy = strafe * MAX_V;

      // ===== B1 / B3: rotate =====
      const btnB1 = buttons[1] ?? false; // xoay trái
      const btnB3 = buttons[3] ?? false; // xoay phải
      let yaw = 0;
      if (btnB1 && !btnB3) yaw = +1;
      else if (btnB3 && !btnB1) yaw = -1;

      const rz = yaw * MAX_W;

      // ===== gửi lệnh move nếu thay đổi =====
      const last = lastMoveRef.current;
      if (
        Math.abs(vx - last.vx) > 0.01 ||
        Math.abs(vy - last.vy) > 0.01 ||
        Math.abs(rz - last.rz) > 0.01
      ) {
        lastMoveRef.current = { vx, vy, rz };
        RobotAPI.move({ vx, vy, vz: 0, rx: 0, ry: 0, rz }).catch(() => {});
      }

      // ===== B0: toggle LiDAR (nếu có callback) =====
      const btnB0 = buttons[0] ?? false;
      const prevB0 = lastButtons[0] ?? false;
      if (btnB0 && !prevB0 && onToggleLidar) {
        onToggleLidar();
      }

      // ===== B2: toggle stabilizing_mode (nếu có callback) =====
      const btnB2 = buttons[2] ?? false;
      const prevB2 = lastButtons[2] ?? false;
      if (btnB2 && !prevB2 && onToggleStabilizing) {
        onToggleStabilizing();
      }

      lastButtonsRef.current = buttons.slice();
    }, SEND_INTERVAL);

    return () => {
      clearInterval(timer);
      // dừng robot khi rời trang
      RobotAPI.move({
        vx: 0,
        vy: 0,
        vz: 0,
        rx: 0,
        ry: 0,
        rz: 0,
      }).catch(() => {});
    };
  }, [onToggleLidar, onToggleStabilizing]);
}
