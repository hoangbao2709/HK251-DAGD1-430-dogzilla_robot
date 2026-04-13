// app/lib/robotApi.ts
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const DEFAULT_DOG_SERVER = "http://100.95.128.237:8080";

export const robotId = "robot-a";

type RequestInitWithBody = RequestInit & {
  body?: string;
};

async function api<T = any>(path: string, init?: RequestInitWithBody): Promise<T> {
  if (!API_BASE) {
    throw new Error("API_BASE is not configured");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  const json = await res.json().catch(() => ({}));

  if (!res.ok) {
    const msg = (json as any)?.error || (json as any)?.message || `HTTP ${res.status}`;
    const err: any = new Error(msg);
    err.status = res.status;
    err.body = json;
    throw err;
  }

  return json as T;
}

const CONTROL_PREFIX = "/control/api/robots";

export const RobotAPI = {
  connect: (addr: string) =>
    api<{ ok?: boolean; connected?: boolean; error?: string; log?: string }>(
      `${CONTROL_PREFIX}/${robotId}/connect/`,
      {
        method: "POST",
        body: JSON.stringify({ addr }),
      }
    ),

  status: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/status/`),

  fpv: () =>
    api<{ stream_url: string | null }>(
      `${CONTROL_PREFIX}/${robotId}/fpv/`
    ),

  speed: (mode: "slow" | "normal" | "high") =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/speed/`, {
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
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/move/`, {
      method: "POST",
      body: JSON.stringify(cmd),
    }),

  lidar: (action: "start" | "stop") =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/lidar/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  posture: (name: string) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/posture/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  behavior: (name: string) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/behavior/`, {
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
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/body_adjust/`, {
      method: "POST",
      body: JSON.stringify(sl),
    }),

  stabilizingMode: (action: "on" | "off" | "toggle") =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/stabilizing_mode/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  textCommand: (text: string, addr?: string) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/text/`, {
      method: "POST",
      body: JSON.stringify({
        text,
        ...(addr ? { addr } : {}),
      }),
    }),

  qrState: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/qr/state/`),

  qrPosition: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/qr/position/`),

  slamState: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/slam/state/`),

  points: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/points/`),

  createPoint: (payload: {
    name: string;
    x: number;
    y: number;
    yaw?: number;
  }) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/points/`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deletePoint: (name: string) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/delete-point/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  goToPoint: (name: string) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/go-to-point/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  goToMarker: (payload: {
    label: string;
    x: number;
    y: number;
    yaw?: number;
  }) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/go-to-marker/`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  qrVideoFeedUrl: () =>
    `${API_BASE}${CONTROL_PREFIX}/${robotId}/qr/video-feed/`,

  slamMapUrl: (ts?: number) =>
    `${API_BASE}${CONTROL_PREFIX}/${robotId}/slam/map.png${ts ? `?t=${ts}` : ""}`,
};