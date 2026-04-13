export const ROBOT_IP_COOKIE = "robot_ip";
export const ROBOT_ID_COOKIE = "robot_id";

export function setCookie(name: string, value: string, maxAgeSeconds = 60 * 60 * 24 * 7) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSeconds}; samesite=lax`;
}

export function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;

  const cookies = document.cookie.split(";").map((c) => c.trim());
  const found = cookies.find((c) => c.startsWith(`${name}=`));
  if (!found) return null;

  return decodeURIComponent(found.substring(name.length + 1));
}

export function deleteCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; path=/; max-age=0; samesite=lax`;
}

export function saveRobotSession(ip: string, robotId = "robot-a") {
  setCookie(ROBOT_IP_COOKIE, ip);
  setCookie(ROBOT_ID_COOKIE, robotId);
}

export function getRobotSession() {
  return {
    ip: getCookie(ROBOT_IP_COOKIE),
    robotId: getCookie(ROBOT_ID_COOKIE) || "robot-a",
  };
}

export function clearRobotSession() {
  deleteCookie(ROBOT_IP_COOKIE);
  deleteCookie(ROBOT_ID_COOKIE);
}