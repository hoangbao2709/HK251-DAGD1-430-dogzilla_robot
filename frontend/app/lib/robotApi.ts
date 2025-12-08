// app/lib/robotApi.ts
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/control";

export const DEFAULT_DOG_SERVER =
  process.env.NEXT_PUBLIC_DOGZILLA_BASE || "http://127.0.0.1:9000";

export const robotId = "robot-a";

// ==============================
// Generic API wrapper (trả JSON trực tiếp)
// ==============================
async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) {
    throw new Error("API_BASE is not configured");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  const json = await res.json().catch(() => ({}));

  if (!res.ok) {
    const msg = (json as any)?.error || `HTTP ${res.status}`;
    const err: any = new Error(msg);
    err.status = res.status;
    err.body = json;
    throw err;
  }

  return json as T;
}

// ==============================
// Robot API functions
// ==============================
export const RobotAPI = {
  // /control/api/robots/robot-a/connect/
  connect: (addr: string) =>
    api<{ connected: boolean; error?: string; log?: string }>(
      `/api/robots/${robotId}/connect/`,
      {
        method: "POST",
        body: JSON.stringify({ addr }),
      }
    ),

  // /control/api/robots/robot-a/status/
  status: () => api<any>(`/api/robots/${robotId}/status/`),

  // /control/api/robots/robot-a/fpv/
  // backend nên trả: { "stream_url": "http://.../camera/stream" }
  fpv: () => api<{ stream_url: string | null }>(`/api/robots/${robotId}/fpv/`),

  // speed mode: "slow" | "normal" | "high"
  speed: (mode: "slow" | "normal" | "high") =>
    api<any>(`/api/robots/${robotId}/command/speed/`, {
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
    api<any>(`/api/robots/${robotId}/command/move/`, {
      method: "POST",
      body: JSON.stringify(cmd),
    }),

  lidar: (action: "start" | "stop") =>
    api<any>(`/api/robots/${robotId}/command/lidar/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  posture: (name: string) =>
    api<any>(`/api/robots/${robotId}/command/posture/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  behavior: (name: string) =>
    api<any>(`/api/robots/${robotId}/command/behavior/`, {
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
    api<any>(`/api/robots/${robotId}/command/body_adjust/`, {
      method: "POST",
      body: JSON.stringify(sl),
    }),

  stabilizingMode: (action: "on" | "off" | "toggle") =>
    api<any>(`/api/robots/${robotId}/command/stabilizing_mode/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
};
