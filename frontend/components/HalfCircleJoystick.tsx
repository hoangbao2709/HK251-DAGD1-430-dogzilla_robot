"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type JoystickChange = { angleDeg: number; power: number };

type CircleJoystickProps = {
  width?: number;
  height?: number;
  knobRadius?: number;
  onChange?: (data: JoystickChange) => void;
  onRelease?: () => void;
  disabled?: boolean;
  className?: string;
  rest?: "center" | "top" | { x: number; y: number };
};

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v));
}

function HalfCircleJoystick({
  width = 260,
  height = 260,
  knobRadius = 14,
  onChange,
  onRelease,
  disabled = false,
  className = "",
  rest = "center",
}: CircleJoystickProps) {
  const strokeWidth = 6;
  const pad = 12;

  const cx = Math.round(width / 2) + 0.5;
  const cy = Math.round(height / 2) + 0.5;
  const R = Math.min(cx, cy) - pad - strokeWidth / 2;

  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragging = useRef(false);
  const [knob, setKnob] = useState<{ x: number; y: number } | null>(null);
  const [isPressed, setIsPressed] = useState(false);

  const restPos = useMemo(() => {
    if (typeof rest === "object") return rest;
    if (rest === "top") return { x: cx, y: cy - R * 0.7 };
    return { x: cx, y: cy };
  }, [cx, cy, R, rest]);

  const getLocalPoint = useCallback((clientX: number, clientY: number) => {
    if (!svgRef.current) return { x: cx, y: cy };
    const bbox = svgRef.current.getBoundingClientRect();
    const x = clientX - bbox.left;
    const y = clientY - bbox.top;
    return { x, y };
  }, [cx, cy]);

  const projectToCircle = useCallback(
    (pt: { x: number; y: number }) => {
      let dx = pt.x - cx;
      let dy = pt.y - cy;
      const dist = Math.hypot(dx, dy);
      if (dist <= R) return pt;
      const k = R / (dist || 1);
      return { x: cx + dx * k, y: cy + dy * k };
    },
    [cx, cy, R]
  );

  const computeOutput = useCallback(
    (p: { x: number; y: number }) => {
      const vx = p.x - cx;
      const vy = p.y - cy;
      const dist = Math.hypot(vx, vy);
      const power = clamp(dist / R, 0, 1);

      // 0° = lên trên, quay clockwise là dương
      const angleRad = Math.atan2(vx, -vy);
      const angleDeg = (angleRad * 180) / Math.PI;
      return { angleDeg, power } as JoystickChange;
    },
    [cx, cy, R]
  );

  const setFromClient = useCallback(
    (clientX: number, clientY: number) => {
      if (!svgRef.current) return;
      const local = getLocalPoint(clientX, clientY);
      const p = projectToCircle(local);
      setKnob({ x: p.x, y: p.y });
      onChange?.(computeOutput(p));
    },
    [computeOutput, getLocalPoint, onChange, projectToCircle]
  );

  const endDrag = useCallback(() => {
    if (!dragging.current) return;
    dragging.current = false;
    setIsPressed(false);
    setKnob(null);
    onChange?.({ angleDeg: 0, power: 0 });
    onRelease?.();
  }, [onChange, onRelease]);

  // ===== Pointer (mouse / pen) =====
  const handlePointerDown = (e: React.PointerEvent) => {
    if (disabled) return;
    dragging.current = true;
    setIsPressed(true);
    setFromClient(e.clientX, e.clientY);
  };

  const handlePointerMove = (e: PointerEvent) => {
    if (!dragging.current || disabled) return;
    setFromClient(e.clientX, e.clientY);
  };

  // ===== Touch fallback (điện thoại không hỗ trợ pointer events chuẩn) =====
  const handleTouchStart = (e: React.TouchEvent) => {
    if (disabled) return;
    dragging.current = true;
    setIsPressed(true);
    const t = e.touches[0];
    if (!t) return;
    setFromClient(t.clientX, t.clientY);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!dragging.current || disabled) return;
    const t = e.touches[0];
    if (!t) return;
    setFromClient(t.clientX, t.clientY);
  };

  const handleTouchEnd = () => {
    endDrag();
  };

  useEffect(() => {
    // pointermove trên window cho mouse/pen
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", endDrag);
      window.removeEventListener("pointercancel", endDrag);
    };
  }, [endDrag]);

  const knobPos = knob ?? restPos;
  const fx = (v: number) => Math.round(v) + 0.5;

  return (
    <div
      className={`select-none ${disabled ? "opacity-50" : ""} ${className}`}
      aria-disabled={disabled}
      style={{ touchAction: "none" }} 
    >
      <svg
        ref={svgRef}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="rounded-2xl bg-transparent"
        onPointerDown={handlePointerDown}
        onPointerUp={() => endDrag()}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onTouchCancel={handleTouchEnd}
        role="slider"
        aria-valuemin={-180}
        aria-valuemax={180}
        aria-label="Circle joystick"
      >
        <defs>
          <radialGradient id="padGlowCircle" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="#2dd4bf" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="trackCircle" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#93c5fd" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
        </defs>

        {/* nền + viền */}
        <circle cx={cx} cy={cy} r={R} fill="url(#padGlowCircle)" stroke="none" />
        <circle
          cx={cx}
          cy={cy}
          r={R}
          className="[stroke:url(#trackCircle)]"
          strokeWidth={strokeWidth}
          fill="none"
        />

        {/* tick marks 8 hướng */}
        {Array.from({ length: 8 }).map((_, i) => {
          const rad = (i * Math.PI) / 4;
          const inner = 10;
          const x1 = fx(cx + R * Math.cos(rad));
          const y1 = fx(cy + R * Math.sin(rad));
          const x2 = fx(cx + (R - inner) * Math.cos(rad));
          const y2 = fx(cy + (R - inner) * Math.sin(rad));
          return (
            <line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              className="stroke-slate-400/60"
              strokeWidth={i % 2 === 0 ? 2.5 : 1.5}
              strokeLinecap="round"
            />
          );
        })}

        {/* guide line */}
        <line
          x1={cx}
          y1={cy}
          x2={knobPos.x}
          y2={knobPos.y}
          className={`${isPressed ? "opacity-80" : "opacity-40"} stroke-cyan-300`}
          strokeWidth={2}
          strokeLinecap="round"
        />

        {/* knob */}
        <g>
          <circle
            cx={knobPos.x}
            cy={knobPos.y}
            r={knobRadius}
            className="fill-white/95"
            style={{ filter: "drop-shadow(0 6px 10px rgba(0,0,0,0.35))" }}
          />
          <circle
            cx={knobPos.x}
            cy={knobPos.y}
            r={knobRadius - 5}
            className="fill-cyan-400/90"
          />
          <circle cx={knobPos.x} cy={knobPos.y} r={3} className="fill-white" />
        </g>
      </svg>
    </div>
  );
}

export { HalfCircleJoystick };
