// app/lib/useRobotDrive.ts
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type MoveCommand = {
  vx: number;
  vy: number;
  vz: number;
  rx: number;
  ry: number;
  rz: number;
};

type UseRobotDriveOptions = {
  enableGamepad?: boolean;
  onToggleLidar?: () => void;
  onToggleStabilizing?: () => void;
};

const JOY_MAX_V = 0.25;
const JOY_MAX_SIDE_V = 0.25;

const GAMEPAD_MAX_V = 0.4;
const GAMEPAD_MAX_W = 1.2;
const DEADZONE = 0.2;
const SEND_INTERVAL = 80; // ms

const TURN_W = 0.8; // dùng cho 2 nút < >

type GamepadSnapshot = {
  connected: boolean;
  axes: number[];
  buttons: boolean[];
};

export function useRobotDrive(
  sendMove: (cmd: MoveCommand) => void | Promise<void>,
  opts: UseRobotDriveOptions = {}
) {
  const { enableGamepad = true, onToggleLidar, onToggleStabilizing } = opts;

  // ================== JOYSTICK ==================
  const joyRef = useRef<{ vx: number; vy: number; active: boolean }>({
    vx: 0,
    vy: 0,
    active: false,
  });

  const [lefting, setLefting] = useState(false);
  const [righting, setRighting] = useState(false);

  // interval gửi lệnh khi joystick đang active
  useEffect(() => {
    const timer = setInterval(() => {
      const { vx, vy, active } = joyRef.current;
      if (!active) return;

      sendMove({ vx, vy, vz: 0, rx: 0, ry: 0, rz: 0 });
    }, SEND_INTERVAL);

    return () => clearInterval(timer);
  }, [sendMove]);

    const onJoyChange = useCallback(
    ({ angleDeg, power }: { angleDeg: number; power: number }) => {
        // h?y tr?ng thái quay khi ch?m joystick
        setLefting(false);
        setRighting(false);

        const rad = (angleDeg * Math.PI) / 180;
        const forward = Math.cos(rad) * power;
        const strafe = Math.sin(rad) * power;

        const vx = forward * JOY_MAX_V;
        const vy = strafe * JOY_MAX_SIDE_V;

        joyRef.current = { vx, vy, active: power > 0.01 };
    },
    []
    );


  const onJoyRelease = useCallback(() => {
    joyRef.current = { vx: 0, vy: 0, active: false };
    sendMove({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: 0 });
  }, [sendMove]);

  // ================== NÚT QUAY / STOP ==================
  const clearJoy = () => {
    joyRef.current = { vx: 0, vy: 0, active: false };
};
  const turnLeft = useCallback(() => {
    clearJoy();   
    setRighting(false);
    setLefting((cur) => {
      const next = !cur;
      sendMove({
        vx: 0,
        vy: 0,
        vz: 0,
        rx: 0,
        ry: 0,
        rz: next ? +TURN_W : 0,
      });
      return next;
    });
  }, [sendMove]);

  const turnRight = useCallback(() => {
    clearJoy();   
    setLefting(false);
    setRighting((cur) => {
      const next = !cur;
      sendMove({
        vx: 0,
        vy: 0,
        vz: 0,
        rx: 0,
        ry: 0,
        rz: next ? -TURN_W : 0,
      });
      return next;
    });
  }, [sendMove]);

  const stop = useCallback(() => {
    clearJoy(); 
    setLefting(false);
    setRighting(false);
    sendMove({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: 0 });
  }, [sendMove]);

  // ================== GAMEPAD ==================
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

  useEffect(() => {
    if (!enableGamepad) return;
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
  }, [enableGamepad]);

  useEffect(() => {
    if (!enableGamepad) return;

    const timer = setInterval(() => {
      const snap = padRef.current;
      if (!snap.connected) return;

      const axes = snap.axes;
      const buttons = snap.buttons;
      const lastButtons = lastButtonsRef.current;

      // LEFT STICK: move (axis 0 = strafe, axis 1 = forward/back)
      const axLX = axes[0] ?? 0;
      const axLY = axes[1] ?? 0;

      let fwd = -axLY;
      let strafe = axLX;

      if (Math.abs(fwd) < DEADZONE) fwd = 0;
      if (Math.abs(strafe) < DEADZONE) strafe = 0;

      const vx = fwd * GAMEPAD_MAX_V;
      const vy = strafe * GAMEPAD_MAX_V;

      // B1 / B3: rotate
      const btnB1 = buttons[1] ?? false; // xoay trái
      const btnB3 = buttons[3] ?? false; // xoay phải
      let yaw = 0;
      if (btnB1 && !btnB3) yaw = +1;
      else if (btnB3 && !btnB1) yaw = -1;

      const rz = yaw * GAMEPAD_MAX_W;

      const last = lastMoveRef.current;
      if (
        Math.abs(vx - last.vx) > 0.01 ||
        Math.abs(vy - last.vy) > 0.01 ||
        Math.abs(rz - last.rz) > 0.01
      ) {
        lastMoveRef.current = { vx, vy, rz };
        sendMove({ vx, vy, vz: 0, rx: 0, ry: 0, rz });
      }

      // B0: toggle LiDAR
      const btnB0 = buttons[0] ?? false;
      const prevB0 = lastButtons[0] ?? false;
      if (btnB0 && !prevB0 && onToggleLidar) {
        onToggleLidar();
      }

      // B2: toggle stabilizing
      const btnB2 = buttons[2] ?? false;
      const prevB2 = lastButtons[2] ?? false;
      if (btnB2 && !prevB2 && onToggleStabilizing) {
        onToggleStabilizing();
      }

      lastButtonsRef.current = buttons.slice();
    }, SEND_INTERVAL);

    return () => {
      clearInterval(timer);
      // stop when unmount
      sendMove({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: 0 });
    };
  }, [enableGamepad, onToggleLidar, onToggleStabilizing, sendMove]);

  return {
    // joystick
    onJoyChange,
    onJoyRelease,
    // buttons
    turnLeft,
    turnRight,
    stop,
    lefting,
    righting,
  };
}
