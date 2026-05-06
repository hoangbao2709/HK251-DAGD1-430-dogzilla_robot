from __future__ import annotations

import logging
import math
import os
import sys
import time
from typing import Literal

import requests
from fastmcp import FastMCP

logger = logging.getLogger("RobotController")

if sys.platform == "win32":
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

mcp = FastMCP("RobotController")

ROBOT_IP = os.getenv("ROBOT_IP", "127.0.0.1")
ROBOT_PORT = os.getenv("ROBOT_PORT", "9000")
MAP_SERVER_PORT = os.getenv("MAP_SERVER_PORT", "8080")
REQUEST_TIMEOUT = float(os.getenv("ROBOT_TIMEOUT", "5"))

CONTROL_URL = f"http://{ROBOT_IP}:{ROBOT_PORT}/control"
MAP_BASE_URL = f"http://{ROBOT_IP}:{MAP_SERVER_PORT}"

WAYPOINT_REACH_TOLERANCE_M = float(os.getenv("WAYPOINT_REACH_TOLERANCE_M", "0.35"))
WAYPOINT_WAIT_TIMEOUT_SEC = float(os.getenv("WAYPOINT_WAIT_TIMEOUT_SEC", "120"))
WAYPOINT_POLL_INTERVAL_SEC = float(os.getenv("WAYPOINT_POLL_INTERVAL_SEC", "1.0"))

POSTURES = {
    "Lie_Down",
    "Stand_Up",
    "Crawl",
    "Squat",
    "Sit_Down",
}

BEHAVIORS = {
    "Turn_Around",
    "Mark_Time",
    "Turn_Roll",
    "Turn_Pitch",
    "Turn_Yaw",
    "3_Axis",
    "Pee",
    "Wave_Hand",
    "Stretch",
    "Wave_Body",
    "Swing",
    "Pray",
    "Seek",
    "Handshake",
    "Play_Ball",
}


def send_control(payload: dict) -> dict:
    try:
        response = requests.post(CONTROL_URL, json=payload, timeout=REQUEST_TIMEOUT)
        response_text = response.text
        try:
            response_body = response.json()
        except ValueError:
            response_body = {"raw": response_text}

        result = {
            "success": response.ok,
            "url": CONTROL_URL,
            "status_code": response.status_code,
            "payload": payload,
            "response": response_body,
        }
        logger.info("Sent payload=%s status=%s", payload, response.status_code)
        return result
    except requests.RequestException as exc:
        logger.error("Failed to send payload=%s error=%s", payload, exc)
        return {
            "success": False,
            "url": CONTROL_URL,
            "payload": payload,
            "error": str(exc),
        }


def call_map_api(method: str, path: str, **kwargs) -> dict:
    url = f"{MAP_BASE_URL}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            timeout=REQUEST_TIMEOUT,
            **kwargs,
        )
        response_text = response.text
        try:
            response_body = response.json()
        except ValueError:
            response_body = {"raw": response_text}

        return {
            "success": response.ok,
            "url": url,
            "status_code": response.status_code,
            "response": response_body,
        }
    except requests.RequestException as exc:
        return {
            "success": False,
            "url": url,
            "error": str(exc),
        }


def get_point(name: str) -> dict:
    result = call_map_api("GET", f"/points/{name}")
    if not result["success"]:
        return result
    return result


def get_state() -> dict:
    return call_map_api("GET", "/state")


def is_goal_reached(target_x: float, target_y: float, tolerance_m: float) -> dict:
    state_result = get_state()
    if not state_result["success"]:
        return {
            "success": False,
            "reached": False,
            "error": "cannot read robot state",
            "state_result": state_result,
        }

    state = state_result.get("response") or {}
    pose = state.get("pose") or {}

    if not pose.get("ok"):
        return {
            "success": False,
            "reached": False,
            "error": "robot pose not available",
            "state_result": state_result,
        }

    rx = float(pose["x"])
    ry = float(pose["y"])
    dist = math.hypot(target_x - rx, target_y - ry)

    return {
        "success": True,
        "reached": dist <= tolerance_m,
        "distance_m": dist,
        "robot_pose": {
            "x": rx,
            "y": ry,
            "theta": float(pose.get("theta", 0.0)),
        },
    }


