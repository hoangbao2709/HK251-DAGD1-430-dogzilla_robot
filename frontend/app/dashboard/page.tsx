"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";

import ConnectionCard, { Device } from "@/components/ConnectionCard";
import { getStoredSession, onAuthChanged } from "@/app/lib/auth";
import { setSelectedRobotAddr } from "@/app/lib/selectedRobot";
import { RobotAPI } from "@/app/lib/robotApi";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
const SESSION_DEVICES_KEY = "dogzilla_session_devices";

function normalizeRobotAddr(device: Device) {
  const raw = device.ip.trim();

  if (!raw) return "";

  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    return raw.replace(/\/+$/, "");
  }

  if (raw.includes(":")) {
    return `http://${raw.replace(/\/+$/, "")}`;
  }

  return `http://${raw}:9000`;
}

function mergeDevices(currentDevices: Device[], serverDevices: Device[]) {
  const map = new Map<string, Device>();

  for (const item of currentDevices) {
    map.set(item.ip, item);
  }

  for (const item of serverDevices) {
    map.set(item.ip, item);
  }

  return Array.from(map.values());
}

function loadSessionDevices(): Device[] {
  if (typeof window === "undefined") return [];

  try {
    const raw = window.sessionStorage.getItem(SESSION_DEVICES_KEY);
    const parsed = raw ? JSON.parse(raw) : [];

    if (!Array.isArray(parsed)) return [];

    return parsed
      .filter((item) => item && typeof item.ip === "string" && item.ip.trim())
      .map((item, index) => ({
        id: Number(item.id ?? Date.now() + index),
        name: String(item.name || `Robot ${index + 1}`),
        ip: String(item.ip).trim(),
        url: String(item.url || item.ip || ""),
        battery: Number(item.battery ?? 100),
        status: item.status === "online" || item.status === "offline" ? item.status : "unknown",
        source: "session",
      }));
  } catch {
    return [];
  }
}

function saveSessionDevices(devices: Device[]) {
  if (typeof window === "undefined") return;

  const sessionDevices = devices
    .filter((device) => device.source !== "database")
    .map((device) => ({
      id: device.id,
      name: device.name,
      ip: device.ip,
      url: device.url || "",
      battery: device.battery ?? 100,
      status: device.status || "unknown",
      source: "session",
    }));

  window.sessionStorage.setItem(SESSION_DEVICES_KEY, JSON.stringify(sessionDevices));
}

