from __future__ import annotations

from typing import Any

from ..models import Robot, VoiceConversationMetric


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def record_voice_conversation_metric(
    robot_id: str,
    *,
    input_text: str,
    robot_addr: str = "",
    planner_source: str = "",
    success: bool,
    dry_run: bool,
    response_time_ms: float | None,
    reply_text: str = "",
    llm_error: str = "",
    error_code: str = "",
    plan_json: dict[str, Any] | None = None,
    result_json: dict[str, Any] | None = None,
    results_json: list[Any] | None = None,
    response_json: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> VoiceConversationMetric:
    robot, _ = Robot.objects.get_or_create(
        pk=robot_id,
        defaults={"name": robot_id.replace("-", " ").title()},
    )

    return VoiceConversationMetric.objects.create(
        robot=robot,
        input_text=str(input_text or ""),
        robot_addr=str(robot_addr or ""),
        planner_source=str(planner_source or ""),
        success=bool(success),
        dry_run=bool(dry_run),
        response_time_ms=_as_float(response_time_ms),
        reply_text=str(reply_text or ""),
        llm_error=str(llm_error or ""),
        error_code=str(error_code or ""),
        plan_json=plan_json or {},
        result_json=result_json,
        results_json=results_json or [],
        response_json=response_json or {},
        payload=payload or {},
    )
