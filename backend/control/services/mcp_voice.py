from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from django.conf import settings

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
logger = logging.getLogger(__name__)

TEXT_TOOL_MAP = [
    (["đứng lên", "stand up"], ("set_posture", {"name": "Stand_Up"})),
    (["nằm xuống", "lie down"], ("set_posture", {"name": "Lie_Down"})),
    (["bò", "crawl"], ("set_posture", {"name": "Crawl"})),
    (["ngồi", "ngồi xuống", "squat", "sit down"], ("set_posture", {"name": "Squat"})),
    (["bắt tay", "handshake"], ("play_behavior", {"name": "Handshake"})),
    (["vẫy tay", "wave hand"], ("play_behavior", {"name": "Wave_Hand"})),
    (["đánh dấu", "pee"], ("play_behavior", {"name": "Pee"})),
    (["duỗi người", "stretch"], ("play_behavior", {"name": "Stretch"})),
    (["cầu nguyện", "pray"], ("play_behavior", {"name": "Pray"})),
    (["chơi bóng", "play ball"], ("play_behavior", {"name": "Play_Ball"})),
    (["xoay vòng", "turn around"], ("play_behavior", {"name": "Turn_Around"})),
    (["chạy tại chỗ", "mark time"], ("play_behavior", {"name": "Mark_Time"})),
    (["lắc người", "swing"], ("play_behavior", {"name": "Swing"})),
    (["lắc thân", "wave body"], ("play_behavior", {"name": "Wave_Body"})),
    (["tìm kiếm", "seek"], ("play_behavior", {"name": "Seek"})),
    (["nghiêng roll", "turn roll"], ("play_behavior", {"name": "Turn_Roll"})),
    (["nghiêng pitch", "turn pitch"], ("play_behavior", {"name": "Turn_Pitch"})),
    (["nghiêng yaw", "turn yaw"], ("play_behavior", {"name": "Turn_Yaw"})),
    (["ba trục", "3 axis", "three axis"], ("play_behavior", {"name": "3_Axis"})),
    (["reset", "khởi động lại", "đặt lại"], ("reset_robot", {})),
    (["rotation", "xoay"], ("rotation", {})),
]


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_text(text: str) -> str:
    text = strip_accents((text or "").strip().lower())
    text = re.sub(r"[^a-z0-9\s,_-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_waypoints(text: str) -> List[str]:
    """
    Hỗ trợ các dạng:
    - hãy cho robot đi đến điểm A
    - đi đến điểm A
    - đi tới điểm B
    - đi đến A, B, C
    - đi qua A, B, C
    - tới điểm A và B
    - go to point A
    - move to point A, B
    """
    normalized = normalize_text(text)

    stop_phrases = [
        "dung lai",
        "dung dieu huong",
        "huy dieu huong",
        "stop navigation",
        "stop moving",
    ]
    for phrase in stop_phrases:
        if phrase in normalized:
            return []

    patterns = [
        r"^(?:hay cho robot\s+)?(?:di den|di toi|den|toi)\s+(?:diem\s+)?(.+)$",
        r"^(?:hay cho robot\s+)?di qua\s+(.+)$",
        r"^(?:please\s+)?(?:go to|move to)\s+(?:point\s+)?(.+)$",
    ]

    raw_points = None
    for pattern in patterns:
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match:
            raw_points = match.group(1).strip()
            break

    if not raw_points:
        return []

    raw_points = re.sub(r"\s+(va|and)\s+", ",", raw_points)

    points: List[str] = []
    for item in raw_points.split(","):
        point = item.strip().upper()
        point = re.sub(r"^DIEM\s+", "", point, flags=re.IGNORECASE)
        point = re.sub(r"^POINT\s+", "", point, flags=re.IGNORECASE)
        point = re.sub(r"[^A-Z0-9_-]", "", point)

        if point:
            points.append(point)

    return points


def map_text_to_tool(text: str) -> Tuple[str, Dict[str, Any]]:
    normalized = normalize_text(text)

    stop_phrases = [
        "dung lai",
        "dung dieu huong",
        "huy dieu huong",
        "stop navigation",
        "stop moving",
    ]
    for phrase in stop_phrases:
        if phrase in normalized:
            return "stop_navigation", {}

    points = extract_waypoints(text)
    if points:
        if len(points) == 1:
            return "goto_point", {"name": points[0]}
        return "goto_waypoints", {"points": points}

    for phrases, target in TEXT_TOOL_MAP:
        if normalized in [normalize_text(p) for p in phrases]:
            return target

    for phrases, target in TEXT_TOOL_MAP:
        for phrase in phrases:
            if normalize_text(phrase) in normalized:
                return target

    raise ValueError(f"Không map được text command: {text}")


def parse_robot_addr(addr: str) -> Tuple[str, str, str]:
    raw = (addr or "").strip()
    if not raw:
        raise ValueError("addr is required")

    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlparse(raw)

    host = parsed.hostname
    port = parsed.port or 8080
    scheme = parsed.scheme or "http"

    if not host:
        raise ValueError(f"Robot addr không hợp lệ: {addr}")

    base_url = f"{scheme}://{host}:{port}"
    return host, str(port), base_url


def build_mcp_server_script_path() -> str:
    base_dir = Path(settings.BASE_DIR)
    script_path = base_dir / "mcp-calculator" / "robot_mcp_server.py"

    if not script_path.exists():
        raise FileNotFoundError(f"Không tìm thấy MCP server script: {script_path}")

    return str(script_path)


async def _call_mcp_tool(robot_addr: str, text: str) -> Dict[str, Any]:
    host, port, base_url = parse_robot_addr(robot_addr)
    tool_name, arguments = map_text_to_tool(text)
    script_path = build_mcp_server_script_path()

    env = os.environ.copy()
    env["ROBOT_IP"] = host
    env["ROBOT_PORT"] = port
    env["ROBOT_BASE_URL"] = base_url
    env["MAP_SERVER_PORT"] = env.get("MAP_SERVER_PORT", "8080")

    transport = StdioTransport(
        command=sys.executable,
        args=[script_path],
        env=env,
        cwd=str(Path(script_path).parent),
        keep_alive=False,
    )

    client = Client(transport)

    logger.info(
        "MCP text command | robot=%s | tool=%s | args=%s",
        base_url,
        tool_name,
        arguments,
    )

    async with client:
        result = await client.call_tool(tool_name, arguments)

        if hasattr(result, "data"):
            payload = result.data
        elif hasattr(result, "structured_content"):
            payload = result.structured_content
        else:
            payload = str(result)

        return {
            "ok": True,
            "robot_addr": base_url,
            "tool": tool_name,
            "arguments": arguments,
            "content": payload,
            "raw": str(result),
        }

def process_text_command(robot_addr: str, text: str) -> Dict[str, Any]:
    if not robot_addr:
        raise ValueError("robot_addr is required")
    if not text or not text.strip():
        raise ValueError("text is required")
    tool_name, arguments = map_text_to_tool(text)
    print("[mcp_voice] mapped tool =", tool_name)
    print("[mcp_voice] mapped args =", arguments)
    return asyncio.run(_call_mcp_tool(robot_addr=robot_addr, text=text))