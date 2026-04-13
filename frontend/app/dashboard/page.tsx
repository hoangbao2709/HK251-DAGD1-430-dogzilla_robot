"use client";

import React, { useMemo, useState, useEffect } from "react";
import ConnectionCard from "@/components/ConnectionCard";
import { useRouter } from "next/navigation";
import { saveRobotSession } from "./../lib/robotSession";
import { RobotAPI } from "./../lib/robotApi";

export type Device = {
  id: number;
  name: string;
  ip: string;
  battery: number;
  url?: string;
  status: "online" | "offline" | "unknown";
  source?: "manual" | "cloudflare";
};

const BACKEND_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const robotId = "robot-a";
const DEVICES_COOKIE_KEY = "dogzilla_devices";

// ========================
// Helpers cookie cho danh sách device
// ========================
function saveDevicesToCookie(devices: Device[]) {
  if (typeof document === "undefined") return;

  try {
    const manualDevices = devices.filter((d) => d.source !== "cloudflare");
    const raw = JSON.stringify(manualDevices);

    document.cookie = `${DEVICES_COOKIE_KEY}=${encodeURIComponent(
      raw
    )}; path=/; max-age=31536000; samesite=lax`;
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

// Chuẩn hóa addr robot
function normalizeRobotAddress(raw: string) {
  const value = raw.trim();

  if (!value) return "";

  // đã có http/https
  if (value.startsWith("http://") || value.startsWith("https://")) {
    return value.replace(/\/+$/, "");
  }

  // có ip:port
  if (value.includes(":")) {
    return `http://${value.replace(/\/+$/, "")}`;
  }

  // chỉ là ip
  return `http://${value}:9000`;
}

export default function DashboardPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [addr, setAddr] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [isPortrait, setIsPortrait] = useState(false);

  const router = useRouter();
  const canAdd = useMemo(() => addr.trim().length > 0, [addr]);

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

  // 1) load manual devices từ cookie
  useEffect(() => {
    const stored = loadDevicesFromCookie();
    if (stored && stored.length > 0) {
      setDevices(stored);
    }
  }, []);

  // 2) hỏi backend lấy robot_url mới nhất từ account
  useEffect(() => {
    if (typeof window === "undefined") return;

    async function fetchProfile() {
      try {
        const token = localStorage.getItem("access_token");
        const headers: HeadersInit = {};

        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const res = await fetch(`${BACKEND_BASE}/api/auth/me/`, { headers });
        const json = await res.json().catch(() => null);

        if (!res.ok || !json) {
          if (res.status === 401 && json?.code === "token_not_valid") {
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");
          }
          return;
        }

        const robotUrl = (json.robot_url as string | null) ?? null;
        const robotDeviceId =
          (json.robot_device_id as string | null) ?? "rpi5-dogzilla";

        if (!robotUrl) return;

        localStorage.setItem("robot_url", robotUrl);
        localStorage.setItem("robot_device_id", robotDeviceId);

        setDevices((prev) => {
          const cfId = 0;
          const exists = prev.find((d) => d.id === cfId);

          const cfDevice: Device = {
            id: cfId,
            name: "My Robot (Cloudflare)",
            ip: robotUrl,
            battery: exists?.battery ?? 100,
            status: exists?.status ?? "unknown",
            source: "cloudflare",
          };

          if (exists) {
            return prev.map((d) => (d.id === cfId ? cfDevice : d));
          }

          return [cfDevice, ...prev];
        });
      } catch (err) {
        console.error("fetchProfile error:", err);
      }
    }

    fetchProfile();
  }, []);

  // 3) mỗi khi devices đổi thì lưu lại cookie
  useEffect(() => {
    saveDevicesToCookie(devices);
  }, [devices]);

  const handleConnectDevice = async (device: Device) => {
    if (loading) return;

    setErrorMsg(null);
    setLoading(true);

    const dogzillaAddr = normalizeRobotAddress(device.ip);

    const isCloudflare =
      device.source === "cloudflare" ||
      dogzillaAddr.includes("trycloudflare.com") ||
      dogzillaAddr.startsWith("https://");

    try {
      let connected = false;
      let newStatus: Device["status"] = "offline";

      if (isCloudflare) {
        // kiểm tra trực tiếp
        const statusUrl = `${dogzillaAddr.replace(/\/+$/, "")}/status`;
        const resp = await fetch(statusUrl, { cache: "no-store" });

        if (!resp.ok) {
          throw new Error(`Cloudflare status HTTP ${resp.status}`);
        }

        connected = true;
        newStatus = "online";
      } else {
        // LAN -> nhờ Django connect & lưu addr
        const res = await RobotAPI.connect(dogzillaAddr);
        connected = !!res.connected;
        newStatus = connected ? "online" : "offline";

        if (!connected) {
          throw new Error(res.error || "Không kết nối được tới robot.");
        }
      }

      setDevices((prev) =>
        prev.map((d) =>
          d.id === device.id ? { ...d, status: newStatus } : d
        )
      );

      if (!connected) {
        setErrorMsg("Không kết nối được tới robot.");
        return;
      }

      // QUAN TRỌNG: lưu session robot vào cookie
      saveRobotSession(dogzillaAddr, robotId);

      // sau đó sang trang control, không cần ?ip=...
      router.push("/control");
    } catch (e: any) {
      console.error("Connect error:", e);

      setDevices((prev) =>
        prev.map((d) =>
          d.id === device.id ? { ...d, status: "offline" } : d
        )
      );

      setErrorMsg(e?.message || "Không kết nối được tới backend/robot");
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
      source: "manual",
    };

    setDevices((prev) => [nextDevice, ...prev]);
    setAddr("");
  };

  return (
    <section className="h-full w-full p-4 md:p-6">
      {isPortrait && (
        <div className="mb-3 rounded-xl bg-amber-500/10 border border-amber-400/40 px-3 py-2 text-xs md:text-sm text-amber-200">
          For best control experience, please rotate your phone to{" "}
          <span className="font-semibold">landscape</span>.
        </div>
      )}

      <h1 className={`gradient-title mb-6 ${isPortrait ? "" : "hidden"}`}>
        Connection Manager
      </h1>

      <div className="mb-6 flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          placeholder="Enter device IP (vd: 192.168.2.100)"
          value={addr}
          onChange={(e) => setAddr(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && canAdd && handleAdd()}
          className="flex-1 rounded-xl bg-white/10 px-4 py-2 text-sm placeholder:text-white/60 focus:outline-none focus:ring-2 focus:ring-pink-400/60 min-h-[44px]"
        />
        <button
          onClick={handleAdd}
          disabled={!canAdd || loading}
          className={`gradient-button1 px-4 py-2 rounded-xl cursor-pointer text-sm font-medium min-h-[44px] ${
            !canAdd || loading ? "opacity-50 cursor-not-allowed" : ""
          }`}
        >
          Add
        </button>
      </div>

      {errorMsg && (
        <div className="mb-4 text-xs text-rose-400">Error: {errorMsg}</div>
      )}

      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
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