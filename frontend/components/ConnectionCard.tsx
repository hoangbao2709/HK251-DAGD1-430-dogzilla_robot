"use client";

import { useEffect, useState } from "react";

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
  const [info, setInfo] = useState<CardStatus>({
    status: "unknown",
    battery: null,
  });

  const [showModal, setShowModal] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [linking, setLinking] = useState(false);

  const isCloudflare =
    device.source === "cloudflare" ||
    device.ip.startsWith("http://") ||
    device.ip.startsWith("https://");

  const cardClass = isCloudflare
    ? "bg-gradient-to-r from-sky-500/20 via-fuchsia-500/15 to-pink-500/20 border border-sky-400/40"
    : "bg-white/10 border border-white/10";

  // Helper: build base URL tới robot
function buildRobotBase() {
  let base = device.ip.trim();

  // Nếu đã có http/https -> giữ nguyên, chỉ bỏ dấu / ở cuối
  if (base.startsWith("http://") || base.startsWith("https://")) {
    return base.replace(/\/+$/, "");
  }

  // Nếu user đã nhập ip:port thì không thêm :9000 nữa
  if (base.includes(":")) {
    return `http://${base.replace(/\/+$/, "")}`;
  }

  // Mặc định: chỉ có IP -> tự thêm port 9000
  return `http://${base}:9000`;
}


  // Poll /status của từng robot
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [device.ip]);

  const statusClass =
    info.status === "online"
      ? "bg-green-500/20 text-green-300"
      : info.status === "offline"
      ? "bg-rose-500/20 text-rose-300"
      : "bg-yellow-500/20 text-yellow-300";

  const batteryText =
    info.battery != null
      ? `${info.battery}%`
      : info.status === "offline"
      ? "-"
      : "…";

  // ==== NEW: when not logged in -> connect thẳng, không hiện modal ====
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

      // Phòng trường hợp mất email giữa chừng -> fallback: chỉ connect
      if (!email) {
        handleJustConnect();
        return;
      }

      const base = buildRobotBase();
      const url = `${base}/link-account`;
      console.log("POST to robot:", url, { email });

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
      console.log("link-account response:", res.status, text);

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
      <div
        className={`flex justify-between items-center rounded-2xl p-4 ${cardClass}`}
      >
        {/* Left info */}
        <div>
          <div className="font-semibold flex items-center gap-2">
            <span>{device.name}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${statusClass}`}>
              {info.status}
            </span>
            {isCloudflare && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-sky-500/20 text-sky-200 border border-sky-400/40">
                Cloudflare
              </span>
            )}
          </div>

          <div className="text-sm text-white/70">
            {isCloudflare ? "URL" : "IP"}: {device.ip}
          </div>
          <div className="text-sm text-white/70">Battery: {batteryText}</div>
        </div>

        {/* Right buttons */}
        <div className="flex flex-col gap-2 items-end">
          <button
            onClick={handleConnectClick}
            className="rounded-xl bg-gradient-to-r from-pink-500 to-purple-500 px-4 py-2 text-sm cursor-pointer w-24 text-center"
          >
            Connect
          </button>

          {onDelete && (
            <button
              onClick={() => onDelete(device as any)}
              className="rounded-xl bg-red-500/20 text-red-300 px-4 py-1 text-xs cursor-pointer w-24 text-center hover:bg-red-500/30"
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/60"
          onClick={closeModal} // click nền ngoài -> tắt
        >
          <div
            className="w-full max-w-md rounded-2xl bg-[#1A0F28] border border-white/10 p-6"
            onClick={(e) => e.stopPropagation()} // chặn click trong modal
          >
            <h2 className="text-lg font-semibold mb-2">
              Link this robot to your account?
            </h2>
            <p className="text-sm text-white/70 mb-4">
              If you agree, this robot ({device.name}) will remember your email.
              Every time it boots and creates a new Cloudflare URL, it will
              automatically update that URL to your account.
            </p>

            {linkError && (
              <p className="text-xs text-rose-300 mb-2">{linkError}</p>
            )}

            <div className="flex justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={handleJustConnect}
                className="px-3 py-1.5 text-xs rounded-xl bg-white/5 hover:bg-white/10"
              >
                Just connect
              </button>
              <button
                onClick={rememberAndConnect}
                disabled={linking}
                className="rounded-xl bg-gradient-to-r from-sky-500 to-pink-500 px-4 py-2 text-sm disabled:opacity-60"
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
