import threading
import time
from typing import Dict, Any, Optional, List

from robot_api import RobotAPIClient
from path_planner import PathPlanner
from warehouse_map import (
    normalize_target,
    JUNCTION_SEQUENCE_FROM_START,
    get_turn_info,
)
from config import DEFAULT_SPEED_MODE


class MissionManager:
    def __init__(self, tracker, robot_base_url: str):
        self.tracker = tracker
        self.robot = RobotAPIClient(robot_base_url)
        self.planner = PathPlanner()

        self.running = False
        self.thread: Optional[threading.Thread] = None

        self.enabled = True
        self.loop_dt = 0.08

        self.turn_threshold = 0.18
        self.soft_turn_threshold = 0.08
        self.line_lost_stop = True

        self.lock = threading.Lock()

        self.target: Optional[str] = None
        self.path: List[str] = []
        self.turn_plan: List[Dict[str, str]] = []
        self.plan_index = 0

        self.status = "idle"
        self.current_junction: Optional[str] = None
        self.last_passed_junction: Optional[str] = None

        self.current_command = "stop"
        self.pending_command: Optional[str] = None
        self.pending_command_frames = 0
        self.command_hold_frames = 2
        self.min_command_interval = 0.14
        self.last_command_at = 0.0

        self.junction_true_frames = 0
        self.junction_confirm_frames = 2
        self.junction_cooldown_sec = 1.2
        self.next_junction_ready_at = 0.0
        self.junction_latched = False

        self.speed_mode = str(DEFAULT_SPEED_MODE).lower().strip()
        if self.speed_mode not in {"slow", "normal", "high"}:
            self.speed_mode = "normal"
        self.robot.set_speed_mode(self.speed_mode, force=True)

        self.translation_z = 0.0
        self.attitude_pitch = 0.0

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
            },
        }

    def start(self):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("[MissionManager] started")

    def stop(self):
        self.running = False
        self.robot.stop(force=True)
        self.current_command = "stop"
        self.pending_command = None
        self.pending_command_frames = 0
        print("[MissionManager] stopped")

    def enable(self):
        self.enabled = True
        with self.lock:
            if self.target:
                self.status = "running"
            else:
                self.status = "idle"
        print("[MissionManager] enabled")

    def disable(self):
        self.enabled = False
        self.robot.stop(force=True)
        self.current_command = "stop"
        self.pending_command = None
        self.pending_command_frames = 0
        with self.lock:
            if self.target:
                self.status = "paused"
            else:
                self.status = "idle"
        print("[MissionManager] disabled")

    def set_robot_base_url(self, base_url: str):
        self.robot = RobotAPIClient(base_url)
        self.robot.set_speed_mode(self.speed_mode, force=True)
        self.robot.body_adjust(
            tz=self.translation_z,
            ry=self.attitude_pitch,
            force=True,
        )
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

        print(f"[MissionManager] speed_mode = {mode}")
        return self.get_state()

    def set_translation_z(self, z_value: float):
        z_value = float(z_value)
        if z_value < 75:
            z_value = 75.0
        if z_value > 110:
            z_value = 110.0

        ok = self.robot.set_translation_z(z_value, force=True)
        if not ok:
            raise RuntimeError(f"Không đổi được Translation_Z sang {z_value}")

        with self.lock:
            self.translation_z = z_value

        print(f"[MissionManager] translation_z = {z_value}")
        return self.get_state()

    def set_attitude_pitch(self, pitch_value: float):
        pitch_value = float(pitch_value)
        if pitch_value < -15:
            pitch_value = -15.0
        if pitch_value > 15:
            pitch_value = 15.0

        ok = self.robot.set_attitude_pitch(pitch_value, force=True)
        if not ok:
            raise RuntimeError(f"Không đổi được Attitude_pitch sang {pitch_value}")

        with self.lock:
            self.attitude_pitch = pitch_value

        print(f"[MissionManager] attitude_pitch = {pitch_value}")
        return self.get_state()

    def set_body_pose(self, translation_z: float, attitude_pitch: float):
        translation_z = float(translation_z)
        attitude_pitch = float(attitude_pitch)

        if translation_z < 75:
            translation_z = 75.0
        if translation_z > 110:
            translation_z = 110.0

        if attitude_pitch < -15:
            attitude_pitch = -15.0
        if attitude_pitch > 15:
            attitude_pitch = 15.0

        ok = self.robot.body_adjust(
            tz=translation_z,
            ry=attitude_pitch,
            force=True,
        )
        if not ok:
            raise RuntimeError("Không cập nhật được body pose")

        with self.lock:
            self.translation_z = translation_z
            self.attitude_pitch = attitude_pitch

        print(
            f"[MissionManager] body pose updated: "
            f"translation_z={translation_z}, attitude_pitch={attitude_pitch}"
        )
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
        self.robot.stop(force=True)
        self.current_command = "stop"
        self.pending_command = None
        self.pending_command_frames = 0

        print("[MissionManager] mission cancelled")
        return self.get_state()

    def _active_plan_item(self) -> Optional[Dict[str, str]]:
        if 0 <= self.plan_index < len(self.turn_plan):
            return self.turn_plan[self.plan_index]
        return None

    def _get_active_turn_choice(self) -> str:
        item = self._active_plan_item()
        if item is None:
            return "straight"
        return item["choice"]

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
            elif next_node in JUNCTION_SEQUENCE_FROM_START:
                choice = "straight"
            else:
                choice = "straight"

            plan.append({
                "junction": node,
                "choice": choice,
            })

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

    def _decide_command(self, result: Dict[str, Any]) -> str:
        found = bool(result.get("found", False))
        angular_z = float(result.get("angular_z", 0.0))
        linear_x = float(result.get("linear_x", 0.0))
        turn_state = str(result.get("turn_state", "follow"))
        turn_choice = str(result.get("turn_choice", "straight"))
        action_label = str(result.get("action_label", "STOP"))

        active_turn_states = {"approach_turn", "prepare_turn", "turning", "commit_turn"}

        if turn_choice in ("left", "right") and turn_state in active_turn_states:
            if turn_state == "approach_turn":
                return "left" if turn_choice == "left" else "right"
            return "turnleft" if turn_choice == "left" else "turnright"

        if not found:
            return "stop" if self.line_lost_stop else self.current_command

        if action_label == "LEFT_HARD":
            return "turnleft"
        if action_label == "RIGHT_HARD":
            return "turnright"
        if action_label == "LEFT_SOFT":
            return "left"
        if action_label == "RIGHT_SOFT":
            return "right"

        if angular_z > self.turn_threshold:
            return "turnleft"
        if angular_z < -self.turn_threshold:
            return "turnright"

        if angular_z > self.soft_turn_threshold:
            return "left"
        if angular_z < -self.soft_turn_threshold:
            return "right"

        if linear_x <= 0.0:
            return "stop"

        return "forward"

    def _filter_command(self, command: str) -> str:
        now = time.time()

        if command == self.current_command:
            self.pending_command = None
            self.pending_command_frames = 0
            return command

        if command != self.pending_command:
            self.pending_command = command
            self.pending_command_frames = 1
            return self.current_command

        self.pending_command_frames += 1

        if self.pending_command_frames < self.command_hold_frames:
            return self.current_command

        if (now - self.last_command_at) < self.min_command_interval:
            return self.current_command

        self.pending_command = None
        self.pending_command_frames = 0
        return command

    def _send_motion_command(self, command: str):
        if command == self.current_command:
            return

        if command == "forward":
            self.robot.forward()
        elif command == "back":
            self.robot.back()
        elif command == "left":
            self.robot.left()
        elif command == "right":
            self.robot.right()
        elif command == "turnleft":
            self.robot.turnleft()
        elif command == "turnright":
            self.robot.turnright()
        else:
            self.robot.stop()

        self.current_command = command
        self.last_command_at = time.time()

    def _loop(self):
        while self.running:
            try:
                if not self.enabled:
                    if self.current_command != "stop":
                        self.robot.stop()
                        self.current_command = "stop"
                    time.sleep(self.loop_dt)
                    continue

                result = self._get_tracker_result()
                self._update_mission_progress(result)
                raw_command = self._decide_command(result)
                command = self._filter_command(raw_command)
                self._send_motion_command(command)

            except Exception as e:
                print(f"[MissionManager] loop error: {e}")
                try:
                    self.robot.stop(force=True)
                    self.current_command = "stop"
                    self.pending_command = None
                    self.pending_command_frames = 0
                except Exception:
                    pass

            time.sleep(self.loop_dt)