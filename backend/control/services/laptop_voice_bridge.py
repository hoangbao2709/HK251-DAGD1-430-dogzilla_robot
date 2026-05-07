from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("LaptopVoiceBridge")

app = Flask(__name__, static_folder="static", static_url_path="/static")

SERVER_SCRIPT = str(BASE_DIR / "robot_mcp_server.py")

CHILD_ENV = {
    "ROBOT_IP": os.getenv("ROBOT_IP", "127.0.0.1"),
    "ROBOT_PORT": os.getenv("ROBOT_PORT", "9000"),
    "ROBOT_TIMEOUT": os.getenv("ROBOT_TIMEOUT", "5"),
    "MAP_SERVER_PORT": os.getenv("MAP_SERVER_PORT", "8080"),
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
}

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini").strip()

openrouter_client = OpenAI(
    api_key=OPENROUTER_API_KEY or "missing-key",
    base_url="https://openrouter.ai/api/v1",
)

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

ALLOWED_TOOLS = {
    "go_to_point",
    "goto_waypoints",
    "stop_navigation",
    "reset_robot",
    "rotation",
    "set_posture",
    "play_behavior",
}

MAX_ACTIONS = int(os.getenv("LLM_MAX_ACTIONS", "5"))


SYSTEM_PROMPT = """
You are a robot command planner.

Your task:
Convert Vietnamese or English natural language commands into MCP robot tool calls.

Return ONLY valid JSON.
Do not explain.
Do not use markdown.
Do not include extra text.

Allowed tools:

1. go_to_point
Arguments:
{
  "name": "A"
}

Use this when the user wants the robot to go to one saved point.
Examples:
- "đi tới điểm A"
- "robot qua A"
- "đến vị trí B"

2. goto_waypoints
Arguments:
{
  "points": ["A", "B", "C"]
}

Use this when the user wants the robot to visit multiple saved points in order.
Examples:
- "đi qua A B C"
- "tuần tra qua điểm A rồi B rồi C"
- "đi tới A sau đó tới B"

3. stop_navigation
Arguments:
{}

Use this when the user asks the robot to stop moving or cancel navigation.
Examples:
- "dừng lại"
- "dừng điều hướng"
- "hủy di chuyển"
- "stop"

4. reset_robot
Arguments:
{}

Use this when the user asks to reset the robot.
Examples:
- "reset"
- "khởi động lại"
- "đặt lại robot"

5. rotation
Arguments:
{}

Use this when the user asks the robot to rotate/spin.
Examples:
- "xoay tròn"
- "quay tròn"
- "rotation"

6. set_posture
Arguments:
{
  "name": "Stand_Up"
}

Allowed posture names:
- Stand_Up
- Lie_Down
- Crawl
- Squat
- Sit_Down

Meaning:
- "đứng lên" -> Stand_Up
- "nằm xuống" -> Lie_Down
- "bò" -> Crawl
- "ngồi xuống", "ngồi xổm" -> Squat or Sit_Down depending on wording
- "sit down" -> Sit_Down
- "squat" -> Squat

7. play_behavior
Arguments:
{
  "name": "Handshake"
}

Allowed behavior names:
- Turn_Around
- Mark_Time
- Turn_Roll
- Turn_Pitch
- Turn_Yaw
- 3_Axis
- Pee
- Wave_Hand
- Stretch
- Wave_Body
- Swing
- Pray
- Seek
- Handshake
- Play_Ball

Meaning:
- "bắt tay" -> Handshake
- "vẫy tay" -> Wave_Hand
- "chơi bóng" -> Play_Ball
- "cầu nguyện" -> Pray
- "duỗi người", "vươn mình" -> Stretch
- "quay vòng" -> Turn_Around
- "giậm chân tại chỗ" -> Mark_Time
- "lắc người" -> Wave_Body or Swing depending on wording
- "tìm kiếm" -> Seek

Output format:
{
  "actions": [
    {
      "tool": "tool_name",
      "arguments": {}
    }
  ]
}

Rules:
- Use only allowed tools.
- Use only allowed posture names.
- Use only allowed behavior names.
- Convert point names to uppercase.
- If the user asks multiple actions, return them in the spoken order.
- If the command is unclear, return:
{
  "actions": []
}
"""


