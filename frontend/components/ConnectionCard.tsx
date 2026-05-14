"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

export type Device = {
  id: number;
  name: string;
  ip: string;
  battery: number;
  url?: string;
  status: "online" | "offline" | "unknown";
};

type CardStatus = {
  status: "online" | "offline" | "unknown";
  battery: number | null;
};

export default function ConnectionCard({
  device,
  onConnect,
  onDelete,
}: {
  device: Device;
  onConnect?: (device: Device) => void | Promise<void>;
  onDelete?: (device: Device) => void | Promise<void>;
}) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [info, setInfo] = useState<CardStatus>({
    status: "unknown",
    battery: null,
  });

  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = mounted && resolvedTheme === "dark";
  const cardClass = isDark
    ? "bg-[#160a28] border border-white/10"
    : "bg-[#ffffff] border border-[#dacfff]";

  function buildRobotBase() {
    const base = device.ip.trim();
    if (base.startsWith("http://") || base.startsWith("https://")) {
      return base.replace(/\/+$/, "");
    }
    if (base.includes(":")) {
      return `http://${base.replace(/\/+$/, "")}`;
    }
    return `http://${base}:9000`;
  }

  useEffect(() => {
    let alive = true;
    let inFlight = false;

    async function fetchStatus() {
      if (inFlight) return;
      inFlight = true;
      const base = buildRobotBase();
      try {
        const res = await fetch(`${base}/status`, { cache: "no-store" });
        if (!alive) return;
        if (!res.ok) throw new Error("Bad status");

        const data = await res.json().catch(() => ({} as any));
        setInfo({
          status: "online",
          battery: data.battery ?? null,
        });
      } catch (err) {
        if (!alive) return;
        console.warn(`status error for ${device.name}:`, err);
        setInfo({
          status: "offline",
          battery: null,
        });
      } finally {
        inFlight = false;
      }
    }

    fetchStatus();
    const timer = setInterval(fetchStatus, 5000);

    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [device.ip, device.name]);

  const statusClass =
    info.status === "online"
      ? isDark
        ? "bg-emerald-500/15 text-emerald-300"
        : "bg-emerald-500/10 text-emerald-700"
      : info.status === "offline"
      ? isDark
        ? "bg-rose-500/15 text-rose-300"
        : "bg-rose-500/10 text-rose-700"
      : isDark
      ? "bg-yellow-500/15 text-yellow-200"
      : "bg-yellow-500/10 text-yellow-700";

  const batteryText =
    info.battery != null ? `${info.battery}%` : info.status === "offline" ? "-" : "...";

  return (
    <div className={`flex items-center justify-between rounded-2xl p-4 ${cardClass}`}>
      <div>
        <div className={`flex items-center gap-2 font-semibold ${isDark ? "text-white" : "text-[#1f1640]"}`}>
          <span>{device.name}</span>
          <span className={`rounded-full px-2 py-0.5 text-xs ${statusClass}`}>
            {info.status}
          </span>
        </div>

        <div className={`text-sm ${isDark ? "text-white/70" : "text-[#564a76]"}`}>
          IP: {device.ip}
        </div>
        <div className={`text-sm ${isDark ? "text-white/70" : "text-[#564a76]"}`}>
          Battery: {batteryText}
        </div>
      </div>

      <div className="flex flex-col items-end gap-2">
        <button onClick={() => onConnect?.(device)}
          className={`cursor-pointer w-24 rounded-xl px-4 py-2 text-center text-sm transition ${
            isDark
              ? "bg-[#fd749b] text-white hover:bg-[#f05b86]"
              : "bg-[#7c4dff] text-white hover:bg-[#693be6]"
          }`}
        >
          Connect
        </button>

        {onDelete && (
          <button onClick={() => onDelete(device)}
            className={`cursor-pointer w-24 rounded-xl px-4 py-1 text-center text-xs transition ${
              isDark
                ? "bg-rose-500/15 text-rose-200 hover:bg-rose-500/25"
                : "bg-rose-500/10 text-rose-700 hover:bg-rose-500/20"
            }`}
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
