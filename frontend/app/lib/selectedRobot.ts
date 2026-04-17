"use client";

const SELECTED_ROBOT_ADDR_KEY = "dogzilla_selected_robot_addr";
const SELECTED_ROBOT_ADDR_COOKIE = "dogzilla_selected_robot_addr";

function readCookie(name: string) {
  if (typeof document === "undefined") return null;

  const cookies = document.cookie.split(";").map((item) => item.trim());
  const match = cookies.find((item) => item.startsWith(`${name}=`));
  if (!match) return null;

  const value = match.slice(name.length + 1);
  return value ? decodeURIComponent(value) : null;
}

export function getSelectedRobotAddr() {
  if (typeof window === "undefined") return null;

  const fromSession = window.sessionStorage.getItem(SELECTED_ROBOT_ADDR_KEY);
  if (fromSession) return fromSession;

  const fromCookie = readCookie(SELECTED_ROBOT_ADDR_COOKIE);
  if (fromCookie) {
    window.sessionStorage.setItem(SELECTED_ROBOT_ADDR_KEY, fromCookie);
    return fromCookie;
  }

  return null;
}

export function setSelectedRobotAddr(addr: string) {
  if (typeof window === "undefined") return;

  window.sessionStorage.setItem(SELECTED_ROBOT_ADDR_KEY, addr);
  document.cookie = `${SELECTED_ROBOT_ADDR_COOKIE}=${encodeURIComponent(
    addr
  )}; path=/`;
}

export function clearSelectedRobotAddr() {
  if (typeof window === "undefined") return;

  window.sessionStorage.removeItem(SELECTED_ROBOT_ADDR_KEY);
  document.cookie = `${SELECTED_ROBOT_ADDR_COOKIE}=; path=/; max-age=0`;
}