# ---------------------------------------------------------------------
# Fallback parser cũ
# Giữ lại để khi OpenRouter lỗi thì hệ thống vẫn chạy được.
# ---------------------------------------------------------------------

POSTURE_KEYWORDS = {
    "Lie_Down": ["nam xuong", "nằm xuống", "lie down"],
    "Stand_Up": ["dung len", "đứng lên", "stand up"],
    "Crawl": ["bo", "bò", "crawl"],
    "Squat": ["ngoi xuong", "ngồi xuống", "ngoi xom", "ngồi xổm", "squat"],
    "Sit_Down": ["ngoi", "ngồi", "sit down"],
}

BEHAVIOR_KEYWORDS = {
    "Turn_Around": ["xoay vong", "quay vong", "quay vòng", "turn around"],
    "Mark_Time": ["di bo tai cho", "giậm chân tại chỗ", "giam chan tai cho", "mark time"],
    "Turn_Roll": ["roll", "lăn"],
    "Turn_Pitch": ["pitch", "gật"],
    "Turn_Yaw": ["yaw", "xoay dau", "xoay đầu"],
    "3_Axis": ["3 truc", "ba trục", "ba truc", "3 axis"],
    "Pee": ["pee", "đi vệ sinh giả", "di ve sinh gia"],
    "Wave_Hand": ["vay tay", "vẫy tay", "wave hand"],
    "Stretch": ["vuon minh", "vươn mình", "duoi nguoi", "duỗi người", "stretch"],
    "Wave_Body": ["lac nguoi", "lắc người", "wave body"],
    "Swing": ["du dua", "đung đưa", "swing"],
    "Pray": ["cau nguyen", "cầu nguyện", "pray"],
    "Seek": ["tim kiem", "tìm kiếm", "seek"],
    "Handshake": ["bat tay", "bắt tay", "handshake"],
    "Play_Ball": ["choi bong", "chơi bóng", "play ball"],
}

