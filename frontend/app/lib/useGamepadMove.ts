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
const SEND_INTERVAL = 80;
const MAX_V = 0.4; 
const MAX_W = 1.2; 

type Options = {
  onToggleLidar?: () => void;
  onToggleStabilizing?: () => void;
  onLog?: (line: string) => void;
};

function errorText(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error || "Unknown error");
}

export function useGamepadMove(opts: Options = {}) {
  const { onToggleLidar, onToggleStabilizing, onLog } = opts;

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

  useEffect(() => {
    const timer = setInterval(() => {
      const snap = padRef.current;
      if (!snap.connected) return;

      const axes = snap.axes;
      const buttons = snap.buttons;
      const lastButtons = lastButtonsRef.current;

      const axLX = axes[0] ?? 0;
      const axLY = axes[1] ?? 0;

      let fwd = -axLY;
      let strafe = axLX; 

      if (Math.abs(fwd) < DEADZONE) fwd = 0;
      if (Math.abs(strafe) < DEADZONE) strafe = 0;

      const vx = fwd * MAX_V;
      const vy = strafe * MAX_V;

      const btnB1 = buttons[1] ?? false;
      const btnB3 = buttons[3] ?? false; 
      let yaw = 0;
      if (btnB1 && !btnB3) yaw = +1;
      else if (btnB3 && !btnB1) yaw = -1;

      const rz = yaw * MAX_W;

      const last = lastMoveRef.current;
      if (
        Math.abs(vx - last.vx) > 0.01 ||
        Math.abs(vy - last.vy) > 0.01 ||
        Math.abs(rz - last.rz) > 0.01
      ) {
        lastMoveRef.current = { vx, vy, rz };
        RobotAPI.move({ vx, vy, vz: 0, rx: 0, ry: 0, rz }).catch((error) => {
          onLog?.(`[GAMEPAD MOVE ERROR] ${errorText(error)}`);
        });
      }

      const btnB0 = buttons[0] ?? false;
      const prevB0 = lastButtons[0] ?? false;
      if (btnB0 && !prevB0 && onToggleLidar) {
        onToggleLidar();
      }

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
      }).catch((error) => {
        onLog?.(`[GAMEPAD STOP ERROR] ${errorText(error)}`);
      });
    };
  }, [onToggleLidar, onToggleStabilizing, onLog]);
}
