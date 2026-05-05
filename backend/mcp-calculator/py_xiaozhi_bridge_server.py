from __future__ import annotations

import os
from typing import Any

import requests
from fastmcp import FastMCP

mcp = FastMCP("PyXiaozhiDogzillaBridge")

BACKEND_BASE_URL = os.getenv("DOGZILLA_BACKEND_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
BRIDGE_TOKEN = os.getenv("XIAOZHI_BRIDGE_TOKEN", "")
DEFAULT_ROBOT_ID = os.getenv("XIAOZHI_DEFAULT_ROBOT_ID", "robot-a")
DEFAULT_ROBOT_ADDR = os.getenv("XIAOZHI_DEFAULT_ROBOT_ADDR", "")
REQUEST_TIMEOUT = float(os.getenv("XIAOZHI_BRIDGE_TIMEOUT", "20"))


def _build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if BRIDGE_TOKEN:
        headers["Authorization"] = f"Bearer {BRIDGE_TOKEN}"
    return headers


def _bridge_url(path: str) -> str:
    return f"{BACKEND_BASE_URL}{path}"


@mcp.tool()
def bridge_health() -> dict[str, Any]:
    """Check whether the local Dogzilla backend bridge is reachable."""
    response = requests.get(
        _bridge_url("/control/api/xiaozhi/health/"),
        headers=_build_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def send_robot_text_command(
    text: str,
    robot_id: str = DEFAULT_ROBOT_ID,
    robot_addr: str = DEFAULT_ROBOT_ADDR,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Forward a Xiaozhi text command to the existing Django backend bridge."""
    payload = {
        "text": text,
        "robot_id": robot_id or DEFAULT_ROBOT_ID,
        "robot_addr": robot_addr or DEFAULT_ROBOT_ADDR,
        "dry_run": dry_run,
    }

    response = requests.post(
        _bridge_url("/control/api/xiaozhi/command/"),
        json=payload,
        headers=_build_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
