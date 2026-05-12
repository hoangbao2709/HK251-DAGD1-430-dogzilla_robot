"use client";

import React from "react";
import { RobotAPI } from "@/app/lib/robotApi";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

function useIsDarkMode() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  return mounted && resolvedTheme === "dark";
}

export function Panel({
  title,
  children,
  tone = "violet",
}: {
  title: string;
  children: React.ReactNode;
  tone?: "violet" | "cyan" | "pink" | "emerald";
}) {
  const isDark = useIsDarkMode();

  const toneStyles = {
    violet: isDark
      ? "bg-[linear-gradient(90deg,rgba(92,56,180,0.58),rgba(53,24,96,0.92))] text-white"
      : "bg-[#E8DDFF] text-[#2C165A]",
    cyan: isDark
      ? "bg-[linear-gradient(90deg,rgba(8,83,112,0.65),rgba(7,38,60,0.95))] text-white"
      : "bg-[#D9F5FF] text-[#12374A]",
    pink: isDark
      ? "bg-[linear-gradient(90deg,rgba(142,42,86,0.68),rgba(62,18,40,0.95))] text-white"
      : "bg-[#FFD8E7] text-[#5A1436]",
    emerald: isDark
      ? "bg-[linear-gradient(90deg,rgba(18,108,64,0.68),rgba(12,45,30,0.95))] text-white"
      : "bg-[#D8F7E3] text-[#12412A]",
  }[tone];

  const baseStyles = isDark
    ? "bg-[linear-gradient(180deg,rgba(17,7,31,0.98),rgba(10,4,20,0.98))] border border-[rgba(255,255,255,0.08)] shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_14px_28px_rgba(0,0,0,0.34)]"
    : "bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,244,255,0.96))] border border-[var(--border)] shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_10px_24px_rgba(124,77,255,0.05)]";

  return (
    <div className={`rounded-2xl p-5 ${baseStyles}`}>
      <div className={`-mx-5 -mt-5 mb-4 rounded-t-2xl px-5 pt-4 pb-3 ${toneStyles}`}>
        <div className={`text-base font-bold ${isDark ? "text-white" : "text-[#24163f]"}`}>
          {title}
        </div>
      </div>
      {children}
    </div>
  );
}

export function Chip({
  label,
  active,
  onClick,
  disabled,
}: {
  label: string;
  active?: boolean;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-4 py-1 rounded-xl text-sm border transition
      ${
        active
          ? "bg-indigo-500/20 border-indigo-400/60 text-[var(--foreground)]"
          : "bg-[var(--surface-2)] border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--surface-elev)]"
      } ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
    >
      {label}
    </button>
  );
}

export function Btn({
  label,
  variant = "default",
  tone = "violet",
  className = "",
  onClick,
}: {
  label: string;
  variant?: "default" | "danger" | "success";
  tone?: "violet" | "cyan" | "pink" | "emerald";
  className?: string;
  onClick?: () => void;
}) {
  const isDark = useIsDarkMode();

  const base =
    "px-3 py-2 text-xs rounded-xl border font-semibold cursor-pointer whitespace-nowrap " +
    "transition-all duration-200 transform select-none";

  let styles = "";

  if (variant === "danger") {
      styles = [
        isDark ? "bg-[rgba(120,22,62,0.78)] border-[rgba(255,120,166,0.35)] text-white" : "bg-rose-500 border-rose-500 text-white",
      isDark ? "hover:bg-[rgba(146,27,75,0.92)] hover:border-[rgba(255,120,166,0.5)]" : "hover:bg-rose-400 hover:border-rose-300",
      "hover:shadow-xl hover:shadow-rose-500/40",
      "hover:-translate-y-0.5 hover:scale-[1.05]",
      "active:scale-95 active:translate-y-0",
    ].join(" ");
  } else if (variant === "success") {
    styles = [
      isDark ? "bg-[rgba(14,97,56,0.82)] border-[rgba(66,211,132,0.35)] text-white" : "bg-emerald-500 border-emerald-500 text-white",
      isDark ? "hover:bg-[rgba(18,114,67,0.96)] hover:border-[rgba(66,211,132,0.5)]" : "hover:bg-emerald-400 hover:border-emerald-300",
      "hover:shadow-xl hover:shadow-emerald-500/40",
      "hover:-translate-y-0.5 hover:scale-[1.05]",
      "active:scale-95 active:translate-y-0",
    ].join(" ");
  } else {
    const toneFill =
      tone === "cyan"
        ? isDark
          ? "bg-[rgba(7,75,103,0.88)] border-[rgba(0,194,255,0.34)] text-white"
          : "bg-[#D9F5FF] border-[#7FD9F8] text-[#0E3752]"
        : tone === "pink"
        ? isDark
          ? "bg-[rgba(95,28,63,0.88)] border-[rgba(253,116,155,0.34)] text-white"
          : "bg-[#FFD8E7] border-[#F6A8C7] text-[#5A1436]"
        : tone === "emerald"
        ? isDark
          ? "bg-[rgba(14,83,48,0.88)] border-[rgba(34,197,94,0.34)] text-white"
          : "bg-[#D8F7E3] border-[#8AE0A8] text-[#12412A]"
        : isDark
        ? "bg-[rgba(61,31,124,0.88)] border-[rgba(124,77,255,0.34)] text-white"
        : "bg-[#E8DDFF] border-[#B89DFF] text-[#2C165A]";

    styles = [
      toneFill,
      isDark ? "hover:brightness-110" : "hover:brightness-105",
      "hover:shadow-lg",
      "hover:-translate-y-0.5 hover:scale-[1.07]",
      "active:scale-95 active:translate-y-0",
    ].join(" ");
  }

  return (
    <button onClick={onClick} className={`cursor-pointer ${base} ${styles} ${className}`}>
      {label}
    </button>
  );
}

export function SliderRow({
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
        <span className="opacity-75 text-[var(--foreground)]">{label}</span>
        <span className="font-mono opacity-70">
          <span className="text-fuchsia-600 dark:text-fuchsia-300 text-[20px]">
            {value}
          </span>
        </span>
      </div>
      <div className="flex items-center text-[11px] text-[var(--muted)]">
        -100
        <input
          type="range"
          min={min}
          max={max}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full mx-2 accent-fuchsia-500"
        />
        100
      </div>
    </div>
  );
}

export function MouseLookToggle({
  on,
  onToggle,
  variant,
}: {
  on: boolean;
  onToggle: () => void;
  variant: string,
}) {
  const handleClick = () => {
    if (on) {
      RobotAPI.move({ vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: 0 });
    }
    onToggle();
  };

  return (
    <Btn
      label={on ? "Mouse Look ON" : "Mouse Look OFF"}
      variant={on ? "success" : "default"}
      tone="cyan"
      onClick={handleClick}
    />
  );
}
