"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { X } from "lucide-react";
import { getStoredSession } from "@/app/lib/auth";

export type Device = {
  id: number;
  name: string;
  ip: string;
  battery: number;
  url?: string;
  status: "online" | "offline" | "unknown";
  source?: "session" | "database";
};

type CardStatus = {
  status: "online" | "offline" | "unknown";
  battery: number | null;
};

export default function ConnectionCard({
  device,
  onConnect,
  onRememberAndConnect,
  onDelete,
}: {
  device: Device;
  onConnect?: (device: Device) => void | Promise<void>;
  onRememberAndConnect?: (device: Device) => void | Promise<void>;
  onDelete?: (device: Device) => void | Promise<void>;
}) {
  const { resolvedTheme } = useTheme();

  const [mounted, setMounted] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [loadingAction, setLoadingAction] = useState<
    "connect" | "remember" | null
  >(null);

  const [info, setInfo] = useState<CardStatus>({
    status: "unknown",
    battery: null,
  });

  useEffect(() => {
    setMounted(true);

    const session = getStoredSession();
    setIsLoggedIn(Boolean(session?.access));
  }, []);

  const isDark = mounted && resolvedTheme === "dark";
  const isSaved = device.source === "database";

  const cardClass = isSaved
    ? isDark
      ? [
        "relative overflow-hidden",
        "bg-gradient-to-r from-[#241233] via-[#1b1838] to-[#16263f]",
        "border border-[#5b6ee1]/45",
        "shadow-[0_10px_30px_rgba(91,110,225,0.18)]",
        "before:absolute before:inset-0",
        "before:bg-[radial-gradient(circle_at_12%_20%,rgba(255,255,255,0.06),transparent_28%),radial-gradient(circle_at_85%_30%,rgba(124,77,255,0.10),transparent_30%)]",
        "before:pointer-events-none",
      ].join(" ")
      : [
        "relative overflow-hidden",
        "bg-gradient-to-r from-[#ffffff] via-[#f8f5ff] to-[#eef3ff]",
        "border border-[#b9c6ff]",
        "shadow-[0_8px_24px_rgba(91,110,225,0.12)]",
        "before:absolute before:inset-0",
        "before:bg-[radial-gradient(circle_at_12%_20%,rgba(124,77,255,0.07),transparent_28%),radial-gradient(circle_at_85%_30%,rgba(91,110,225,0.08),transparent_30%)]",
        "before:pointer-events-none",
      ].join(" ")
    : isDark
      ? "bg-[#160a28] border border-white/10"
      : "bg-white border border-[#dacfff]";

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

    async function fetchStatus() {
      const base = buildRobotBase();

      try {
        const res = await fetch(`${base}/status`, {
          cache: "no-store",
        });

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
      }
    }

    fetchStatus();

    const timer = setInterval(fetchStatus, 2000);

    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [device.ip, device.name]);

  async function handleOpenConnect() {
    if (device.source === "database") {
      await onConnect?.(device);
      return;
    }

    if (isLoggedIn && onRememberAndConnect) {
      setModalOpen(true);
      return;
    }

    await onConnect?.(device);
  }

  async function handleJustConnect() {
    try {
      setLoadingAction("connect");
      await onConnect?.(device);
      setModalOpen(false);
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleRememberConnect() {
    try {
      setLoadingAction("remember");
      await onRememberAndConnect?.(device);
      setModalOpen(false);
    } finally {
      setLoadingAction(null);
    }
  }

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
    info.battery != null
      ? `${info.battery}%`
      : info.status === "offline"
        ? "-"
        : "...";

  return (
    <>
      <div className={`rounded-2xl p-4 transition ${cardClass}`}>
        <div className="relative z-10 flex items-center justify-between">
          <div className="min-w-0">
            <div
              className={`flex flex-wrap items-center gap-2 font-semibold ${isDark ? "text-white" : "text-[#1f1640]"
                }`}
            >
              <span>{device.name}</span>

              <span
                className={`rounded-full px-2 py-0.5 text-xs ${statusClass}`}
              >
                {info.status}
              </span>
            </div>

            <div
              className={`mt-1 text-sm ${isDark ? "text-white/70" : "text-[#564a76]"
                }`}
            >
              IP: {device.ip}
            </div>

            <div
              className={`text-sm ${isDark ? "text-white/70" : "text-[#564a76]"
                }`}
            >
              Battery: {batteryText}
            </div>
          </div>

          <div className="ml-4 flex shrink-0 flex-col items-end gap-2">
            <button
              onClick={handleOpenConnect}
              className={`w-28 cursor-pointer rounded-xl px-4 py-2 text-center text-sm font-semibold transition ${isDark
                ? "bg-[#fd749b] text-white hover:bg-[#f05b86]"
                : "bg-[#7c4dff] text-white hover:bg-[#693be6]"
                }`}
            >
              Connect
            </button>

            {onDelete && (
              <button
                onClick={() => onDelete(device)}
                className={`w-28 cursor-pointer rounded-xl px-4 py-1 text-center text-xs transition ${isDark
                  ? "bg-rose-500/15 text-rose-200 hover:bg-rose-500/25"
                  : "bg-rose-500/10 text-rose-700 hover:bg-rose-500/20"
                  }`}
              >
                Delete
              </button>
            )}
          </div>
        </div>
      </div>

      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
          onClick={() => setModalOpen(false)}
        >
          <div
            className={`w-full max-w-md rounded-2xl border p-6 shadow-2xl ${isDark
                ? "border-white/10 bg-[#1A0F28] text-white"
                : "border-[#e4d8ff] bg-white text-[#1f1640]"
              }`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4">
              <h2 className="text-lg font-semibold">
                Connect this robot?
              </h2>

              <p
                className={`mt-2 text-sm leading-6 ${isDark ? "text-white/70" : "text-[#5f5578]"
                  }`}
              >
                Choose how you want to connect to{" "}
                <span className="font-semibold">{device.name}</span>.
              </p>

              <div
                className={`mt-3 rounded-xl px-3 py-2 text-xs ${isDark
                    ? "bg-white/5 text-white/60"
                    : "bg-[#f6f2ff] text-[#6f648d]"
                  }`}
              >
                IP: {device.ip} · Status: {info.status}
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={handleJustConnect}
                disabled={loadingAction !== null}
                className={`rounded-xl px-4 py-2 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${isDark
                    ? "bg-white/5 text-white/80 hover:bg-white/10"
                    : "bg-[#f3efff] text-[#5f5380] hover:bg-[#ece5ff]"
                  }`}
              >
                {loadingAction === "connect" ? "Connecting..." : "Just connect"}
              </button>

              <button
                onClick={handleRememberConnect}
                disabled={loadingAction !== null}
                className={`rounded-xl px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${isDark
                    ? "bg-gradient-to-r from-sky-500 to-pink-500 text-white hover:opacity-90"
                    : "bg-gradient-to-r from-[#7c4dff] to-[#fd749b] text-white hover:opacity-90"
                  }`}
              >
                {loadingAction === "remember"
                  ? "Saving..."
                  : "Remember & connect"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}