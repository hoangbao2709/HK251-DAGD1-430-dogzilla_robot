"use client";

import React from "react";
import { RobotAPI } from "@/app/lib/robotApi";

export function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="
      rounded-2xl
      bg-white/80 border border-slate-200
      dark:bg-white/5 dark:border-white/10
      p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]
    ">
      <div className="text-base font-semibold mb-4 opacity-90">{title}</div>
      {children}
    </div>
  );
}

export function Chip({
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
      ${
        active
          ? "bg-indigo-500/20 border-indigo-400/60 text-indigo-700 dark:text-indigo-100"
          : "bg-white/60 border-slate-300 text-slate-800 dark:bg-white/5 dark:border-white/10 dark:text-white hover:bg-white/80 dark:hover:bg-white/10"
      }`}
    >
      {label}
    </button>
  );
}

export function Btn({
  label,
  variant = "default",
  onClick,
}: {
  label: string;
  variant?: "default" | "danger" | "success";
  onClick?: () => void;
}) {
  const base =
    "px-4 py-2 text-sm rounded-xl border font-medium cursor-pointer " +
    "transition-all duration-200 transform select-none";

  let styles = "";

  if (variant === "danger") {
    styles = [
      "bg-rose-500 border-rose-500 text-white",
      "hover:bg-rose-400 hover:border-rose-300",
      "hover:shadow-xl hover:shadow-rose-500/40",
      "hover:-translate-y-0.5 hover:scale-[1.05]",
      "active:scale-95 active:translate-y-0",
    ].join(" ");
  } else if (variant === "success") {
    styles = [
      "bg-emerald-500 border-emerald-500 text-white",
      "hover:bg-emerald-400 hover:border-emerald-300",
      "hover:shadow-xl hover:shadow-emerald-500/40",
      "hover:-translate-y-0.5 hover:scale-[1.05]",
      "active:scale-95 active:translate-y-0",
    ].join(" ");
  } else {
    styles = [
      // light
      "bg-white border-slate-300 text-slate-900",
      // dark
      "dark:bg-white/10 dark:border-white/20 dark:text-white",
      "hover:bg-fuchsia-500 hover:text-[#0c0520] hover:border-fuchsia-200",
      "dark:hover:bg-fuchsia-500 dark:hover:text-[#0c0520] dark:hover:border-fuchsia-200",
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
        <span className="opacity-75">{label}</span>
        <span className="font-mono opacity-70">
          <span className="text-fuchsia-600 dark:text-fuchsia-300 text-[20px]">
            {value}
          </span>
        </span>
      </div>
      <div className="flex items-center text-[11px] text-slate-500 dark:text-slate-300">
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
}: {
  on: boolean;
  onToggle: () => void;
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
      onClick={handleClick}
    />
  );
}
