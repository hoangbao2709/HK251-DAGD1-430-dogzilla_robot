from __future__ import annotations

from typing import Any


def build_bridge_response_text(result: dict[str, Any]) -> str:
    tool_name = str(result.get("tool") or "")
    arguments = result.get("arguments") or {}

    if tool_name == "goto_point":
        return f"Da gui lenh di toi diem {arguments.get('name', '')}."

    if tool_name == "goto_waypoints":
        points = arguments.get("points") or []
        return f"Da bat dau lo trinh qua cac diem: {', '.join(points)}."

    if tool_name == "stop_navigation":
        return "Da gui lenh dung dieu huong."

    if tool_name == "reset_robot":
        return "Da gui lenh reset robot."

    if tool_name == "rotation":
        return "Da gui lenh xoay robot."

    if tool_name == "set_posture":
        return f"Da gui lenh doi tu the sang {arguments.get('name', '')}."

    if tool_name == "play_behavior":
        return f"Da gui lenh chay dong tac {arguments.get('name', '')}."

    return f"Da gui lenh {tool_name}."
