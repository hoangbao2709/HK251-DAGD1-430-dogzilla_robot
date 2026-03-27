import threading
import time
from typing import Dict, Any, Optional, List

from robot_api import RobotAPIClient
from path_planner import PathPlanner
from warehouse_map import normalize_target, JUNCTION_SEQUENCE_FROM_START, get_turn_info
from config import DEFAULT_SPEED_MODE


class MissionManager:
    def __init__(self, tracker, robot_base_url: str):
        self.tracker = tracker
        self.robot = RobotAPIClient(robot_base_url)
        self.planner = PathPlanner()

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        self.enabled = True
        self.loop_dt = 0.06

        self.target: Optional[str] = None
        self.path: List[str] = []
        self.turn_plan: List[Dict[str, str]] = []
        self.plan_index = 0

        self.status = "idle"
        self.current_junction: Optional[str] = None
        self.last_passed_junction: Optional[str] = None

        self.junction_true_frames = 0
        self.junction_confirm_frames = 2
        self.junction_cooldown_sec = 0.9
        self.next_junction_ready_at = 0.0
        self.junction_latched = False

        self.speed_mode = str(DEFAULT_SPEED_MODE).lower().strip()
        if self.speed_mode not in {"slow", "normal", "high"}:
            self.speed_mode = "slow"
        self.robot.set_speed_mode(self.speed_mode, force=True)

        self.translation_z = 75.0
        self.attitude_pitch = 18.0
        self.robot.set_body_pose(self.translation_z, self.attitude_pitch, force=True)

        self.drive_linear_x = 0.0
        self.drive_angular_z = 0.0
        self.drive_send_interval = 0.06
        self.last_drive_sent_at = 0.0
        self.last_drive_payload = None

        self.not_found_frames = 0
        self.max_not_found_frames = 4
        self.current_command = "stop"

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("[MissionManager] started")

    def stop(self):
        self.running = False
        self._send_drive(0.0, 0.0, force=True)
        self.robot.stop(force=True)
        self.current_command = "stop"
        print("[MissionManager] stopped")

    def enable(self):
        with self.lock:
            self.enabled = True
            self.status = "running" if self.target else "idle"
        print("[MissionManager] enabled")

    def disable(self):
        with self.lock:
            self.enabled = False
            self.status = "paused" if self.target else "idle"
        self._send_drive(0.0, 0.0, force=True)
        self.robot.stop(force=True)
        self.current_command = "stop"
        print("[MissionManager] disabled")

    def set_robot_base_url(self, base_url: str):
        self.robot = RobotAPIClient(base_url)
        self.robot.set_speed_mode(self.speed_mode, force=True)
        self.robot.set_body_pose(self.translation_z, self.attitude_pitch, force=True)
        print(f"[MissionManager] robot base url = {base_url}")

    def set_speed_mode(self, mode: str):
        mode = str(mode).strip().lower()
        if mode not in {"slow", "normal", "high"}:
            raise ValueError("speed_mode must be one of: slow, normal, high")
        ok = self.robot.set_speed_mode(mode, force=True)
        if not ok:
            raise RuntimeError(f"Không đổi được tốc độ robot sang {mode}")
        with self.lock:
            self.speed_mode = mode
        return self.get_state()

    def set_translation_z(self, z_value: float):
        z_value = float(z_value)
        with self.lock:
            self.translation_z = z_value
        self.robot.set_body_pose(self.translation_z, self.attitude_pitch, force=True)
        return self.get_state()

    def set_attitude_pitch(self, pitch_value: float):
        pitch_value = float(pitch_value)
        with self.lock:
            self.attitude_pitch = pitch_value
        self.robot.set_body_pose(self.translation_z, self.attitude_pitch, force=True)
        return self.get_state()

    def set_body_pose(self, translation_z: float, attitude_pitch: float):
        with self.lock:
            self.translation_z = float(translation_z)
            self.attitude_pitch = float(attitude_pitch)
        self.robot.set_body_pose(self.translation_z, self.attitude_pitch, force=True)
        return self.get_state()

    def set_target(self, target: str):
        target = normalize_target(target)
        path, plan = self._build_turn_plan(target)
        with self.lock:
            self.target = target
            self.path = path
            self.turn_plan = plan
            self.plan_index = 0
            self.current_junction = plan[0]["junction"] if plan else None
            self.last_passed_junction = None
            self.status = "running"
            self.enabled = True
            self.junction_true_frames = 0
            self.junction_latched = False
            self.next_junction_ready_at = time.time() + 0.5
        self.tracker.set_turn_choice(self._get_active_turn_choice())
        print(f"[MissionManager] target={target} path={path} plan={plan}")
        return self.get_state()

    def cancel(self):
        with self.lock:
            self.target = None
            self.path = []
            self.turn_plan = []
            self.plan_index = 0
            self.current_junction = None
            self.last_passed_junction = None
            self.status = "idle"
            self.junction_true_frames = 0
            self.junction_latched = False
            self.next_junction_ready_at = 0.0
        self.tracker.set_turn_choice("straight")
        self._send_drive(0.0, 0.0, force=True)
        self.robot.stop(force=True)
        self.current_command = "stop"
        return self.get_state()

    def _active_plan_item(self) -> Optional[Dict[str, str]]:
        if 0 <= self.plan_index < len(self.turn_plan):
            return self.turn_plan[self.plan_index]
        return None

    def _get_active_turn_choice(self) -> str:
        item = self._active_plan_item()
        return item["choice"] if item else "straight"

    def _build_turn_plan(self, target: str):
        target = normalize_target(target)
        path = self.planner.shortest_from_start(target)
        if not path:
            raise ValueError(f"Không tìm được đường đi tới {target}")
        final_turn = get_turn_info(target)
        plan: List[Dict[str, str]] = []
        for i in range(len(path) - 1):
            node = path[i]
            next_node = path[i + 1]
            if node not in JUNCTION_SEQUENCE_FROM_START:
                continue
            if node == final_turn["junction"] and next_node == target:
                choice = final_turn["choice"]
            else:
                choice = "straight"
            plan.append({"junction": node, "choice": choice})
        return path, plan

    def _get_tracker_result(self) -> Dict[str, Any]:
        try:
            with self.tracker.lock:
                return dict(self.tracker.result)
        except Exception:
            return dict(getattr(self.tracker, "result", {}) or {})

    def _update_mission_progress(self, result: Dict[str, Any]):
        with self.lock:
            if not self.target:
                return
            active_item = self._active_plan_item()
            if active_item is None:
                self.current_junction = self.last_passed_junction
                if self.enabled:
                    self.status = "final_approach"
                self.tracker.set_turn_choice("straight")
                return

            self.current_junction = active_item["junction"]
            self.tracker.set_turn_choice(active_item["choice"])

            junction_now = bool(result.get("junction", False) or result.get("cross", False))
            now = time.time()
            if junction_now:
                self.junction_true_frames += 1
            else:
                self.junction_true_frames = 0
                self.junction_latched = False

            if (
                junction_now
                and self.junction_true_frames >= self.junction_confirm_frames
                and not self.junction_latched
                and now >= self.next_junction_ready_at
            ):
                passed = active_item
                self.last_passed_junction = passed["junction"]
                self.plan_index += 1
                self.junction_latched = True
                self.next_junction_ready_at = now + self.junction_cooldown_sec
                next_item = self._active_plan_item()
                if next_item is not None:
                    self.current_junction = next_item["junction"]
                    self.status = f"after_{passed['junction']}"
                    self.tracker.set_turn_choice(next_item["choice"])
                else:
                    self.current_junction = passed["junction"]
                    self.status = "final_approach"
                    self.tracker.set_turn_choice("straight")

    def _map_tracker_to_drive(self, result: Dict[str, Any]):
        found = bool(result.get("found", False))
        linear_x = float(result.get("linear_x", 0.0))
        angular_z = float(result.get("angular_z", 0.0))
        turn_state = str(result.get("turn_state", "follow"))
        turn_choice = str(result.get("turn_choice", "straight"))
        confidence = float(result.get("confidence", 0.0))

        if not found:
            self.not_found_frames += 1
            if self.not_found_frames >= self.max_not_found_frames:
                return 0.0, 0.0, "stop_lost"
            return self.drive_linear_x * 0.65, self.drive_angular_z * 0.65, "hold_lost"

        self.not_found_frames = 0

        lin = max(0.0, linear_x)
        ang = angular_z

        if confidence > 0.0:
            lin *= min(1.0, 0.45 + confidence)

        if turn_state in {"prepare_turn", "turning", "commit_turn"}:
            lin = min(lin, 0.032)
            if turn_choice == "left":
                ang = max(ang, 0.22)
            elif turn_choice == "right":
                ang = min(ang, -0.22)
            label = "turn"
        elif turn_state == "approach_turn":
            lin = min(lin, 0.040)
            label = "approach"
        else:
            label = "follow"

        if abs(ang) < 0.02:
            ang = 0.0
        if lin < 0.012:
            lin = 0.0

        return lin, ang, label

    def _send_drive(self, linear_x: float, angular_z: float, force: bool = False):
        payload = (round(float(linear_x), 4), round(float(angular_z), 4))
        now = time.time()
        if not force and self.last_drive_payload == payload and (now - self.last_drive_sent_at) < self.drive_send_interval:
            return True
        ok = self.robot.drive(payload[0], payload[1], force=force)
        if ok:
            self.drive_linear_x = payload[0]
            self.drive_angular_z = payload[1]
            self.last_drive_payload = payload
            self.last_drive_sent_at = now
            self.current_command = "drive"
        return ok

    def _loop(self):
        while self.running:
            try:
                if not self.enabled:
                    self._send_drive(0.0, 0.0, force=True)
                    time.sleep(self.loop_dt)
                    continue

                result = self._get_tracker_result()
                self._update_mission_progress(result)
                linear_x, angular_z, mode = self._map_tracker_to_drive(result)
                with self.lock:
                    if self.target and self.status == "idle":
                        self.status = "running"
                    elif not self.target:
                        self.status = mode
                self._send_drive(linear_x, angular_z)

            except Exception as e:
                print(f"[MissionManager] loop error: {e}")
                try:
                    self._send_drive(0.0, 0.0, force=True)
                    self.robot.stop(force=True)
                except Exception:
                    pass

            time.sleep(self.loop_dt)

    def get_state(self):
        result = self._get_tracker_result()
        active_item = self._active_plan_item()
        return {
            "running": self.running,
            "enabled": self.enabled,
            "robot_base_url": self.robot.base_url,
            "target": self.target,
            "path": list(self.path),
            "turn_plan": list(self.turn_plan),
            "plan_index": self.plan_index,
            "status": self.status,
            "current_junction": self.current_junction,
            "last_passed_junction": self.last_passed_junction,
            "next_turn_choice": active_item["choice"] if active_item else "straight",
            "turn_choice": result.get("turn_choice", "straight"),
            "speed_mode": self.speed_mode,
            "translation_z": self.translation_z,
            "attitude_pitch": self.attitude_pitch,
            "body_state": self.robot.get_body_state(),
            "drive_linear_x": self.drive_linear_x,
            "drive_angular_z": self.drive_angular_z,
            "tracker": {
                "found": result.get("found", False),
                "linear_x": result.get("linear_x", 0.0),
                "angular_z": result.get("angular_z", 0.0),
                "junction": result.get("junction", False),
                "cross": result.get("cross", False),
                "approach": result.get("approach", False),
                "turn_state": result.get("turn_state", "follow"),
                "turn_choice": result.get("turn_choice", "straight"),
                "action_label": result.get("action_label", "STOP"),
                "error_px": result.get("error_px", 0),
                "confidence": result.get("confidence", 0.0),
            },
        }