export default function DashboardPage() {
  const router = useRouter();
  const { resolvedTheme } = useTheme();

  const [themeMounted, setThemeMounted] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [addr, setAddr] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [isPortrait, setIsPortrait] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  const canAdd = useMemo(() => addr.trim().length > 0, [addr]);
  const isDark = themeMounted && resolvedTheme === "dark";

  useEffect(() => {
    setThemeMounted(true);
  }, []);

  useEffect(() => {
    const updateLoginState = () => {
      const session = getStoredSession();
      setIsLoggedIn(Boolean(session?.access));
    };

    updateLoginState();

    const unsubscribe = onAuthChanged(updateLoginState);
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const updateOrientation = () => {
      setIsPortrait(window.innerHeight > window.innerWidth);
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
    async function loadRememberedRobots() {
      const session = getStoredSession();
      const sessionDevices = loadSessionDevices();

      if (!session?.access) {
        setDevices(sessionDevices);
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/api/auth/robots/`, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${session.access}`,
          },
          cache: "no-store",
        });

        if (!res.ok) {
          throw new Error(`Cannot load remembered robots: ${res.status}`);
        }

        const data = await res.json();

        const serverDevices: Device[] = Array.isArray(data)
          ? data.map((item: any, index: number) => ({
              id: Number(item.id ?? Date.now() + index),
              name: item.name || `Robot ${index + 1}`,
              ip: item.ip || item.url || "",
              url: item.url || item.ip || "",
              battery: Number(item.battery ?? 100),
              status: item.status || "unknown",
              source: "database",
            }))
          : [];

        setDevices((prev) => mergeDevices(mergeDevices(sessionDevices, prev), serverDevices));
      } catch (err) {
        console.warn("Load remembered robots failed:", err);
        setDevices((prev) => mergeDevices(sessionDevices, prev));
      }
    }

    loadRememberedRobots();
  }, [isLoggedIn]);

  const handleConnectDevice = async (device: Device, remember = false) => {
    if (loading) return;

    setErrorMsg(null);
    setLoading(true);

    const robotAddr = normalizeRobotAddr(device);

    try {
      const res = await RobotAPI.connect(robotAddr);
      const connected = Boolean(res.connected);

      if (!connected) {
        throw new Error(res.error || "Không kết nối được tới robot.");
      }

      setDevices((prev) => {
        const next: Device[] = prev.map((d) =>
          d.ip === device.ip
            ? {
                ...d,
                id: device.id,
                status: "online" as const,
                source: remember ? "database" : d.source ?? "session",
              }
            : d
        );
        saveSessionDevices(next);
        return next;
      });

      setSelectedRobotAddr(robotAddr, remember);
      router.push("/control");
    } catch (e: any) {
      console.error("Connect error:", e);

      setDevices((prev) => {
        const next: Device[] = prev.map((d) =>
          d.ip === device.ip
            ? {
                ...d,
                status: "offline" as const,
              }
            : d
        );
        saveSessionDevices(next);
        return next;
      });

      setErrorMsg(e?.message || "Không kết nối được tới backend/robot.");
    } finally {
      setLoading(false);
    }
  };

  const handleRememberAndConnect = async (device: Device) => {
    const session = getStoredSession();

    if (!session?.access) {
      await handleConnectDevice(device, false);
      return;
    }

    const robotAddr = normalizeRobotAddr(device);

    try {
      setErrorMsg(null);

      const res = await fetch(`${API_BASE}/api/auth/robots/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access}`,
        },
        body: JSON.stringify({
          name: device.name,
          ip: device.ip,
          url: robotAddr,
          status: device.status,
          battery: device.battery ?? 100,
        }),
      });

      const data = await res.json().catch(() => ({}));

      console.log("SAVE ROBOT STATUS =", res.status);
      console.log("SAVE ROBOT RESPONSE =", data);

      if (!res.ok) {
        throw new Error(
          data?.error ||
            data?.detail ||
            `Không lưu được robot vào database. Status: ${res.status}`
        );
      }

      const savedDevice: Device = {
        ...device,
        id: Number(data.id ?? device.id),
        name: data.name ?? device.name,
        ip: data.ip ?? device.ip,
        url: data.url ?? robotAddr,
        status: data.status ?? device.status,
        battery: Number(data.battery ?? device.battery ?? 100),
        source: "database",
      };

      setDevices((prev) =>
        prev.map((d) => (d.ip === device.ip ? savedDevice : d))
      );

      await handleConnectDevice(savedDevice, true);
    } catch (err: any) {
      console.error("Remember robot error:", err);
      setErrorMsg(err?.message || "Không lưu được robot vào database.");
    }
  };

  const handleDeleteDevice = async (device: Device) => {
    const session = getStoredSession();

    setDevices((prev) => {
      const next = prev.filter((d) => d.ip !== device.ip);
      saveSessionDevices(next);
      return next;
    });

    if (!session?.access) return;
    if (device.source !== "database") return;

    try {
      await fetch(`${API_BASE}/api/auth/robots/${device.id}/`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${session.access}`,
        },
      });
    } catch (err) {
      console.warn("Delete remembered robot failed:", err);
    }
  };

  const handleAdd = () => {
    const ip = addr.trim();

    if (!ip || loading) return;

    setErrorMsg(null);

    if (devices.some((d) => d.ip === ip)) {
      setAddr("");
      return;
    }

    const nextId = Date.now();

    const nextDevice: Device = {
      id: nextId,
      name: `Robot ${String.fromCharCode(65 + devices.length)}`,
      ip,
      battery: 100,
      status: "unknown",
      source: "session",
    };

    setDevices((prev) => {
      const next = [nextDevice, ...prev];
      saveSessionDevices(next);
      return next;
    });
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
          placeholder="Enter device IP, ví dụ: 100.95.128.237"
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
          } ${
            !canAdd || loading
              ? "cursor-not-allowed opacity-50"
              : "cursor-pointer"
          }`}
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
            key={`${dev.source}-${dev.id}-${dev.ip}`}
            device={dev}
            onConnect={handleConnectDevice}
            onRememberAndConnect={handleRememberAndConnect}
            onDelete={handleDeleteDevice}
          />
        ))}
      </div>
    </section>
  );
}
