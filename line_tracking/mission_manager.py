import threading
import time
from copy import deepcopy

from path_planner import PathPlanner
from warehouse_map import (
    DESTINATION_TO_TURN,
    JUNCTION_SEQUENCE_FROM_START,
    VALID_TARGETS,
)


class MissionManager:
    def __init__(self, tracker, poll_interval=0.05, junction_debounce_sec=0.8):
        self.tracker = tracker
        self.poll_interval = poll_interval
        self.junction_debounce_sec = junction_debounce_sec

        self.planner = PathPlanner()
        self.lock = threading.Lock()

        self.running = False
        self.thread = None

        self.active = False
        self.target = None
        self.path = []
        self.plan = []
        self.current_turn_choice = "straight"

        self.junction_index = 0
        self.current_junction = None
        self.last_junction_seen = False
        self.last_junction_time = 0.0
        self.completed = False
        self.status_text = "idle"

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)

    def set_target(self, target):
        target = str(target).strip().upper()
        if target not in VALID_TARGETS:
            raise ValueError(f"Target must be one of {VALID_TARGETS}")

        path = self.planner.shortest_from_start(target)
        plan = self._build_plan(target)

        with self.lock:
            self.active = True
            self.completed = False
            self.target = target
            self.path = path
            self.plan = plan
            self.current_turn_choice = "straight"
            self.junction_index = 0
            self.current_junction = None
            self.last_junction_seen = False
            self.last_junction_time = 0.0
            self.status_text = f"Mission started to {target}"

        self.tracker.set_turn_choice("straight")
        return self.get_state()

    def cancel(self):
        with self.lock:
            self.active = False
            self.completed = False
            self.target = None
            self.path = []
            self.plan = []
            self.current_turn_choice = "straight"
            self.junction_index = 0
            self.current_junction = None
            self.last_junction_seen = False
            self.last_junction_time = 0.0
            self.status_text = "mission cancelled"

        self.tracker.set_turn_choice("straight")
        return self.get_state()

    def get_state(self):
        with self.lock:
            remaining = self.plan[self.junction_index:] if self.active else []
            return {
                "active": self.active,
                "completed": self.completed,
                "target": self.target,
                "path": deepcopy(self.path),
                "plan": deepcopy(self.plan),
                "remaining_plan": deepcopy(remaining),
                "junction_index": self.junction_index,
                "current_junction": self.current_junction,
                "turn_choice": self.current_turn_choice,
                "status": self.status_text,
            }

    def _build_plan(self, target):
        target_meta = DESTINATION_TO_TURN[target]
        target_junction = target_meta["junction"]
        target_choice = target_meta["choice"]

        plan = []
        for junction in JUNCTION_SEQUENCE_FROM_START:
            if junction == target_junction:
                plan.append(
                    {
                        "junction": junction,
                        "action": target_choice,
                        "target": target,
                        "final": True,
                    }
                )
                break

            plan.append(
                {
                    "junction": junction,
                    "action": "straight",
                    "target": None,
                    "final": False,
                }
            )

        return plan

    def _loop(self):
        while self.running:
            with self.tracker.lock:
                tracker_result = dict(self.tracker.result)

            now = time.time()
            junction_seen = bool(tracker_result.get("junction", False))

            with self.lock:
                if not self.active:
                    self.last_junction_seen = junction_seen
                else:
                    rising_edge = junction_seen and not self.last_junction_seen
                    debounce_ok = (now - self.last_junction_time) >= self.junction_debounce_sec

                    if rising_edge and debounce_ok:
                        self.last_junction_time = now
                        self._handle_new_junction_locked()

                    self.last_junction_seen = junction_seen

            time.sleep(self.poll_interval)

    def _handle_new_junction_locked(self):
        if self.junction_index >= len(self.plan):
            return

        step = self.plan[self.junction_index]
        self.current_junction = step["junction"]
        self.current_turn_choice = step["action"]
        self.tracker.set_turn_choice(step["action"])

        self.status_text = (
            f"At {step['junction']} -> {step['action']}"
            + (f" to {step['target']}" if step["target"] else "")
        )

        self.junction_index += 1

        if step["final"]:
            self.status_text = f"Final turn at {step['junction']} -> {step['action']} to {step['target']}"