DIRECT_COMMANDS = {
    "reset": ["reset", "dat lai", "đặt lại", "ve mac dinh", "về mặc định", "khoi dong lai", "khởi động lại"],
    "rotation": ["rotation", "xoay", "quay tron", "quay tròn"],
}


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_text(text: str) -> str:
    text = strip_accents((text or "").lower()).replace("_", " ")
    text = re.sub(r"[^a-z0-9\s,]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_first_match(normalized: str, mapping: dict[str, list[str]]) -> str | None:
    padded = f" {normalized} "
    for target, keywords in mapping.items():
        for keyword in keywords:
            candidate = normalize_text(keyword)
            if f" {candidate} " in padded:
                return target
    return None


def parse_navigation_command(text: str) -> dict[str, Any] | None:
    normalized = normalize_text(text)

    if (
        "dung di chuyen" in normalized
        or "dung lai" in normalized
        or "dung dieu huong" in normalized
        or "huy dieu huong" in normalized
        or "stop navigation" in normalized
        or normalized == "stop"
    ):
        return {
            "tool": "stop_navigation",
            "arguments": {},
            "matched": "stop_navigation",
            "normalized_text": normalized,
            "intent": "navigation",
        }

    m = re.search(r"\b(di toi|di den|den|toi|qua)\s+(diem\s+)?([a-z])\b", normalized)
    if m:
        point = m.group(3).upper()
        return {
            "tool": "go_to_point",
            "arguments": {"name": point},
            "matched": f"point_{point}",
            "normalized_text": normalized,
            "intent": "navigation",
        }

    m = re.search(r"\b(di qua|toi qua|tuan tra qua|di toi|di den)\s+(.+)$", normalized)
    if m:
        tail = m.group(2)
        points = [p.upper() for p in re.findall(r"\b[a-z]\b", tail)]
        deduped = []
        for p in points:
            if p not in deduped:
                deduped.append(p)

        if len(deduped) >= 2:
            return {
                "tool": "goto_waypoints",
                "arguments": {"points": deduped},
                "matched": deduped,
                "normalized_text": normalized,
                "intent": "navigation",
            }

    return None


def map_text_to_mcp(text: str) -> dict[str, Any]:
    normalized = normalize_text(text)
    if not normalized:
        raise ValueError("Không nhận được nội dung giọng nói.")

    nav = parse_navigation_command(text)
    if nav:
        return nav

    direct = find_first_match(normalized, DIRECT_COMMANDS)
    if direct == "reset":
        return {
            "tool": "reset_robot",
            "arguments": {},
            "matched": "reset",
            "normalized_text": normalized,
        }

    if direct == "rotation":
        return {
            "tool": "rotation",
            "arguments": {},
            "matched": "rotation",
            "normalized_text": normalized,
        }

    posture = find_first_match(normalized, POSTURE_KEYWORDS)
    if posture:
        return {
            "tool": "set_posture",
            "arguments": {"name": posture},
            "matched": posture,
            "normalized_text": normalized,
        }

    behavior = find_first_match(normalized, BEHAVIOR_KEYWORDS)
    if behavior:
        return {
            "tool": "play_behavior",
            "arguments": {"name": behavior},
            "matched": behavior,
            "normalized_text": normalized,
        }

    raise ValueError(f"Chưa map được câu lệnh: '{text}'")


# ---------------------------------------------------------------------
# OpenRouter LLM planner
# ---------------------------------------------------------------------

def _extract_json_object(content: str) -> dict[str, Any]:
    """
    OpenRouter thường trả JSON đúng do response_format=json_object.
    Hàm này vẫn có fallback để tránh lỗi nếu model bọc thêm text.
    """
    content = (content or "").strip()
    if not content:
        raise ValueError("LLM returned empty response")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response does not contain a JSON object")

    return json.loads(content[start : end + 1])


def _normalize_action(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        raise ValueError("Action must be an object")

    tool = str(action.get("tool") or "").strip()
    arguments = action.get("arguments") or {}

    if tool not in ALLOWED_TOOLS:
        raise ValueError(f"Tool không được phép: {tool}")

    if not isinstance(arguments, dict):
        raise ValueError(f"Arguments của {tool} phải là object")

    if tool == "go_to_point":
        name = str(arguments.get("name") or "").strip().upper()
        if not name:
            raise ValueError("go_to_point cần arguments.name")
        arguments = {"name": name}

    elif tool == "goto_waypoints":
        raw_points = arguments.get("points") or []
        if not isinstance(raw_points, list):
            raise ValueError("goto_waypoints cần arguments.points là list")

        points: list[str] = []
        for point in raw_points:
            value = str(point).strip().upper()
            if value and value not in points:
                points.append(value)

        if not points:
            raise ValueError("goto_waypoints cần ít nhất 1 điểm")

        arguments = {"points": points}

    elif tool == "set_posture":
        name = str(arguments.get("name") or "").strip()
        if name not in POSTURES:
            raise ValueError(f"Posture không hợp lệ: {name}")
        arguments = {"name": name}

    elif tool == "play_behavior":
        name = str(arguments.get("name") or "").strip()
        if name not in BEHAVIORS:
            raise ValueError(f"Behavior không hợp lệ: {name}")
        arguments = {"name": name}

    else:
        arguments = {}

    return {
        "tool": tool,
        "arguments": arguments,
    }


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("LLM plan phải là object")

    actions = plan.get("actions")
    if actions is None:
        raise ValueError("LLM plan thiếu actions")

    if not isinstance(actions, list):
        raise ValueError("actions phải là list")

    normalized_actions: list[dict[str, Any]] = []

    for action in actions[:MAX_ACTIONS]:
        normalized_actions.append(_normalize_action(action))

    return {
        "actions": normalized_actions,
    }


def map_text_with_llm(text: str) -> dict[str, Any]:
    if not OPENROUTER_API_KEY:
        raise ValueError("Thiếu OPENROUTER_API_KEY trong .env")

    response = openrouter_client.chat.completions.create(
        model=OPENROUTER_MODEL,
        temperature=0,
        max_tokens=512,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    )

    content = response.choices[0].message.content or ""
    raw_plan = _extract_json_object(content)
    return validate_plan(raw_plan)


def map_text_to_plan(text: str) -> dict[str, Any]:
    """
    Ưu tiên OpenRouter.
    Nếu OpenRouter lỗi thì fallback về parser keyword cũ.
    """
    try:
        plan = map_text_with_llm(text)
        if plan.get("actions"):
            return {
                "source": "openrouter",
                "plan": plan,
            }

        raise ValueError("LLM không chọn action nào")
    except Exception as llm_error:
        logger.warning("OpenRouter planner failed, fallback to keyword parser: %s", llm_error)

        old = map_text_to_mcp(text)
        return {
            "source": "fallback_keyword",
            "llm_error": str(llm_error),
            "plan": {
                "actions": [
                    {
                        "tool": old["tool"],
                        "arguments": old.get("arguments", {}),
                    }
                ]
            },
        }


# ---------------------------------------------------------------------
# MCP caller
# ---------------------------------------------------------------------

async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    transport = StdioTransport(
        command="python",
        args=[SERVER_SCRIPT],
        env=CHILD_ENV,
        cwd=str(BASE_DIR),
        keep_alive=False,
    )

    client = Client(transport)

    async with client:
        result = await client.call_tool(tool_name, arguments)

        if hasattr(result, "data"):
            return result.data

        if hasattr(result, "structured_content"):
            return result.structured_content

        return str(result)


async def execute_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for action in plan.get("actions", []):
        normalized = _normalize_action(action)
        tool_name = normalized["tool"]
        arguments = normalized["arguments"]

        result = await call_mcp_tool(tool_name, arguments)

        results.append(
            {
                "tool": tool_name,
                "arguments": arguments,
                "result": result,
            }
        )

    return results


# ---------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------

@app.get("/")
def index():
    # Nếu voice_control.html nằm cùng thư mục với file Python thì dùng BASE_DIR.
    # Nếu bạn để trong static/ thì đổi lại thành send_from_directory(app.static_folder, "voice_control.html").
    return send_from_directory(BASE_DIR, "voice_control.html")


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "robot_server": SERVER_SCRIPT,
            "robot_ip": CHILD_ENV["ROBOT_IP"],
            "robot_port": CHILD_ENV["ROBOT_PORT"],
            "map_server_port": CHILD_ENV["MAP_SERVER_PORT"],
            "openrouter_configured": bool(OPENROUTER_API_KEY),
            "openrouter_model": OPENROUTER_MODEL,
        }
    )


