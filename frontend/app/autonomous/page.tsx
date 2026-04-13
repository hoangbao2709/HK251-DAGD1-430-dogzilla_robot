"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  Bot,
  Wifi,
  WifiOff,
  Activity,
  AlertTriangle,
  Mic,
  Send,
  Loader2,
} from "lucide-react";
import { getRobotSession } from "./../lib/robotSession";

type TextCommandResponse = {
  success: boolean;
  input_text?: string;
  error?: string;
  log?: string;
  mapped?: {
    tool?: string;
    arguments?: Record<string, unknown>;
    matched?: string | string[];
    normalized_text?: string;
    intent?: string;
  };
  mcp_result?: unknown;
};

type RobotStatusResponse = {
  id?: string;
  name?: string;
  floor?: string;
  status_text?: string;
  water_level?: number;
  battery?: number;
  fps?: number;
  telemetry?: {
    robot_connected?: boolean;
    battery?: number;
    fps?: number;
    system?: {
      ip?: string;
      time?: string;
      cpu_percent?: number;
      ram?: string;
      disk?: string;
    };
  };
};

function nowTimeLabel() {
  const d = new Date();
  return d.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function StatBlock({
  value,
  label,
}: {
  value: string | number;
  label: string;
}) {
  return (
    <div>
      <div className="text-white font-semibold text-base">{value}</div>
      <div className="text-white/50 text-[11px] tracking-widest uppercase mt-0.5">
        {label}
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-white/60 text-xs font-semibold uppercase tracking-widest mb-3">
      {children}
    </h3>
  );
}

function DarkCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`bg-[#0f0822] rounded-xl p-4 ${className}`}>{children}</div>;
}

