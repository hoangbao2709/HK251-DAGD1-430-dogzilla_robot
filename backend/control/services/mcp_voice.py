from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from django.conf import settings
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

logger = logging.getLogger(__name__)


class AmbiguousCommandError(ValueError):
    def __init__(self, message: str, *, normalized_text: str, matches: List[Dict[str, Any]]) -> None:
        super().__init__(message)
        self.normalized_text = normalized_text
        self.matches = matches


STOP_PHRASES = [
    "dung lai",
    "dung di chuyen",
    "dung dieu huong",
    "huy dieu huong",
    "stop navigation",
    "stop moving",
]

COMMAND_SPECS: list[dict[str, Any]] = [
    {
        "tool": "reset_robot",
        "arguments": {},
        "phrases": [
            "reset",
            "khoi dong lai",
            "dat lai",
            "ve mac dinh",
        ],
    },
    {
        "tool": "rotation",
        "arguments": {},
        "phrases": [
            "rotation",
            "quay tron",
            "xoay tron",
        ],
    },
    {
        "tool": "set_posture",
        "arguments": {"name": "Stand_Up"},
        "phrases": [
            "dung len",
            "stand up",
        ],
    },
    {
        "tool": "set_posture",
        "arguments": {"name": "Lie_Down"},
        "phrases": [
            "nam xuong",
            "lie down",
        ],
    },
    {
        "tool": "set_posture",
        "arguments": {"name": "Crawl"},
        "phrases": [
            "bo",
            "crawl",
        ],
    },
    {
        "tool": "set_posture",
        "arguments": {"name": "Squat"},
        "phrases": [
            "ngoi xuong",
            "squat",
            "sit down",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Handshake"},
        "phrases": [
            "bat tay",
            "handshake",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Wave_Hand"},
        "phrases": [
            "vay tay",
            "wave hand",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Pee"},
        "phrases": [
            "danh dau",
            "pee",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Stretch"},
        "phrases": [
            "vuon minh",
            "stretch",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Pray"},
        "phrases": [
            "cau nguyen",
            "pray",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Play_Ball"},
        "phrases": [
            "choi bong",
            "play ball",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Turn_Around"},
        "phrases": [
            "xoay vong",
            "quay vong",
            "turn around",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Mark_Time"},
        "phrases": [
            "chay tai cho",
            "giam chan tai cho",
            "mark time",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Swing"},
        "phrases": [
            "lac nguoi",
            "swing",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Wave_Body"},
        "phrases": [
            "lac than",
            "wave body",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Seek"},
        "phrases": [
            "tim kiem",
            "seek",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Turn_Roll"},
        "phrases": [
            "nghieng roll",
            "turn roll",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Turn_Pitch"},
        "phrases": [
            "nghieng pitch",
            "turn pitch",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "Turn_Yaw"},
        "phrases": [
            "nghieng yaw",
            "turn yaw",
        ],
    },
    {
        "tool": "play_behavior",
        "arguments": {"name": "3_Axis"},
        "phrases": [
            "ba truc",
            "3 axis",
            "three axis",
        ],
    },
]

NAVIGATION_PATTERNS = [
    r"^(?:(?:hay|hãy)\s+)?(?:cho\s+robot\s+)?(?:di\s+den|di\s+toi|den|toi|go\s+to|move\s+to)\s+(?:diem\s+|point\s+)?(.+)$",
    r"^(?:(?:hay|hãy)\s+)?(?:cho\s+robot\s+)?di\s+qua\s+(.+)$",
]

WAYPOINT_SEPARATORS = re.compile(r"\s*(?:,|va|and)\s*")


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_text(text: str) -> str:
    value = strip_accents((text or "").strip().lower())
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"[^a-z0-9\s,]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    candidate = normalize_text(phrase)
    if not candidate:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])", normalized_text) is not None


def _build_match(
    *,
    source: str,
    tool: str,
    arguments: Dict[str, Any],
    matched_phrase: str,
    score: tuple[int, int],
    intent: str,
) -> Dict[str, Any]:
    return {
        "source": source,
        "tool": tool,
        "arguments": arguments,
        "matched_phrase": matched_phrase,
        "score": score,
        "intent": intent,
    }


def _resolve_keyword_commands(normalized_text: str) -> List[Dict[str, Any]]:
    matches: list[Dict[str, Any]] = []

    for spec in COMMAND_SPECS:
        for phrase in spec["phrases"]:
            normalized_phrase = normalize_text(phrase)
            if not normalized_phrase:
                continue
            if _contains_phrase(normalized_text, normalized_phrase):
                matches.append(
                    _build_match(
                        source="keyword",
                        tool=spec["tool"],
                        arguments=dict(spec["arguments"]),
                        matched_phrase=normalized_phrase,
                        score=(len(normalized_phrase.split()), len(normalized_phrase)),
                        intent="robot_control",
                    )
                )
    return matches


def _normalize_point_token(token: str) -> str:
    value = normalize_text(token).upper()
    value = re.sub(r"^(DIEM|POINT)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", "_", value).strip("_")
    return value


def extract_waypoints(text: str) -> List[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    for phrase in STOP_PHRASES:
        if _contains_phrase(normalized, phrase):
            return []

    raw_points = None
    for pattern in NAVIGATION_PATTERNS:
        match = re.match(pattern, normalized, re.IGNORECASE)
        if match:
            raw_points = match.group(1).strip()
            break

    if not raw_points:
        return []

    points: List[str] = []
    for item in WAYPOINT_SEPARATORS.split(raw_points):
        point = _normalize_point_token(item)
        if point:
            points.append(point)

    deduped: List[str] = []
    for point in points:
        if point not in deduped:
            deduped.append(point)
    return deduped


def _resolve_navigation_matches(text: str, normalized: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []

    for phrase in STOP_PHRASES:
        if _contains_phrase(normalized, phrase):
            matches.append(
                _build_match(
                    source="stop_phrase",
                    tool="stop_navigation",
                    arguments={},
                    matched_phrase=phrase,
                    score=(3, len(phrase)),
                    intent="navigation",
                )
            )

    points = extract_waypoints(text)
    if points:
        if len(points) == 1:
            matches.append(
                _build_match(
                    source="navigation_pattern",
                    tool="go_to_point",
                    arguments={"name": points[0]},
                    matched_phrase=points[0],
                    score=(4, len(points[0])),
                    intent="navigation",
                )
            )
        else:
            matches.append(
                _build_match(
                    source="navigation_pattern",
                    tool="goto_waypoints",
                    arguments={"points": points},
                    matched_phrase=",".join(points),
                    score=(4, len(points)),
                    intent="navigation",
                )
            )

    return matches


def _serialize_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for match in matches:
        serialized.append(
            {
                "source": match["source"],
                "tool": match["tool"],
                "arguments": match["arguments"],
                "matched_phrase": match["matched_phrase"],
                "intent": match["intent"],
            }
        )
    return serialized


def _pick_unambiguous_match(normalized: str, matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not matches:
        raise ValueError("Khong map duoc text command.")

    matches.sort(key=lambda item: item["score"], reverse=True)
    top = matches[0]
    top_score = top["score"]
    top_matches = [match for match in matches if match["score"] == top_score]

    distinct_top_commands = {
        (match["tool"], json.dumps(match["arguments"], sort_keys=True), match["intent"])
        for match in top_matches
    }
    if len(distinct_top_commands) > 1:
        raise AmbiguousCommandError(
            "Cau lenh mo ho, khop nhieu hanh dong cung muc uu tien. Hay noi ro hon.",
            normalized_text=normalized,
            matches=_serialize_matches(top_matches),
        )

    intents = {match["intent"] for match in matches}
    if len(intents) > 1:
        raise AmbiguousCommandError(
            "Cau lenh dang tron nhieu intent dieu khien. Hay tach thanh tung lenh rieng.",
            normalized_text=normalized,
            matches=_serialize_matches(matches),
        )

    return top


def map_text_to_tool(text: str) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    normalized = normalize_text(text)
    if not normalized:
        raise ValueError("Khong map duoc lenh rong.")

    navigation_matches = _resolve_navigation_matches(text, normalized)
    keyword_matches = _resolve_keyword_commands(normalized)
    chosen_match = _pick_unambiguous_match(normalized, [*navigation_matches, *keyword_matches])

    return chosen_match["tool"], chosen_match["arguments"], {
        "intent": chosen_match["intent"],
        "matched_phrase": chosen_match["matched_phrase"],
        "normalized_text": normalized,
        "source": chosen_match["source"],
        "candidate_matches": _serialize_matches([*navigation_matches, *keyword_matches]),
    }


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
        raise ValueError(f"Robot addr khong hop le: {addr}")

    base_url = f"{scheme}://{host}:{port}"
    return host, str(port), base_url


def build_mcp_server_script_path() -> str:
    base_dir = Path(settings.BASE_DIR)
    script_path = base_dir / "control" / "services" / "robot_mcp_server.py"

    if not script_path.exists():
        raise FileNotFoundError(f"Khong tim thay MCP server script: {script_path}")

    return str(script_path)


async def _call_mcp_tool(
    robot_addr: str,
    text: str,
    tool_name: str,
    arguments: Dict[str, Any],
    mapping: Dict[str, Any],
) -> Dict[str, Any]:
    host, port, base_url = parse_robot_addr(robot_addr)
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
        "MCP text command | robot=%s | text=%s | tool=%s | args=%s | matched=%s",
        base_url,
        text,
        tool_name,
        arguments,
        mapping.get("matched_phrase"),
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
            "mapping": mapping,
            "content": payload,
            "raw": str(result),
        }


def execute_mcp_tool(
    *,
    robot_addr: str,
    text: str,
    tool_name: str,
    arguments: Dict[str, Any],
    mapping: Dict[str, Any],
) -> Dict[str, Any]:
    if not robot_addr:
        raise ValueError("robot_addr is required")
    if not tool_name:
        raise ValueError("tool_name is required")

    logger.info(
        "Executing planned MCP tool | tool=%s | args=%s | source=%s",
        tool_name,
        arguments,
        mapping.get("source"),
    )

    return asyncio.run(
        _call_mcp_tool(
            robot_addr=robot_addr,
            text=text,
            tool_name=tool_name,
            arguments=arguments,
            mapping=mapping,
        )
    )
