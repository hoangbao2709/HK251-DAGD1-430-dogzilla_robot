import threading
from typing import Dict, List, Optional
from .patrol_types import PatrolMission

_lock = threading.Lock()
_current_missions: Dict[str, PatrolMission] = {}
_history: Dict[str, List[PatrolMission]] = {}


def set_current_mission(robot_id: str, mission: Optional[PatrolMission]) -> None:
    with _lock:
        if mission is None:
            _current_missions.pop(robot_id, None)
        else:
            _current_missions[robot_id] = mission


def get_current_mission(robot_id: str) -> Optional[PatrolMission]:
    with _lock:
        return _current_missions.get(robot_id)


def append_history(robot_id: str, mission: PatrolMission) -> None:
    with _lock:
        if robot_id not in _history:
            _history[robot_id] = []
        _history[robot_id].append(mission)


def get_history(robot_id: str) -> List[PatrolMission]:
    with _lock:
        return list(_history.get(robot_id, []))