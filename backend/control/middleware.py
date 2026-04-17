import json
import re
import time
from typing import Any

from .models import ActionEvent, Robot


_CONTROL_PATH_RE = re.compile(r"^/control/api/robots/(?P<robot_id>[^/]+)/(?P<tail>.+)/?$")


def _ensure_robot(robot_id: str) -> Robot:
    robot, _ = Robot.objects.get_or_create(
        pk=robot_id,
        defaults={"name": robot_id.replace("-", " ").title()},
    )
    return robot


def _humanize_tail(tail: str) -> str:
    parts = [p for p in tail.split("/") if p]
    if not parts:
        return "Action"

    last = parts[-1].replace("-", " ")
    if len(parts) >= 2 and parts[-2] == "command":
        last = parts[-1].replace("_", " ")
    if len(parts) >= 2 and parts[-2] == "patrol":
        last = f"Patrol {parts[-1].replace('_', ' ').title()}"
    if parts[-1] == "lidar" and len(parts) >= 2 and parts[-2] == "command":
        last = "Lidar"
    return " ".join(word.capitalize() for word in last.split())


def _severity_for_status(status_code: int) -> str:
    if status_code >= 500:
        return ActionEvent.Severity.CRITICAL
    if status_code >= 400:
        return ActionEvent.Severity.WARNING
    return ActionEvent.Severity.INFO


class RobotActionEventMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)

        if request.method != "POST":
            return response

        match = _CONTROL_PATH_RE.match(request.path)
        if not match:
            return response

        robot_id = match.group("robot_id")
        tail = match.group("tail")
        status_code = getattr(response, "status_code", 200)

        payload: dict[str, Any] = {}
        try:
            if request.body:
                payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            payload = {}

        event_name = _humanize_tail(tail)
        if tail == "command/lidar" and payload.get("action"):
            event_name = f"Lidar {str(payload.get('action')).title()}"
        elif tail == "command/lidar/reset":
            event_name = "Lidar Reset"

        detail = ""
        data = getattr(response, "data", None)
        if isinstance(data, dict):
            detail = str(
                data.get("error")
                or data.get("detail")
                or data.get("log")
                or data.get("message")
                or ""
            )

        try:
            ActionEvent.objects.create(
                robot=_ensure_robot(robot_id),
                event=event_name,
                severity=_severity_for_status(status_code),
                duration_seconds=round(time.perf_counter() - started, 3),
                status=(
                    ActionEvent.Status.SUCCESS
                    if status_code < 400
                    else ActionEvent.Status.FAILED
                ),
                action=tail,
                payload=payload,
                detail=detail,
            )
        except Exception:
            # Logging must never block the control path.
            pass

        return response
