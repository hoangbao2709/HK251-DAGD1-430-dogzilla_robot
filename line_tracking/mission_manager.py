import threading
import time
from typing import Dict, Any, Optional

from robot_api import RobotAPIClient


class MissionManager:
    def __init__(self, tracker, robot_base_url: str):
        self.tracker = tracker
        self.robot = RobotAPIClient(robot_base_url)

        self.running = False
        self.thread: Optional[threading.Thread] = None

        self.enabled = True
        self.loop_dt = 0.08

        # tuning
        self.turn_threshold = 0.22
        self.soft_turn_threshold = 0.10
        self.line_lost_stop = True
    def get_state(self):
        result = self._get_tracker_result()
        return {
            "running": self.running,
            "enabled": self.enabled,
            "robot_base_url": self.robot.base_url,
            "tracker": {
                "found": result.get("found", False),
                "linear_x": result.get("linear_x", 0.0),
                "angular_z": result.get("angular_z", 0.0),
                "junction": result.get("junction", False),
                "cross": result.get("cross", False),
                "turn_state": result.get("turn_state", "follow"),
                "turn_choice": result.get("turn_choice", "straight"),
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
        print("[MissionManager] stopped")

    def enable(self):
        self.enabled = True
        print("[MissionManager] enabled")

    def disable(self):
        self.enabled = False
        self.robot.stop(force=True)
        print("[MissionManager] disabled")

    def set_robot_base_url(self, base_url: str):
        self.robot = RobotAPIClient(base_url)
        print(f"[MissionManager] robot base url = {base_url}")

    def _get_tracker_result(self) -> Dict[str, Any]:
        try:
            with self.tracker.lock:
                return dict(self.tracker.result)
        except Exception:
            return dict(getattr(self.tracker, "result", {}) or {})

    def _decide_command(self, result: Dict[str, Any]) -> str:
        found = bool(result.get("found", False))
        angular_z = float(result.get("angular_z", 0.0))
        linear_x = float(result.get("linear_x", 0.0))

        junction = bool(result.get("junction", False))
        cross = bool(result.get("cross", False))
        turn_state = str(result.get("turn_state", "follow"))
        turn_choice = str(result.get("turn_choice", "straight"))

        if not found:
            return "stop"

        # Nếu tới giao lộ và tracker đang ở trạng thái chuẩn bị rẽ / đang rẽ
        if (junction or cross) and turn_choice in ("left", "right"):
            if turn_state in ("prepare_turn", "turning", "commit_turn"):
                return "turnleft" if turn_choice == "left" else "turnright"

        # Lệch nhiều thì quay tại chỗ
        if angular_z > self.turn_threshold:
            return "turnleft"
        if angular_z < -self.turn_threshold:
            return "turnright"

        # Lệch ít thì đi chếch ngang
        if angular_z > self.soft_turn_threshold:
            return "left"
        if angular_z < -self.soft_turn_threshold:
            return "right"

        # Không có line tiến rõ thì dừng
        if linear_x <= 0.0:
            return "stop"

        return "forward"

    def _send_motion_command(self, command: str):
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

    def _loop(self):
        while self.running:
            try:
                if not self.enabled:
                    self.robot.stop()
                    time.sleep(self.loop_dt)
                    continue

                result = self._get_tracker_result()
                command = self._decide_command(result)
                self._send_motion_command(command)

            except Exception as e:
                print(f"[MissionManager] loop error: {e}")
                try:
                    self.robot.stop(force=True)
                except Exception:
                    pass

            time.sleep(self.loop_dt)