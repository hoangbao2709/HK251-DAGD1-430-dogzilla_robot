import math
import threading
import time
import uuid
from typing import Any, Optional

from .ros import ROSClient
from .patrol_store import (
    set_current_mission,
    get_current_mission,
    append_history,
)
from .patrol_types import PatrolMission, PatrolPointResult


class PatrolManager:
    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}
        self._stop_flags: dict[str, bool] = {}
        self._pause_flags: dict[str, bool] = {}
        self._lock = threading.Lock()
        self.tolerance_m = 0.35
        self.poll_interval_sec = 1.0
        self.point_timeout_sec = 120.0

    def start(
        self,
        robot_id: str,
        route_name: str,
        points: list[str],
        wait_sec_per_point: int = 3,
        max_retry_per_point: int = 1,
        skip_on_fail: bool = True,
    ) -> PatrolMission:
        with self._lock:
            t = self._threads.get(robot_id)
            if t and t.is_alive():
                raise RuntimeError(f"Robot {robot_id} already has a running patrol mission")

            mission = PatrolMission(
                mission_id=f"patrol_{uuid.uuid4().hex[:8]}",
                robot_id=robot_id,
                route_name=route_name,
                points=[p.strip().upper() for p in points if str(p).strip()],
                wait_sec_per_point=int(wait_sec_per_point),
                max_retry_per_point=int(max_retry_per_point),
                skip_on_fail=bool(skip_on_fail),
                status="RUNNING",
            )

            if not mission.points:
                raise RuntimeError("No valid patrol points provided")

            self._stop_flags[robot_id] = False
            self._pause_flags[robot_id] = False
            set_current_mission(robot_id, mission)

            thread = threading.Thread(
                target=self._run_patrol,
                args=(mission,),
                daemon=True,
                name=f"patrol_{robot_id}",
            )
            self._threads[robot_id] = thread
            thread.start()
            return mission

    def start_manual_goal(
        self,
        robot_id: str,
        x: float,
        y: float,
        yaw: float = 0.0,
        route_name: str = "manual_goal",
    ) -> PatrolMission:
        with self._lock:
            t = self._threads.get(robot_id)
            if t and t.is_alive():
                raise RuntimeError(f"Robot {robot_id} already has a running patrol mission")

            point_name = f"GOAL({float(x):.3f},{float(y):.3f})"
            mission = PatrolMission(
                mission_id=f"manual_{uuid.uuid4().hex[:8]}",
                robot_id=robot_id,
                route_name=route_name,
                points=[point_name],
                wait_sec_per_point=0,
                max_retry_per_point=0,
                skip_on_fail=False,
                status="RUNNING",
            )

            self._stop_flags[robot_id] = False
            self._pause_flags[robot_id] = False
            set_current_mission(robot_id, mission)

            thread = threading.Thread(
                target=self._run_manual_goal,
                args=(mission, float(x), float(y), float(yaw)),
                daemon=True,
                name=f"manual_goal_{robot_id}",
            )
            self._threads[robot_id] = thread
            thread.start()
            return mission

    def stop(self, robot_id: str) -> None:
        self._stop_flags[robot_id] = True
        try:
            ROSClient(robot_id).raw_control({"command": "stop"})
        except Exception:
            pass
        try:
            ROSClient(robot_id).clear_navigation()
        except Exception:
            pass

    def pause(self, robot_id: str) -> None:
        self._pause_flags[robot_id] = True

    def resume(self, robot_id: str) -> None:
        self._pause_flags[robot_id] = False

    def _is_stopped(self, robot_id: str) -> bool:
        return self._stop_flags.get(robot_id, False)

    def _is_paused(self, robot_id: str) -> bool:
        return self._pause_flags.get(robot_id, False)

    def _distance_to_point(self, robot_id: str, target_x: float, target_y: float) -> tuple[Optional[float], dict]:
        client = ROSClient(robot_id)
        state = client.get_slam_state_light()
        pose = state.get("pose") or {}

        if not pose.get("ok"):
            return None, state

        rx = float(pose["x"])
        ry = float(pose["y"])
        dist = math.hypot(target_x - rx, target_y - ry)
        return dist, state

    def _wait_until_reached(self, robot_id: str, target_x: float, target_y: float) -> tuple[bool, str, Optional[float]]:
        start = time.time()
        last_dist = None

        while True:
            if self._is_stopped(robot_id):
                return False, "mission stopped", last_dist

            while self._is_paused(robot_id):
                time.sleep(0.5)
                if self._is_stopped(robot_id):
                    return False, "mission stopped", last_dist

            try:
                dist, state = self._distance_to_point(robot_id, target_x, target_y)
                if dist is not None:
                    last_dist = dist
                    if dist <= self.tolerance_m:
                        return True, "reached", dist
            except Exception as e:
                pass

            if time.time() - start > self.point_timeout_sec:
                return False, "timeout waiting for point", last_dist

            time.sleep(self.poll_interval_sec)

    def _read_terminal_navigation_result(
        self,
        metrics: dict[str, Any],
        initial_mission_count: int,
    ) -> dict[str, Any] | None:
        current = metrics.get("current_mission") or {}
        status_value = str(current.get("status") or "").lower()
        if status_value in {"success", "failed", "aborted"}:
            return current

        missions = metrics.get("missions") or []
        if len(missions) > initial_mission_count and isinstance(missions[-1], dict):
            latest = missions[-1]
            latest_status = str(latest.get("status") or "").lower()
            if latest_status in {"success", "failed", "aborted"}:
                return latest

        return None

    def _run_manual_goal(self, mission: PatrolMission, target_x: float, target_y: float, yaw: float) -> None:
        robot_id = mission.robot_id
        point_result = PatrolPointResult(point=mission.points[0], status="RUNNING", attempts=1)
        point_result.started_at = time.time()
        mission.results.append(point_result)

        try:
            client = ROSClient(robot_id)
            try:
                before_metrics = client.get_navigation_metrics() or {}
                initial_mission_count = len(before_metrics.get("missions") or [])
            except Exception:
                initial_mission_count = 0

            send_result = client.set_goal_pose(target_x, target_y, yaw)
            point_result.message = send_result.get("message") or "goal sent"
            if not send_result.get("success", False):
                mission.status = "FAILED"
                point_result.status = "FAILED"
                point_result.finished_at = time.time()
                return

            start = time.time()
            last_dist = None
            terminal_result = None

            while True:
                if self._is_stopped(robot_id):
                    mission.status = "STOPPED"
                    point_result.status = "ABORTED"
                    point_result.message = "mission stopped"
                    break

                try:
                    metrics = client.get_navigation_metrics() or {}
                    terminal_result = self._read_terminal_navigation_result(metrics, initial_mission_count)
                    if terminal_result:
                        status_value = str(terminal_result.get("status") or "").lower()
                        point_result.message = str(
                            terminal_result.get("result") or terminal_result.get("message") or status_value
                        )
                        if status_value == "success":
                            mission.status = "DONE"
                            point_result.status = "SUCCESS"
                        elif status_value == "aborted":
                            mission.status = "STOPPED"
                            point_result.status = "ABORTED"
                        else:
                            mission.status = "FAILED"
                            point_result.status = "FAILED"
                        break
                except Exception:
                    pass

                try:
                    dist, _ = self._distance_to_point(robot_id, target_x, target_y)
                    if dist is not None:
                        last_dist = dist
                except Exception:
                    pass

                if time.time() - start > self.point_timeout_sec:
                    mission.status = "FAILED"
                    point_result.status = "FAILED"
                    point_result.message = "timeout waiting for manual goal"
                    break

                time.sleep(self.poll_interval_sec)

            point_result.finished_at = time.time()
            point_result.reach_time_sec = point_result.finished_at - point_result.started_at
            point_result.distance_on_finish = last_dist

            if terminal_result:
                try:
                    if terminal_result.get("duration_sec") is not None:
                        point_result.reach_time_sec = float(terminal_result["duration_sec"])
                    if terminal_result.get("final_goal_error_m") is not None:
                        point_result.distance_on_finish = float(terminal_result["final_goal_error_m"])
                except (TypeError, ValueError):
                    pass

        except Exception as e:
            mission.status = "FAILED"
            point_result.status = "FAILED"
            point_result.message = str(e)
            point_result.finished_at = time.time()
        finally:
            mission.finished_at = time.time()
            append_history(robot_id, mission)
            set_current_mission(robot_id, None)
            with self._lock:
                self._threads.pop(robot_id, None)
                self._stop_flags.pop(robot_id, None)
                self._pause_flags.pop(robot_id, None)

    def _run_patrol(self, mission: PatrolMission) -> None:
        robot_id = mission.robot_id

        try:
            client = ROSClient(robot_id)
            points_map = client.get_points() or {}

            consecutive_fail = 0

            for idx, point_name in enumerate(mission.points):
                if self._is_stopped(robot_id):
                    mission.status = "STOPPED"
                    break

                mission.current_index = idx
                point_result = PatrolPointResult(point=point_name)
                mission.results.append(point_result)

                point_info = points_map.get(point_name)
                if point_info is None:
                    point_result.status = "FAILED"
                    point_result.message = f"Point '{point_name}' not found"
                    consecutive_fail += 1
                    if not mission.skip_on_fail or consecutive_fail >= 2:
                        mission.status = "FAILED"
                        break
                    point_result.status = "SKIPPED"
                    continue

                target_x = float(point_info["x"])
                target_y = float(point_info["y"])

                success = False

                for attempt in range(1, mission.max_retry_per_point + 2):
                    if self._is_stopped(robot_id):
                        mission.status = "STOPPED"
                        point_result.status = "ABORTED"
                        point_result.message = "mission stopped"
                        point_result.finished_at = time.time()
                        break

                    point_result.attempts = attempt
                    point_result.status = "RUNNING"
                    point_result.started_at = time.time()

                    try:
                        client.go_to_point(point_name)
                    except Exception as e:
                        point_result.message = f"go_to_point failed: {e}"
                        continue

                    ok, message, final_dist = self._wait_until_reached(robot_id, target_x, target_y)
                    point_result.finished_at = time.time()
                    point_result.distance_on_finish = final_dist
                    point_result.message = message

                    if self._is_stopped(robot_id):
                        mission.status = "STOPPED"
                        point_result.status = "ABORTED"
                        point_result.message = message or "mission stopped"
                        break

                    if ok:
                        point_result.status = "SUCCESS"
                        point_result.reach_time_sec = point_result.finished_at - point_result.started_at
                        success = True
                        consecutive_fail = 0
                        wait_until = time.time() + mission.wait_sec_per_point
                        while time.time() < wait_until:
                            if self._is_stopped(robot_id):
                                mission.status = "STOPPED"
                                break
                            time.sleep(min(0.5, wait_until - time.time()))
                        break

                if self._is_stopped(robot_id) or mission.status == "STOPPED":
                    mission.status = "STOPPED"
                    if point_result.status == "RUNNING":
                        point_result.status = "ABORTED"
                        point_result.message = "mission stopped"
                    if point_result.finished_at is None:
                        point_result.finished_at = time.time()
                    break

                if not success:
                    point_result.status = "FAILED"
                    consecutive_fail += 1

                    if not mission.skip_on_fail or consecutive_fail >= 2:
                        mission.status = "FAILED"
                        break

                    point_result.status = "SKIPPED"

            if mission.status == "RUNNING":
                mission.status = "DONE"

        except Exception as e:
            mission.status = "FAILED"
        finally:
            mission.finished_at = time.time()
            append_history(robot_id, mission)
            set_current_mission(robot_id, None)
            with self._lock:
                self._threads.pop(robot_id, None)
                self._stop_flags.pop(robot_id, None)
                self._pause_flags.pop(robot_id, None)


patrol_manager = PatrolManager()
