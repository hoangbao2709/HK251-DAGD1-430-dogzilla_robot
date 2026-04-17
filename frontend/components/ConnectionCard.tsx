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
  source?: "manual" | "cloudflare";
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
  const [showModal, setShowModal] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [linking, setLinking] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = mounted && resolvedTheme === "dark";

  const isCloudflare =
    device.source === "cloudflare" ||
    device.ip.startsWith("http://") ||
    device.ip.startsWith("https://");

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

    async function fetchStatus() {
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
      }
    }

    fetchStatus();
    const timer = setInterval(fetchStatus, 2000);

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
    info.battery != null ? `${info.battery}%` : info.status === "offline" ? "-" : "…";

  function handleConnectClick() {
    setLinkError(null);
    const email = localStorage.getItem("user_email");

    if (!email || isCloudflare) {
      onConnect?.(device as any);
      return;
    }

    setShowModal(true);
  }

  function handleJustConnect() {
    setShowModal(false);
    setLinkError(null);
    setLinking(false);
    onConnect?.(device as any);
  }

  function closeModal() {
    setShowModal(false);
    setLinkError(null);
    setLinking(false);
  }

  async function rememberAndConnect() {
    setLinkError(null);
    setLinking(true);

    try {
      const email = localStorage.getItem("user_email");
      if (!email) {
        handleJustConnect();
        return;
      }

      const base = buildRobotBase();
      const url = `${base}/link-account`;
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          device_id: "rpi5-dogzilla",
        }),
      });

      const text = await res.text();
      if (!res.ok) {
        throw new Error(`Robot returned ${res.status}: ${text || "no body"}`);
      }

      setShowModal(false);
      onConnect?.(device as any);
    } catch (err) {
      console.error("rememberAndConnect error:", err);
      setLinkError("Failed to link robot");
    } finally {
      setLinking(false);
    }
  }

  return (
    <>
      <div className={`flex items-center justify-between rounded-2xl p-4 ${cardClass}`}>
        <div>
          <div className={`flex items-center gap-2 font-semibold ${isDark ? "text-white" : "text-[#1f1640]"}`}>
            <span>{device.name}</span>
            <span className={`rounded-full px-2 py-0.5 text-xs ${statusClass}`}>
              {info.status}
            </span>
            {isCloudflare && (
              <span
                className={`rounded-full border px-2 py-0.5 text-xs ${
                  isDark
                    ? "border-cyan-400/30 bg-cyan-500/15 text-cyan-200"
                    : "border-cyan-300/50 bg-cyan-500/10 text-cyan-700"
                }`}
              >
                Cloudflare
              </span>
            )}
          </div>

          <div className={`text-sm ${isDark ? "text-white/70" : "text-[#564a76]"}`}>
            {isCloudflare ? "URL" : "IP"}: {device.ip}
          </div>
          <div className={`text-sm ${isDark ? "text-white/70" : "text-[#564a76]"}`}>
            Battery: {batteryText}
          </div>
        </div>

        <div className="flex flex-col items-end gap-2">
          <button
            onClick={handleConnectClick}
            className={`w-24 rounded-xl px-4 py-2 text-center text-sm transition ${
              isDark
                ? "bg-[#fd749b] text-white hover:bg-[#f05b86]"
                : "bg-[#7c4dff] text-white hover:bg-[#693be6]"
            }`}
          >
            Connect
          </button>

          {onDelete && (
            <button
              onClick={() => onDelete(device as any)}
              className={`w-24 rounded-xl px-4 py-1 text-center text-xs transition ${
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

      {showModal && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/60"
          onClick={closeModal}
        >
          <div
            className={`w-full max-w-md rounded-2xl border p-6 ${
              isDark
                ? "border-white/10 bg-[#160a28] text-white"
                : "border-[#dacfff] bg-[#fffdfd] text-[#1f1640]"
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold">
              Link this robot to your account?
            </h2>
            <p className={`mb-4 text-sm ${isDark ? "text-white/70" : "text-[#564a76]"}`}>
              If you agree, this robot ({device.name}) will remember your email.
              Every time it boots and creates a new Cloudflare URL, it will
              automatically update that URL to your account.
            </p>

            {linkError && (
              <p className={`mb-2 text-xs ${isDark ? "text-rose-300" : "text-rose-600"}`}>
                {linkError}
              </p>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={handleJustConnect}
                className={`rounded-xl px-3 py-1.5 text-xs transition ${
                  isDark
                    ? "bg-white/5 text-white hover:bg-white/10"
                    : "bg-[#f3efff] text-[#1f1640] hover:bg-[#ece4ff]"
                }`}
              >
                Just connect
              </button>
              <button
                onClick={rememberAndConnect}
                disabled={linking}
                className={`rounded-xl px-4 py-2 text-sm transition disabled:opacity-60 ${
                  isDark
                    ? "bg-[#00b8ff] text-white hover:bg-[#08a7e2]"
                    : "bg-[#7c4dff] text-white hover:bg-[#693be6]"
                }`}
              >
                {linking ? "Linking..." : "Remember & connect"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
