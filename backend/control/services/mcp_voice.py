from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from django.conf import settings

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)

TEXT_TOOL_MAP = [
    (["đứng lên", "stand up"], ("set_posture", {"name": "Stand_Up"})),
    (["nằm xuống", "lie down"], ("set_posture", {"name": "Lie_Down"})),
    (["bò", "crawl"], ("set_posture", {"name": "Crawl"})),
    (["ngồi", "squat"], ("set_posture", {"name": "Squat"})),
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


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_waypoints(text: str) -> List[str]:
    """
    Hỗ trợ:
    - đi đến điểm A
    - đi tới điểm A
    - đi đến A, B, C
    - đi qua A, B, C
    - go to point A, B, C
    """
    normalized = normalize_text(text)

    patterns = [
        r"^(?:đi đến|đi tới|đến|tới)\s+(?:điểm\s+)?(.+)$",
        r"^đi qua\s+(.+)$",
        r"^go to\s+(?:point\s+)?(.+)$",
        r"^move to\s+(?:point\s+)?(.+)$",
    ]

    raw_points = None
    for pattern in patterns:
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match:
            raw_points = match.group(1).strip()
            break

    if not raw_points:
        return []

    # đổi "và" / "and" thành dấu phẩy để tách đều
    raw_points = re.sub(r"\s+(và|and)\s+", ",", raw_points)

    points = []
    for item in raw_points.split(","):
        point = item.strip().upper()
        point = re.sub(r"^điểm\s+", "", point, flags=re.IGNORECASE)
        point = re.sub(r"^point\s+", "", point, flags=re.IGNORECASE)

        # bỏ ký tự thừa, giữ chữ/số/_/-
        point = re.sub(r"[^A-Z0-9_-]", "", point)

        if point:
            points.append(point)

    return points


def map_text_to_tool(text: str) -> Tuple[str, Dict[str, Any]]:
    normalized = normalize_text(text)

    # Ưu tiên parse lệnh điều hướng trước
    points = extract_waypoints(normalized)
    if points:
        if len(points) == 1:
            return "navigate_to_point", {"point": points[0]}
        return "navigate_waypoints", {"points": points}

    for phrases, target in TEXT_TOOL_MAP:
        if normalized in phrases:
            return target

    for phrases, target in TEXT_TOOL_MAP:
        for phrase in phrases:
            if phrase in normalized:
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
    port = parsed.port or 9000
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

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[script_path],
        env=env,
    )

    logger.info(
        "MCP text command | robot=%s | tool=%s | args=%s",
        base_url,
        tool_name,
        arguments,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)

            content = []
            if hasattr(result, "content") and result.content:
                for item in result.content:
                    if hasattr(item, "text"):
                        content.append(item.text)
                    else:
                        content.append(str(item))

            return {
                "ok": True,
                "robot_addr": base_url,
                "tool": tool_name,
                "arguments": arguments,
                "content": content,
                "raw": str(result),
            }


def process_text_command(robot_addr: str, text: str) -> Dict[str, Any]:
    if not robot_addr:
        raise ValueError("robot_addr is required")
    if not text or not text.strip():
        raise ValueError("text is required")

    return asyncio.run(_call_mcp_tool(robot_addr=robot_addr, text=text))