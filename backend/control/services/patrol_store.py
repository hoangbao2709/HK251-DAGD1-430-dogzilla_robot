import threading
import datetime
from typing import Dict, List, Optional

from ..models import PatrolHistory, Robot
from .patrol_types import PatrolMission, PatrolPointResult

_lock = threading.Lock()
_current_missions: Dict[str, PatrolMission] = {}


def set_current_mission(robot_id: str, mission: Optional[PatrolMission]) -> None:
    with _lock:
        if mission is None:
            _current_missions.pop(robot_id, None)
        else:
            _current_missions[robot_id] = mission


def get_current_mission(robot_id: str) -> Optional[PatrolMission]:
    with _lock:
        return _current_missions.get(robot_id)


def _point_result_to_dict(result: PatrolPointResult) -> dict:
    return {
        "point": result.point,
        "status": result.status,
        "attempts": result.attempts,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "reach_time_sec": result.reach_time_sec,
        "distance_on_finish": result.distance_on_finish,
        "message": result.message,
    }


def mission_to_payload(mission: PatrolMission) -> dict:
    return {
        "mission_id": mission.mission_id,
        "robot_id": mission.robot_id,
        "route_name": mission.route_name,
        "points": mission.points,
        "wait_sec_per_point": mission.wait_sec_per_point,
        "max_retry_per_point": mission.max_retry_per_point,
        "skip_on_fail": mission.skip_on_fail,
        "status": mission.status,
        "current_index": mission.current_index,
        "started_at": mission.started_at,
        "finished_at": mission.finished_at,
        "total_distance_m": mission.total_distance_m,
        "cpu_samples": mission.cpu_samples,
        "battery_samples": mission.battery_samples,
        "temperature_samples": mission.temperature_samples,
        "ram_samples": mission.ram_samples,
        "results": [_point_result_to_dict(result) for result in mission.results],
    }


def payload_to_mission(payload: dict) -> PatrolMission:
    mission = PatrolMission(
        mission_id=str(payload.get("mission_id") or ""),
        robot_id=str(payload.get("robot_id") or ""),
        route_name=str(payload.get("route_name") or ""),
        points=list(payload.get("points") or []),
        wait_sec_per_point=int(payload.get("wait_sec_per_point") or 3),
        max_retry_per_point=int(payload.get("max_retry_per_point") or 1),
        skip_on_fail=bool(payload.get("skip_on_fail", True)),
        status=str(payload.get("status") or "IDLE"),
        current_index=int(payload.get("current_index") or 0),
        started_at=float(payload.get("started_at") or 0.0),
        finished_at=payload.get("finished_at"),
        total_distance_m=payload.get("total_distance_m"),
        cpu_samples=list(payload.get("cpu_samples") or []),
        battery_samples=list(payload.get("battery_samples") or []),
        temperature_samples=list(payload.get("temperature_samples") or []),
        ram_samples=list(payload.get("ram_samples") or []),
    )
    mission.results = [
        PatrolPointResult(
            point=str(item.get("point") or ""),
            status=str(item.get("status") or "PENDING"),
            attempts=int(item.get("attempts") or 0),
            started_at=item.get("started_at"),
            finished_at=item.get("finished_at"),
            reach_time_sec=item.get("reach_time_sec"),
            distance_on_finish=item.get("distance_on_finish"),
            message=str(item.get("message") or ""),
        )
        for item in payload.get("results") or []
        if isinstance(item, dict)
    ]
    return mission


def append_history(robot_id: str, mission: PatrolMission) -> None:
    payload = mission_to_payload(mission)
    robot, _ = Robot.objects.get_or_create(
        pk=robot_id,
        defaults={
            "name": robot_id.replace("-", " ").title(),
        },
    )
    PatrolHistory.objects.update_or_create(
        mission_id=mission.mission_id,
        defaults={
            "robot": robot,
            "route_name": mission.route_name,
            "status": mission.status,
            "started_at": mission.started_at,
            "finished_at": mission.finished_at,
            "total_distance_m": mission.total_distance_m,
            "payload": payload,
            "cpu_samples": mission.cpu_samples,
            "battery_samples": mission.battery_samples,
            "temperature_samples": mission.temperature_samples,
            "ram_samples": mission.ram_samples,
        },
    )


def get_history(robot_id: str, date_filter: str | None = None) -> List[PatrolMission]:
    records = PatrolHistory.objects.filter(
        robot_id=robot_id
    ).order_by("-finished_at", "-started_at")

    if date_filter == "all":
        today = None
    elif date_filter == "today" or not date_filter:
        today = datetime.date.today()
    else:
        try:
            today = datetime.datetime.strptime(date_filter, "%Y-%m-%d").date()
        except ValueError:
            today = datetime.date.today()

    if today:
        start_ts = datetime.datetime.combine(today, datetime.time.min).timestamp()
        end_ts   = datetime.datetime.combine(today, datetime.time.max).timestamp()
        records = records.filter(
            started_at__gte=start_ts,
            started_at__lte=end_ts,
        )

    return [payload_to_mission(record.payload) for record in records]
