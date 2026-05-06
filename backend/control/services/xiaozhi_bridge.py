from __future__ import annotations

from typing import Any


def build_bridge_response_text(result: dict[str, Any]) -> str:
    tool_name = str(result.get("tool") or "")
    arguments = result.get("arguments") or {}

    if tool_name == "go_to_point":
        point_name = str(arguments.get("name") or "").strip()
        return f"Em \u0111\u00e3 nh\u1eadn l\u1ec7nh. Robot \u0111ang b\u1eaft \u0111\u1ea7u di chuy\u1ec3n \u0111\u1ebfn \u0111i\u1ec3m {point_name}."

    if tool_name == "goto_waypoints":
        points = arguments.get("points") or []
        return f"Em \u0111\u00e3 nh\u1eadn l\u1ec7nh. Robot s\u1ebd l\u1ea7n l\u01b0\u1ee3t di chuy\u1ec3n qua c\u00e1c \u0111i\u1ec3m: {', '.join(points)}."

    if tool_name == "stop_navigation":
        return "Em \u0111\u00e3 nh\u1eadn l\u1ec7nh. Robot \u0111ang d\u1eebng \u0111i\u1ec1u h\u01b0\u1edbng v\u00e0 x\u00f3a \u0111\u01b0\u1eddng \u0111i hi\u1ec7n t\u1ea1i."

    if tool_name == "reset_robot":
        return "Em \u0111\u00e3 nh\u1eadn l\u1ec7nh. Robot \u0111ang \u0111\u01b0\u1ee3c \u0111\u1eb7t l\u1ea1i v\u1ec1 tr\u1ea1ng th\u00e1i m\u1eb7c \u0111\u1ecbnh."

    if tool_name == "rotation":
        return "Em \u0111\u00e3 nh\u1eadn l\u1ec7nh. Robot \u0111ang th\u1ef1c hi\u1ec7n thao t\u00e1c xoay."

    if tool_name == "set_posture":
        posture_name = str(arguments.get("name") or "").replace("_", " ")
        return f"Em \u0111\u00e3 nh\u1eadn l\u1ec7nh. Robot \u0111ang chuy\u1ec3n sang t\u01b0 th\u1ebf {posture_name}."

    if tool_name == "play_behavior":
        behavior_name = str(arguments.get("name") or "").replace("_", " ")
        return f"Em \u0111\u00e3 nh\u1eadn l\u1ec7nh. Robot \u0111ang th\u1ef1c hi\u1ec7n \u0111\u1ed9ng t\u00e1c {behavior_name}."

    return f"Em \u0111\u00e3 nh\u1eadn l\u1ec7nh. Robot \u0111ang th\u1ef1c hi\u1ec7n thao t\u00e1c {tool_name}."
