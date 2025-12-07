// app/lib/robotApi.ts
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/control";

export const DEFAULT_DOG_SERVER =
  process.env.NEXT_PUBLIC_DOGZILLA_BASE || "http://127.0.0.1:9000";

export const robotId = "robot-a";

// ==============================
// Generic API wrapper
// ==============================
async function api<T = any>(
  path: string,
  init?: RequestInit
): Promise<{ ok: boolean; log?: string; data?: T; error?: string } | null> {
  if (!API_BASE) return null;

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });

    const json = await res.json().catch(() => ({}));

    return {
      ok: res.ok,
      log: json.log,
      data: json,
      error: !res.ok ? json.error || `HTTP ${res.status}` : undefined,
    };
  } catch (e: any) {
    return {
      ok: false,
      error: e?.message || "Network error",
      log: `[Network error] ${path}: ${e?.message}`,
    };
  }
}

// ==============================
// Robot API functions
// ==============================
export const RobotAPI = {
  connect: (addr: string) =>
    api(`/api/robots/${robotId}/connect/`, {
      method: "POST",
      body: JSON.stringify({ addr }),
    }),

  status: () => api(`/api/robots/${robotId}/status/`),

  fpv: () => api(`/api/robots/${robotId}/fpv/`),

  speed: (mode: "slow" | "normal" | "high") =>
    api(`/api/robots/${robotId}/command/speed/`, {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),

  move: (cmd: {
    vx: number;
    vy: number;
    vz: number;
    rx: number;
    ry: number;
    rz: number;
  }) =>
    api(`/api/robots/${robotId}/command/move/`, {
      method: "POST",
      body: JSON.stringify(cmd),
    }),

  lidar: (action: "start" | "stop") =>
    api(`/api/robots/${robotId}/command/lidar/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  posture: (name: string) =>
    api(`/api/robots/${robotId}/command/posture/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  behavior: (name: string) =>
    api(`/api/robots/${robotId}/command/behavior/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  body: (sl: {
    tx: number;
    ty: number;
    tz: number;
    rx: number;
    ry: number;
    rz: number;
  }) =>
    api(`/api/robots/${robotId}/command/body_adjust/`, {
      method: "POST",
      body: JSON.stringify(sl),
    }),

  stabilizingMode: (action: "on" | "off" | "toggle") =>
    api(`/api/robots/${robotId}/command/stabilizing_mode/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
};
