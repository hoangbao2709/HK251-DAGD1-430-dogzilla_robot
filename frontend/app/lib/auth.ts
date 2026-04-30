const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";
const USERNAME_KEY = "username";
const EMAIL_KEY = "user_email";
const ROBOT_IP_KEY = "robot_ip";
const ROBOT_ADDR_KEY = "robot_addr";
const AUTH_CHANGED_EVENT = "robot-auth-changed";

export type AuthSession = {
  access: string;
  refresh?: string | null;
  username?: string | null;
  email?: string | null;
  robotIp?: string | null;
  robotAddr?: string | null;
};

export type CurrentUser = {
  ok: boolean;
  authenticated: boolean;
  username: string;
  email: string | null;
  robot_ip?: string;
  robot_url?: string;
};

function getStorage(preferLocal = true): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return preferLocal ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

function parseJsonResponse(text: string) {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  };

  if (init?.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  const rawText = await response.text();
  const data = parseJsonResponse(rawText);

  if (!response.ok || data?.ok === false) {
    throw new Error(data?.error || data?.detail || `Request failed: ${response.status}`);
  }

  return data as T;
}

function emitAuthChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}

export function getStoredSession(): AuthSession | null {
  const local = getStorage(true);
  const session = getStorage(false);
  const access = local?.getItem(ACCESS_KEY) || session?.getItem(ACCESS_KEY);
  if (!access) return null;

  const source = local?.getItem(ACCESS_KEY) ? local : session;
  return {
    access,
    refresh: source?.getItem(REFRESH_KEY) || null,
    username: source?.getItem(USERNAME_KEY) || null,
    email: source?.getItem(EMAIL_KEY) || null,
    robotIp: source?.getItem(ROBOT_IP_KEY) || null,
    robotAddr: source?.getItem(ROBOT_ADDR_KEY) || null,
  };
}

export function saveAuthSession(payload: Partial<AuthSession>, remember = true) {
  if (!payload.access) {
    throw new Error("Missing access token");
  }

  clearAuthSession(false);
  const storage = getStorage(remember);
  if (!storage) return;

  storage.setItem(ACCESS_KEY, payload.access);
  if (payload.refresh) storage.setItem(REFRESH_KEY, payload.refresh);
  if (payload.username) storage.setItem(USERNAME_KEY, payload.username);
  if (payload.email) storage.setItem(EMAIL_KEY, payload.email);
  if (payload.robotIp) storage.setItem(ROBOT_IP_KEY, payload.robotIp);
  if (payload.robotAddr) storage.setItem(ROBOT_ADDR_KEY, payload.robotAddr);
  emitAuthChanged();
}

export function clearAuthSession(notify = true) {
  for (const storage of [getStorage(true), getStorage(false)]) {
    storage?.removeItem(ACCESS_KEY);
    storage?.removeItem(REFRESH_KEY);
    storage?.removeItem(USERNAME_KEY);
    storage?.removeItem(EMAIL_KEY);
    storage?.removeItem(ROBOT_IP_KEY);
    storage?.removeItem(ROBOT_ADDR_KEY);
  }
  if (notify) emitAuthChanged();
}

export function onAuthChanged(callback: () => void) {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(AUTH_CHANGED_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

export function getAuthHeader(): Record<string, string> {
  const session = getStoredSession();
  return session?.access ? { Authorization: `Bearer ${session.access}` } : {};
}

export const AuthAPI = {
  login: async ({
    identifier,
    password,
    remember,
    robotIp,
    robotAddr,
  }: {
    identifier: string;
    password: string;
    remember: boolean;
    robotIp?: string;
    robotAddr?: string;
  }) => {
    const data = await requestJson<any>("/api/auth/login/", {
      method: "POST",
      body: JSON.stringify({
        identifier,
        email: identifier,
        password,
        ...(robotIp ? { robot_ip: robotIp } : {}),
        ...(robotAddr ? { robot_url: robotAddr } : {}),
      }),
    });

    const access = data.access || data.token || data.access_token;
    if (!access) throw new Error("Login response did not include an access token");

    const session: AuthSession = {
      access,
      refresh: data.refresh || data.refresh_token || null,
      username: data.username || null,
      email: data.email || null,
      robotIp: data.robot_ip || null,
      robotAddr: data.robot_url || null,
    };
    saveAuthSession(session, remember);
    return session;
  },

  register: async ({
    username,
    email,
    password,
  }: {
    username: string;
    email: string;
    password: string;
  }) => {
    const data = await requestJson<any>("/api/auth/register/", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
    });

    const access = data.access || data.token || data.access_token;
    if (!access) throw new Error("Register response did not include an access token");

    const session: AuthSession = {
      access,
      refresh: data.refresh || data.refresh_token || null,
      username: data.username || null,
      email: data.email || null,
    };
    saveAuthSession(session, true);
    return session;
  },

  me: async () => {
    const session = getStoredSession();
    if (!session?.access) {
      return {
        ok: true,
        authenticated: false,
        username: "Guest",
        email: null,
      } satisfies CurrentUser;
    }

    return requestJson<CurrentUser>("/api/auth/me/", {}, session.access);
  },
};