def wait_until_point_reached(target_x: float, target_y: float) -> dict:
    started_at = time.time()

    while True:
        check = is_goal_reached(
            target_x=target_x,
            target_y=target_y,
            tolerance_m=WAYPOINT_REACH_TOLERANCE_M,
        )

        if check["success"] and check["reached"]:
            return {
                "success": True,
                "message": "reached target",
                "final_check": check,
            }

        if time.time() - started_at > WAYPOINT_WAIT_TIMEOUT_SEC:
            return {
                "success": False,
                "message": "timeout waiting for waypoint",
                "last_check": check,
            }

        time.sleep(WAYPOINT_POLL_INTERVAL_SEC)


@mcp.tool()
def reset_robot() -> dict:
    """Reset the robot to its default state."""
    return send_control({"command": "reset"})


@mcp.tool()
def rotation() -> dict:
    """Trigger the robot rotation command."""
    return send_control({"command": "rotation"})


@mcp.tool()
def set_posture(
    name: Literal["Lie_Down", "Stand_Up", "Crawl", "Squat", "Sit_Down"]
) -> dict:
    """Set the robot posture using one of the supported posture names."""
    if name not in POSTURES:
        return {"success": False, "error": f"Invalid posture: {name}"}
    return send_control({"command": "posture", "name": name})


@mcp.tool()
def play_behavior(
    name: Literal[
        "Turn_Around",
        "Mark_Time",
        "Turn_Roll",
        "Turn_Pitch",
        "Turn_Yaw",
        "3_Axis",
        "Pee",
        "Wave_Hand",
        "Stretch",
        "Wave_Body",
        "Swing",
        "Pray",
        "Seek",
        "Handshake",
        "Play_Ball",
    ]
) -> dict:
    """Play a predefined robot behavior such as Handshake, Wave_Hand, or Play_Ball."""
    if name not in BEHAVIORS:
        return {"success": False, "error": f"Invalid behavior: {name}"}
    return send_control({"command": "behavior", "name": name})


@mcp.tool()
def go_to_point(name: str) -> dict:
    """Go to a saved point on the robot map by name, for example A, B, or C."""
    if not name or not str(name).strip():
        return {"success": False, "error": "Point name is required"}

    point_name = str(name).strip().upper()
    result = call_map_api(
        "POST",
        "/go_to_point",
        json={"name": point_name},
    )

    if not result["success"]:
        return {
            "success": False,
            "error": "Failed to send go_to_point",
            "result": result,
        }

    return {
        "success": True,
        "point": point_name,
        "result": result,
    }


@mcp.tool()
def goto_waypoints(points: list[str]) -> dict:
    """Go through multiple saved points in order, for example A, B, C."""
    if not points:
        return {"success": False, "error": "Points list is required"}

    normalized_points = [str(p).strip().upper() for p in points if str(p).strip()]
    if not normalized_points:
        return {"success": False, "error": "No valid points provided"}

    executed = []

    for point_name in normalized_points:
        point_result = get_point(point_name)
        if not point_result["success"]:
            return {
                "success": False,
                "error": f"Point not found or cannot read point: {point_name}",
                "executed": executed,
                "point_result": point_result,
            }

        point_data = point_result.get("response") or {}
        target_x = float(point_data["x"])
        target_y = float(point_data["y"])

        send_result = call_map_api(
            "POST",
            "/go_to_point",
            json={"name": point_name},
        )
        if not send_result["success"]:
            return {
                "success": False,
                "error": f"Failed to send waypoint: {point_name}",
                "executed": executed,
                "send_result": send_result,
            }

        wait_result = wait_until_point_reached(target_x, target_y)
        executed.append(
            {
                "point": point_name,
                "target_x": target_x,
                "target_y": target_y,
                "send_result": send_result,
                "wait_result": wait_result,
            }
        )

        if not wait_result["success"]:
            return {
                "success": False,
                "error": f"Failed while waiting to reach waypoint: {point_name}",
                "executed": executed,
            }

    return {
        "success": True,
        "message": "Completed all waypoints",
        "points": normalized_points,
        "executed": executed,
    }


@mcp.tool()
def stop_navigation() -> dict:
    """Stop current navigation and clear path on the robot map server."""
    result = call_map_api("GET", "/clear_path")

    if not result["success"]:
        return {
            "success": False,
            "error": "Failed to stop navigation",
            "result": result,
        }

    return {
        "success": True,
        "result": result,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