@app.post("/api/text-command")
def text_command():
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    dry_run = bool(payload.get("dry_run", False))

    if not text:
        return jsonify({"success": False, "error": "Thiếu trường 'text'."}), 400

    try:
        mapped = map_text_to_plan(text)
        plan = mapped["plan"]

        if dry_run:
            return jsonify(
                {
                    "success": True,
                    "dry_run": True,
                    "input_text": text,
                    "planner_source": mapped.get("source"),
                    "llm_error": mapped.get("llm_error"),
                    "plan": plan,
                }
            )

        results = asyncio.run(execute_plan(plan))

        return jsonify(
            {
                "success": True,
                "input_text": text,
                "planner_source": mapped.get("source"),
                "llm_error": mapped.get("llm_error"),
                "plan": plan,
                "results": results,
            }
        )

    except ValueError as exc:
        return jsonify({"success": False, "input_text": text, "error": str(exc)}), 400

    except Exception as exc:
        logger.exception("Failed to execute command")
        return jsonify({"success": False, "input_text": text, "error": str(exc)}), 500


if __name__ == "__main__":
    host = os.getenv("VOICE_BRIDGE_HOST", "0.0.0.0")
    port = int(os.getenv("VOICE_BRIDGE_PORT", "8765"))
    app.run(host=host, port=port, debug=False)