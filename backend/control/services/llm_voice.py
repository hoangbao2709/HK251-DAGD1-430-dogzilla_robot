from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from openai import OpenAI


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

SYSTEM_PROMPT = """
You are a robot voice assistant and command planner.

Convert Vietnamese or English natural language robot commands into JSON tool calls.
For normal daily conversation, answer naturally in Vietnamese using reply_text and return no actions.

Return ONLY valid JSON.
Do not explain.
Do not use markdown.

Allowed tools:

1. go_to_point
Arguments:
{"name": "A"}

2. goto_waypoints
Arguments:
{"points": ["A", "B", "C"]}

3. stop_navigation
Arguments:
{}

4. reset_robot
Arguments:
{}

5. rotation
Arguments:
{}

6. set_posture
Arguments:
{"name": "Stand_Up"}

Allowed posture names:
- Stand_Up
- Lie_Down
- Crawl
- Squat
- Sit_Down

7. play_behavior
Arguments:
{"name": "Handshake"}

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

Examples:
- "hãy đi đến điểm A" -> {"actions":[{"tool":"go_to_point","arguments":{"name":"A"}}]}
- "đi qua A B C" -> {"actions":[{"tool":"goto_waypoints","arguments":{"points":["A","B","C"]}}]}
- "đứng lên" -> {"actions":[{"tool":"set_posture","arguments":{"name":"Stand_Up"}}]}
- "nằm xuống" -> {"actions":[{"tool":"set_posture","arguments":{"name":"Lie_Down"}}]}
- "bắt tay" -> {"actions":[{"tool":"play_behavior","arguments":{"name":"Handshake"}}]}
- "vẫy tay" -> {"actions":[{"tool":"play_behavior","arguments":{"name":"Wave_Hand"}}]}
- "dừng lại" -> {"actions":[{"tool":"stop_navigation","arguments":{}}]}

Output format:
{
  "actions": [
    {
      "tool": "tool_name",
      "arguments": {}
    }
  ],
  "reply_text": "short Vietnamese response for the user"
}
Important:
Your response must be a JSON object only.
Start with { and end with }.
Never return empty content.
Never return natural language.
Rules:
- Use only allowed tools.
- Use only allowed posture names.
- Use only allowed behavior names.
- Convert point names to uppercase.
- If there are multiple actions, return them in spoken order.
- If the user asks a normal non-robot question, return {"actions": [], "reply_text": "..."}.
- If the user asks for real-time information you cannot know, say you cannot check live data from here and suggest checking a reliable source.
- If unclear, return {"actions": [], "reply_text": "Em chua hieu ro y anh. Anh noi lai cu the hon duoc khong?"}.
"""


def _get_client() -> OpenAI:
    api_key = str(getattr(settings, "OPENROUTER_API_KEY", "") or "").strip()
    if not api_key:
        raise ValueError("Thiếu OPENROUTER_API_KEY trong settings/.env")

    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )


def _extract_json_object(content: str) -> dict[str, Any]:
    content = (content or "").strip()
    if not content:
        raise ValueError("LLM returned empty response")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    end = content.rfind("}")

    if start < 0 or end < 0 or end <= start:
        raise ValueError("LLM response does not contain JSON object")

    return json.loads(content[start : end + 1])


def _normalize_action(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        raise ValueError("Action must be object")

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

        points = []
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
    if not isinstance(actions, list):
        raise ValueError("LLM plan thiếu actions list")

    max_actions = int(getattr(settings, "LLM_MAX_ACTIONS", 5) or 5)

    reply_text = str(plan.get("reply_text") or "").strip()

    return {
        "actions": [
            _normalize_action(action)
            for action in actions[:max_actions]
        ],
        "reply_text": reply_text,
    }


def map_text_with_openrouter(text: str) -> dict[str, Any]:
    client = _get_client()
    model = str(
        getattr(settings, "OPENROUTER_MODEL", "openai/gpt-4.1-mini")
        or "openai/gpt-4.1-mini"
    )

    kwargs = {
        "model": model,
        "temperature": 0,
        "max_tokens": 512,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    }

    # Chỉ bật JSON mode cho model không phải router/free.
    # Một số free model trả content rỗng khi ép response_format.
    if model != "openrouter/free":
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)

    content = response.choices[0].message.content or ""
    raw_plan = _extract_json_object(content)
    return validate_plan(raw_plan)