export default function AutonomousControlPage() {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

  const [robotId, setRobotId] = useState("robot-a");
  const [robotIp, setRobotIp] = useState("");
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(true);
  const [statusData, setStatusData] = useState<RobotStatusResponse | null>(null);

  const [commandText, setCommandText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(true);
  const [activityLog, setActivityLog] = useState<string[]>([]);
  const [errorLog, setErrorLog] = useState<string[]>([]);
  const [commandResult, setCommandResult] = useState<TextCommandResponse | null>(null);

  const recognitionRef = useRef<any>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wasConnectedRef = useRef(false);

  useEffect(() => {
    const session = getRobotSession();

    if (session.ip) {
      setRobotIp(session.ip);
    } else {
      setErrorLog((prev) => [
        `${nowTimeLabel()} / chưa chọn robot / hãy connect từ dashboard`,
        ...prev,
      ]);
    }

    if (session.robotId) {
      setRobotId(session.robotId);
    }
  }, []);

  const connectUrl = useMemo(
    () => `${API_BASE}/control/api/robots/${robotId}/connect/`,
    [API_BASE, robotId]
  );

  const statusUrl = useMemo(
    () => `${API_BASE}/control/api/robots/${robotId}/status/`,
    [API_BASE, robotId]
  );

  const textCommandUrl = useMemo(
    () => `${API_BASE}/control/api/robots/${robotId}/command/text/`,
    [API_BASE, robotId]
  );

  const appendActivity = useCallback((line: string) => {
    setActivityLog((prev) => [line, ...prev].slice(0, 30));
  }, []);

  const appendError = useCallback((line: string) => {
    setErrorLog((prev) => [line, ...prev].slice(0, 20));
  }, []);

  const fetchStatus = useCallback(async () => {
    const res = await fetch(statusUrl, {
      cache: "no-store",
    });

    const data: RobotStatusResponse = await res.json();

    if (!res.ok) {
      throw new Error("Không lấy được trạng thái robot");
    }

    setStatusData(data);

    const isNowConnected = !!data?.telemetry?.robot_connected;
    setConnected(isNowConnected);

    if (isNowConnected && !wasConnectedRef.current) {
      appendActivity(`${nowTimeLabel()} / robot connected / ${robotIp || robotId}`);
    }

    if (!isNowConnected && wasConnectedRef.current) {
      appendError(`${nowTimeLabel()} / robot disconnected`);
    }

    wasConnectedRef.current = isNowConnected;
  }, [statusUrl, robotId, robotIp, appendActivity, appendError]);

  const connectRobot = useCallback(async () => {
    if (!robotIp) {
      setConnecting(false);
      setConnected(false);
      appendError(`${nowTimeLabel()} / không có robot ip trong cookie`);
      return;
    }

    try {
      setConnecting(true);

      const response = await fetch(connectUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          addr: robotIp,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok || data?.ok === false || data?.connected === false) {
        throw new Error(data?.error || "Connect robot failed");
      }

      await fetchStatus();
    } catch (error) {
      setConnected(false);
      appendError(`${nowTimeLabel()} / connect error / ${String(error)}`);
    } finally {
      setConnecting(false);
    }
  }, [robotIp, connectUrl, fetchStatus, appendError]);

  useEffect(() => {
    if (!robotIp) return;

    connectRobot();

    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
    }

    pollTimerRef.current = setInterval(() => {
      fetchStatus().catch((error) => {
        setConnected(false);
        appendError(`${nowTimeLabel()} / status poll error / ${String(error)}`);
      });
    }, 3000);

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [robotIp, connectRobot, fetchStatus, appendError]);

async function sendTextCommand(textOverride?: string) {
  const text = (textOverride ?? commandText).trim();

  if (!text) {
    appendError(`${nowTimeLabel()} / chưa có text để gửi`);
    return;
  }

  if (!robotIp) {
    appendError(`${nowTimeLabel()} / không có robot ip trong cookie`);
    return;
  }

  setIsSending(true);
  setCommandResult(null);

  try {
    const payload = {
      addr: robotIp,
      text,
    };

    console.log("TEXT COMMAND PAYLOAD =", payload);

    const response = await fetch(textCommandUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data: TextCommandResponse = await response.json();
    setCommandResult(data);

    if (response.ok && data.success) {
      appendActivity(`${nowTimeLabel()} / "${text}" / OK`);
    } else {
      appendError(
        `${nowTimeLabel()} / "${text}" / ERROR / ${data.error || "Unknown error"}`
      );
    }
  } catch (error) {
    appendError(`${nowTimeLabel()} / "${text}" / FETCH ERROR / ${String(error)}`);
    setCommandResult({
      success: false,
      input_text: text,
      error: String(error),
    });
  } finally {
    setIsSending(false);
  }
}
  function setupSpeechRecognition() {
    if (typeof window === "undefined") return null;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setVoiceSupported(false);
      return null;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "vi-VN";
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.onerror = (event: any) => {
      setIsListening(false);
      appendError(`${nowTimeLabel()} / voice error / ${event?.error || "unknown"}`);
    };

    recognition.onresult = async (event: any) => {
      let finalText = "";
      for (let i = 0; i < event.results.length; i++) {
        finalText += `${event.results[i][0].transcript} `;
      }
      finalText = finalText.trim();
      setCommandText(finalText);
      await sendTextCommand(finalText);
    };

    recognitionRef.current = recognition;
    return recognition;
  }

  function handleStartVoice() {
    const recognition = recognitionRef.current || setupSpeechRecognition();
    if (!recognition) return;

    setCommandText("");
    recognition.start();
  }

  function handleStopVoice() {
    recognitionRef.current?.stop?.();
  }

  async function handleReconnect() {
    await connectRobot();
  }

  function handleDisconnectUiOnly() {
    setConnected(false);
    wasConnectedRef.current = false;
    appendActivity(`${nowTimeLabel()} / disconnect ui`);
  }

  const displayName = statusData?.name || "Robot A";
  const displayBattery = statusData?.telemetry?.battery ?? statusData?.battery ?? "--";
  const displayFps = statusData?.telemetry?.fps ?? statusData?.fps ?? 0;
  const displayStatus = statusData?.status_text || (connected ? "online" : "offline");
  const displayFloor = statusData?.floor || "1st";
  const displayWater = statusData?.water_level ?? 50;
  const displayLocation = robotIp || "No robot selected";

  return (
    <div className="flex h-full min-h-screen bg-[#160626]">
      <div className="flex-1 flex flex-col p-6 gap-5 overflow-y-auto">
        <h1 className="gradient-title text-center text-2xl">Autonomous Control</h1>

        <DarkCard>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-gradient-to-br from-pink-500/30 to-purple-600/30 border border-pink-500/20">
                <Bot size={28} className="text-green-400" />
              </div>
              <span className="text-white text-xl font-bold">{displayName}</span>
            </div>

            <button
              onClick={connected ? handleDisconnectUiOnly : handleReconnect}
              disabled={connecting || !robotIp}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-semibold transition-all duration-200 cursor-pointer disabled:opacity-50 ${
                connected
                  ? "bg-red-500 hover:bg-red-600 text-white"
                  : "bg-green-600 hover:bg-green-700 text-white"
              }`}
            >
              {connecting ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Connecting
                </>
              ) : connected ? (
                <>
                  <WifiOff size={14} />
                  Disconnect
                </>
              ) : (
                <>
                  <Wifi size={14} />
                  Connect
                </>
              )}
            </button>
          </div>

          <p className="text-white/50 text-xs mb-4 uppercase tracking-widest">
            Robot Details
          </p>

          <div className="grid grid-cols-3 gap-y-5 gap-x-8">
            <StatBlock value={displayLocation} label="Robot Address" />
            <StatBlock value={connected ? "Connected" : "Disconnected"} label="Connection" />
            <StatBlock value={displayFloor} label="Floor" />
            <StatBlock value={displayStatus} label="Status" />
            <StatBlock value={`${displayWater}%`} label="Water Level" />
            <StatBlock value={`${displayBattery}%`} label="Battery" />
          </div>
        </DarkCard>

        <DarkCard>
          <SectionLabel>Voice / Text command</SectionLabel>

          <div className="space-y-3">
            <textarea
              value={commandText}
              onChange={(e) => setCommandText(e.target.value)}
              placeholder='Ví dụ: "đứng lên", "bắt tay", "vẫy tay", "reset"'
              className="w-full min-h-[110px] rounded-xl bg-[#1b1233] border border-white/10 text-white p-4 outline-none resize-none"
            />

            <div className="flex flex-wrap gap-3">
              <button
                onClick={handleStartVoice}
                disabled={!voiceSupported || isListening || isSending || !connected}
                className="inline-flex items-center gap-2 rounded-xl px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white"
              >
                <Mic size={16} />
                {isListening ? "Đang nghe..." : "Bắt đầu nói"}
              </button>

              <button
                onClick={handleStopVoice}
                disabled={!voiceSupported || !isListening}
                className="inline-flex items-center gap-2 rounded-xl px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white"
              >
                Stop
              </button>

              <button
                onClick={() => sendTextCommand()}
                disabled={isSending || !connected}
                className="inline-flex items-center gap-2 rounded-xl px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white"
              >
                {isSending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                {isSending ? "Đang gửi..." : "Gửi lệnh"}
              </button>
            </div>

            {!voiceSupported && (
              <p className="text-xs text-yellow-300">
                Browser này không hỗ trợ SpeechRecognition. Bạn vẫn có thể nhập text và gửi lệnh.
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              {["đứng lên", "nằm xuống", "bò", "bắt tay", "vẫy tay", "reset"].map((item) => (
                <button
                  key={item}
                  onClick={() => setCommandText(item)}
                  className="px-3 py-1.5 text-sm rounded-full bg-white/5 hover:bg-white/10 text-white border border-white/10"
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        </DarkCard>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <SectionLabel>Lidar map</SectionLabel>
            <div className="bg-[#0f0822] rounded-xl h-44 flex items-center justify-center border border-white/5">
              <span className="text-white/20 text-xs">No data</span>
            </div>
          </div>

          <div>
            <SectionLabel>Path planning</SectionLabel>
            <div className="bg-[#0f0822] rounded-xl h-44 flex items-center justify-center border border-white/5">
              <span className="text-white/20 text-xs">No data</span>
            </div>
          </div>
        </div>

        <div className="bg-[#0f0822] rounded-xl overflow-hidden border border-white/5 relative">
          <div className="w-full h-72 bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center relative">
            <span className="absolute top-3 left-4 text-green-400 font-mono font-bold text-sm tracking-wider">
              FPS:{displayFps}
            </span>
            <div className="text-white/20 text-sm flex flex-col items-center gap-2">
              <Activity size={32} className="text-white/10" />
              <span>Camera stream unavailable</span>
            </div>
          </div>
        </div>

        <DarkCard>
          <SectionLabel>Command result</SectionLabel>
          <pre className="text-xs text-white/80 whitespace-pre-wrap break-words overflow-x-auto">
            {commandResult
              ? JSON.stringify(commandResult, null, 2)
              : "Chưa có dữ liệu."}
          </pre>
        </DarkCard>
      </div>

      <div className="w-72 shrink-0 bg-[#1A0F28] border-l border-white/10 flex flex-col gap-5 p-5 overflow-y-auto">
        <div>
          <div className="space-y-2">
            {[
              { label: "Motor", value: connected ? "Online" : "Offline" },
              { label: "Speech", value: connected ? "Ready" : "Down" },
              { label: "Vision", value: displayFps ? `${displayFps} FPS` : "0 FPS" },
              { label: "Air", value: "-" },
              { label: "Water", value: `${displayWater}%` },
              { label: "Speed", value: "-" },
              { label: "Sensor", value: connected ? "OK" : "N/A" },
              { label: "Battery", value: `${displayBattery}%` },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between py-1">
                <span className="text-white/70 text-sm">{label}</span>
                <span className="text-white font-semibold text-sm">{value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-white/10" />

        <div>
          <SectionLabel>Activity log</SectionLabel>
          <DarkCard className="min-h-[120px]">
            {activityLog.length === 0 ? (
              <span className="text-white/20 text-xs">No activity yet</span>
            ) : (
              <ul className="space-y-1">
                {activityLog.map((entry, i) => (
                  <li key={i} className="text-white/60 text-xs leading-relaxed">
                    {entry}
                  </li>
                ))}
              </ul>
            )}
          </DarkCard>
        </div>

        <div>
          <SectionLabel>Error log</SectionLabel>
          <DarkCard className="min-h-[100px]">
            {errorLog.length === 0 ? (
              <div className="flex items-start gap-2">
                <AlertTriangle size={14} className="text-white/20 mt-0.5 shrink-0" />
                <span className="text-white/20 text-xs">No errors recorded</span>
              </div>
            ) : (
              <ul className="space-y-2">
                {errorLog.map((entry, i) => (
                  <li key={i} className="text-red-300/80 text-xs leading-relaxed">
                    {entry}
                  </li>
                ))}
              </ul>
            )}
          </DarkCard>
        </div>
      </div>
    </div>
  );
}