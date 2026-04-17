"use client";

import React, { useMemo, useState, useEffect } from "react";
import ConnectionCard from "@/components/ConnectionCard";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { setSelectedRobotAddr } from "@/app/lib/selectedRobot";

export type Device = {
  id: number;
  name: string;
  ip: string;
  battery: number;
  url?: string;
  status: "online" | "offline" | "unknown";
  source?: "manual" | "cloudflare";
};
import { RobotAPI } from "./../lib/robotApi";

const BACKEND_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

// Base cho các API điều khiển robot (Django app "control")
const CONTROL_BASE = `${BACKEND_BASE}`;

const robotId = "robot-a";
const DEVICES_COOKIE_KEY = "dogzilla_devices";

// ========================
// Helpers cookie
// ========================
function saveDevicesToCookie(devices: Device[]) {
  if (typeof document === "undefined") return;
  try {
    // chỉ lưu device do user tự nhập (manual)
    const manualDevices = devices.filter((d) => d.source !== "cloudflare");
    const raw = JSON.stringify(manualDevices);
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

    const parsed = JSON.parse(value);
    return parsed as Device[];
  } catch (err) {
    console.error("Cannot parse devices cookie:", err);
    return null;
  }
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

  useEffect(() => {
    setThemeMounted(true);
  }, []);
  const isDark = themeMounted && resolvedTheme === "dark";

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

  // 1) Load manual devices từ cookie
  useEffect(() => {
    const stored = loadDevicesFromCookie();
    if (stored && stored.length > 0) {
      setDevices(stored);
    }
  }, []);

  // 2) Hỏi backend xem robot_url mới nhất là gì (Cloudflare)
  useEffect(() => {
    if (typeof window === "undefined") return;

    async function fetchProfile() {
      try {
        // lấy token nếu có (nếu chưa làm login thì token có thể null, vẫn chạy bình thường)
        const token = localStorage.getItem("access_token");
        const headers: HeadersInit = {};
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const res = await fetch(`${BACKEND_BASE}/api/auth/me/`, {
          headers,
        });

        console.log("[me] status =", res.status);

        const json = await res.json().catch(() => null);
        console.log("[me] json =", json);

        if (!res.ok || !json) {
          // Nếu token sai / hết hạn -> xoá token luôn
          if (res.status === 401 && json?.code === "token_not_valid") {
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");
          }
          console.warn("[me] backend returned error, skip cloudflare card");
          return;
        }

        const robotUrl = (json.robot_url as string | null) ?? null;
        const robotDeviceId =
          (json.robot_device_id as string | null) ?? "rpi5-dogzilla";

        if (!robotUrl) {
          console.log("[me] No robot_url for this user -> no Cloudflare card");
          return;
        }

        // lưu vào localStorage để chỗ khác dùng nếu cần
        localStorage.setItem("robot_url", robotUrl);
        localStorage.setItem("robot_device_id", robotDeviceId);

        // cập nhật / tạo card Cloudflare trong danh sách devices
        setDevices((prev) => {
          const cfId = 0;
          const exists = prev.find((d) => d.id === cfId);

          const cfDevice: Device = {
            id: cfId,
            name: "My Robot (Cloudflare)",
            ip: robotUrl, // full URL: https://xxx.trycloudflare.com
            battery: exists?.battery ?? 100,
            status: exists?.status ?? "unknown",
            source: "cloudflare",
          };

          if (exists) {
            // update card cũ
            return prev.map((d) => (d.id === cfId ? cfDevice : d));
          }
          // luôn đưa Cloudflare card lên đầu
          return [cfDevice, ...prev];
        });
      } catch (err) {
        console.error("fetchProfile error:", err);
      }
    }

    fetchProfile();
  }, []);

  // 3) Mỗi khi devices thay đổi -> lưu lại cookie (chỉ manual)
  useEffect(() => {
    saveDevicesToCookie(devices);
  }, [devices]);

const handleConnectDevice = async (device: Device) => {
  if (loading) return;

  setErrorMsg(null);
  setLoading(true);

  let dogzillaAddr = device.ip.trim();

  // Nếu không phải URL đầy đủ thì coi là IP nội bộ -> thêm http + port 9000
  if (
    !dogzillaAddr.startsWith("http://") &&
    !dogzillaAddr.startsWith("https://")
  ) {
    dogzillaAddr = `http://${dogzillaAddr}:9000`;
  }

  const isCloudflare =
    device.source === "cloudflare" ||
    dogzillaAddr.includes("trycloudflare.com") ||
    dogzillaAddr.startsWith("https://");

  try {
    let connected = false;
    let newStatus: Device["status"] = "offline";

    if (isCloudflare) {
      // 🔵 Cloudflare: check trực tiếp từ browser
      const healthUrl = dogzillaAddr.replace(/\/+$/, "") + "/status"; 
      // nếu robot của bạn dùng /health thì đổi lại chỗ này

      const resp = await fetch(healthUrl, { cache: "no-store" });
      if (!resp.ok) {
        throw new Error(`Cloudflare status HTTP ${resp.status}`);
      }

      // có thể đọc thêm data nếu cần
      // const data = await resp.json().catch(() => ({} as any));

      connected = true;
      newStatus = "online";
    } else {
      // 🟢 LAN: để Django kiểm tra & lưu addr
      const res = await RobotAPI.connect(dogzillaAddr);
      connected = Boolean(res.connected);
      newStatus = connected ? "online" : "offline";

      if (!connected) {
        throw new Error(res.error || "Không kết nối được tới robot.");
      }
    }

    // cập nhật trạng thái card
    setDevices((prev) =>
      prev.map((d) =>
        d.id === device.id ? { ...d, status: newStatus } : d
      )
    );

    if (!connected) {
      // đề phòng nhánh nào đó set connected = false
      setErrorMsg("Không kết nối được tới robot.");
      return;
    }

    // thành công -> lưu robot hiện tại rồi sang trang điều khiển
    setSelectedRobotAddr(dogzillaAddr);
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
      name: `Robot ${String.fromCharCode(64 + devices.length + 1)}`, // Robot A/B/C...
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
      {/* Thanh nhắc xoay ngang trên điện thoại khi đang cầm dọc */}
      {isPortrait && (
        <div className="mb-3 rounded-xl bg-amber-500/10 border border-amber-400/40 px-3 py-2 text-xs md:text-sm text-amber-200">
          For best control experience, please rotate your phone to{" "}
          <span className="font-semibold">landscape</span>.
        </div>
      )}

      <h1 className={`gradient-title mb-6 ${isPortrait ? "" : "hidden"}`}>Connection Manager</h1>

      <div className="mb-6 flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          placeholder="Enter device IP (vd: 192.168.2.100)"
          value={addr}
          onChange={(e) => setAddr(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && canAdd && handleAdd()}
          className={`flex-1 min-h-[44px] rounded-xl px-4 py-2 text-sm outline-none focus:ring-2 ${
            isDark
              ? "border border-white/10 bg-[#160a28] text-white placeholder:text-white/35 focus:ring-cyan-400/30"
              : "border border-[#d8cbff] bg-[#fffdfd] text-[#1f1640] placeholder:text-[#8d84a8] focus:ring-pink-400/30"
          }`}
        />
        <button
          onClick={handleAdd}
          disabled={!canAdd || loading}
          className={`min-h-[44px] rounded-xl px-4 py-2 text-sm font-medium cursor-pointer transition ${
            isDark
              ? "bg-[#7c4dff] text-white hover:bg-[#6b3dff]"
              : "bg-[#7c4dff] text-white hover:bg-[#6b3dff]"
          } ${!canAdd || loading ? "cursor-not-allowed opacity-50" : ""}`}
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
