from dataclasses import dataclass, field
from typing import List, Optional
import time


@dataclass
class PatrolPointResult:
    point: str
    status: str = "PENDING"
    attempts: int = 0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    reach_time_sec: Optional[float] = None
    distance_on_finish: Optional[float] = None
    message: str = ""


@dataclass
class PatrolMission:
    mission_id: str
    robot_id: str
    route_name: str
    points: List[str]
    wait_sec_per_point: int = 3
    max_retry_per_point: int = 1
    skip_on_fail: bool = True
    status: str = "IDLE"
    current_index: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    total_distance_m: Optional[float] = None
    results: List[PatrolPointResult] = field(default_factory=list)
