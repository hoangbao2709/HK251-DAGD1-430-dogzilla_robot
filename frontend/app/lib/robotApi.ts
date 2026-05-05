// app/lib/robotApi.ts
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const DEFAULT_DOG_SERVER = "http://100.95.128.237:9000";

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

type MoveVectorPayload = {
  vx: number;
  vy: number;
  vz: number;
  rx: number;
  ry: number;
  rz: number;
};

type MoveCommandPayload = {
  command:
  | "forward"
  | "backward"
  | "left"
  | "right"
  | "turnleft"
  | "turnright"
  | "stop";
  step?: number;
  speed?: number;
  mode?: "slow" | "normal" | "high";
};

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

  move: (payload: MoveVectorPayload | MoveCommandPayload) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/move/`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  lidar: (action: "start" | "stop") =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/lidar/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  lidarReset: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/lidar/reset/`, {
      method: "POST",
      body: JSON.stringify({}),
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

  qrMetrics: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/qr-metrics/`),

  logQRAttempt: (payload: { name: string; success: boolean; reason?: string }) =>
  api<any>(`${CONTROL_PREFIX}/${robotId}/qr-metrics/`, {
    method: "POST",
    body: JSON.stringify(payload),
  }),

  qrPosition: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/qr/position/`),

  slamState: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/slam/state/`),

  clearNavigation: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/slam/clear/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  setInitialPose: (payload: {
    x: number;
    y: number;
    yaw?: number;
  }) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/slam/initial-pose/`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

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

  createPointFromObstacle: (payload: {
    name: string;
    yaw?: number;
  }) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/points/from-obstacle/`, {
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

  manualGoal: (payload: {
    x: number;
    y: number;
    yaw?: number;
    addr?: string;
    route_name?: string;
  }) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/manual-goal/`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  qrVideoFeedUrl: () =>
    `${API_BASE}${CONTROL_PREFIX}/${robotId}/qr/video-feed/`,

  slamMapUrl: (ts?: number) =>
    `${API_BASE}${CONTROL_PREFIX}/${robotId}/slam/map.png${ts ? `?t=${ts}` : ""}`,

  server: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/server/`),

  health: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/health/`),

  networkMetrics: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/network/metrics/`),

  evaluationMetrics: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/evaluation/metrics/`),

  sessionSummary: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/session/summary/`),

  frameUrl: (ts?: number) =>
    `${API_BASE}${CONTROL_PREFIX}/${robotId}/frame/${ts ? `?t=${ts}` : ""}`,

  test: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/test/`),

  controlStatus: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/control-status/`),

  pace: (mode: "slow" | "normal" | "high") =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/pace/`, {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),

  gait: (mode: "trot" | "walk" | "high_walk") =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/gait/`, {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),

  perform: (action: "on" | "off") =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/perform/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  markTime: (value: number) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/mark-time/`, {
      method: "POST",
      body: JSON.stringify({ value }),
    }),

  reset: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/command/reset/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  events: (limit = 20, offset = 0) =>
    api<{
      ok: boolean;
      robot_id: string;
      count: number;
      limit: number;
      offset: number;
      items: Array<{
        id: string;
        timestamp: string;
        robot: string;
        event: string;
        severity: "Info" | "Warning" | "Critical";
        duration: string | null;
        status: "Success" | "Failed" | "Active";
        action: string;
        detail: string | null;
        payload: Record<string, unknown>;
      }>;
    }>(`${CONTROL_PREFIX}/${robotId}/events/?limit=${limit}&offset=${offset}`),

  patrolHistory: (date?: string) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/patrol/history/${date ? `?date=${date}` : ""}`),

  patrolStart: (payload: {
    route_name?: string;
    points: string[];
    wait_sec_per_point?: number;
    max_retry_per_point?: number;
    skip_on_fail?: boolean;
  }) =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/patrol/start/`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  patrolStop: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/patrol/stop/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  patrolStatus: () =>
    api<any>(`${CONTROL_PREFIX}/${robotId}/patrol/status/`),
};
