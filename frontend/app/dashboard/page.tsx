"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import ConnectionCard from "@/components/ConnectionCard";
import { setSelectedRobotAddr } from "@/app/lib/selectedRobot";
import { RobotAPI } from "./../lib/robotApi";

export type Device = {
  id: number;
  name: string;
  ip: string;
  battery: number;
  url?: string;
  status: "online" | "offline" | "unknown";
};

const DEVICES_COOKIE_KEY = "dogzilla_devices";

function saveDevicesToCookie(devices: Device[]) {
  if (typeof document === "undefined") return;

  try {
    const raw = JSON.stringify(devices);
    document.cookie = `${DEVICES_COOKIE_KEY}=${encodeURIComponent(
      raw
    )}; path=/; max-age=31536000`;
  } catch (err) {
    console.error("Cannot save devices to cookie:", err);
  }
}

function loadDevicesFromCookie(): Device[] | null {
  if (typeof document === "undefined") return null;

  try {
    const cookies = document.cookie.split(";").map((c) => c.trim());
    const found = cookies.find((c) => c.startsWith(`${DEVICES_COOKIE_KEY}=`));
    if (!found) return null;

    const value = decodeURIComponent(found.split("=")[1] || "");
    if (!value) return null;

    return JSON.parse(value) as Device[];
  } catch (err) {
    console.error("Cannot parse devices cookie:", err);
    return null;
  }
}

function normalizeRobotAddr(device: Device) {
  const raw = device.ip.trim();
  if (!raw) return "";

  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    return raw.replace(/\/+$/, "");
  }

  return `http://${raw}:9000`;
}

export default function DashboardPage() {
  const { resolvedTheme } = useTheme();
  const [themeMounted, setThemeMounted] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [addr, setAddr] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [isPortrait, setIsPortrait] = useState(false);

  const router = useRouter();
  const canAdd = useMemo(() => addr.trim().length > 0, [addr]);
  const isDark = themeMounted && resolvedTheme === "dark";

  useEffect(() => {
    setThemeMounted(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const updateOrientation = () => {
      const { innerWidth, innerHeight } = window;
      setIsPortrait(innerHeight > innerWidth);
    };

    updateOrientation();
    window.addEventListener("resize", updateOrientation);
    window.addEventListener("orientationchange", updateOrientation);

    return () => {
      window.removeEventListener("resize", updateOrientation);
      window.removeEventListener("orientationchange", updateOrientation);
    };
  }, []);

  useEffect(() => {
    const stored = loadDevicesFromCookie();
    if (stored && stored.length > 0) {
      setDevices(stored);
    }
  }, []);

  useEffect(() => {
    saveDevicesToCookie(devices);
  }, [devices]);

  const handleConnectDevice = async (device: Device) => {
    if (loading) return;

    setErrorMsg(null);
    setLoading(true);

    const dogzillaAddr = normalizeRobotAddr(device);

    try {
      const res = await RobotAPI.connect(dogzillaAddr);
      const connected = Boolean(res.connected);
      const newStatus: Device["status"] = connected ? "online" : "offline";

      if (!connected) {
        throw new Error(res.error || "Khong ket noi duoc toi robot.");
      }

      setDevices((prev) =>
        prev.map((d) =>
          d.id === device.id ? { ...d, status: newStatus } : d
        )
      );

      setSelectedRobotAddr(dogzillaAddr);
      router.push("/control");
    } catch (e: any) {
      console.error("Connect error:", e);

      setDevices((prev) =>
        prev.map((d) =>
          d.id === device.id ? { ...d, status: "offline" } : d
        )
      );
      setErrorMsg(e?.message || "Khong ket noi duoc toi backend/robot");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteDevice = (device: Device) => {
    setDevices((prev) => prev.filter((d) => d.id !== device.id));
  };

  const handleAdd = () => {
    const ip = addr.trim();
    if (!ip || loading) return;

    setErrorMsg(null);

    if (devices.some((d) => d.ip === ip)) {
      setAddr("");
      return;
    }

    const nextId = devices.length
      ? Math.max(...devices.map((d) => d.id)) + 1
      : 1;

    const nextDevice: Device = {
      id: nextId,
      name: `Robot ${String.fromCharCode(64 + devices.length + 1)}`,
      ip,
      battery: 100,
      status: "unknown",
    };

    setDevices((prev) => [nextDevice, ...prev]);
    setAddr("");
  };

  return (
    <section className="h-full w-full p-4 md:p-6">
      {isPortrait && (
        <div className="mb-3 rounded-xl border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200 md:text-sm">
          For best control experience, please rotate your phone to{" "}
          <span className="font-semibold">landscape</span>.
        </div>
      )}

      <h1 className={`gradient-title mb-6 ${isPortrait ? "" : "hidden"}`}>
        Connection Manager
      </h1>

      <div className="mb-6 flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          placeholder="Enter device IP (vd: 192.168.2.100)"
          value={addr}
          onChange={(e) => setAddr(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && canAdd && handleAdd()}
          className={`min-h-[44px] flex-1 rounded-xl px-4 py-2 text-sm outline-none focus:ring-2 ${
            isDark
              ? "border border-white/10 bg-[#160a28] text-white placeholder:text-white/35 focus:ring-cyan-400/30"
              : "border border-[#d8cbff] bg-[#fffdfd] text-[#1f1640] placeholder:text-[#8d84a8] focus:ring-pink-400/30"
          }`}
        />
        <button
          onClick={handleAdd}
          disabled={!canAdd || loading}
          className={`min-h-[44px] rounded-xl px-4 py-2 text-sm font-medium transition ${
            isDark
              ? "bg-[#7c4dff] text-white hover:bg-[#6b3dff]"
              : "bg-[#7c4dff] text-white hover:bg-[#6b3dff]"
          } ${!canAdd || loading ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
        >
          Add
        </button>
      </div>

      {errorMsg && (
        <div
          className={`mb-4 rounded-xl border px-3 py-2 text-xs ${
            isDark
              ? "border-rose-500/30 bg-rose-500/10 text-rose-200"
              : "border-rose-300/40 bg-rose-500/10 text-rose-600"
          }`}
        >
          Error: {errorMsg}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {devices.map((dev) => (
          <ConnectionCard
            key={dev.id}
            device={dev}
            onConnect={handleConnectDevice}
            onDelete={handleDeleteDevice}
          />
        ))}
      </div>
    </section>
  );
}
