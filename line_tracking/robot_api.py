import requests
from typing import Optional, Dict, Any


class RobotAPIClient:
    def __init__(self, base_url: str, timeout: float = 1.5):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.session = requests.Session()

        self.last_command: Optional[str] = None
        self.last_payload: Optional[Dict[str, Any]] = None
        self.last_drive_payload: Optional[Dict[str, float]] = None
        self.current_speed_mode: str = "normal"

        self.body_state: Dict[str, float] = {
            "tx": 0.0,
            "ty": 0.0,
            "tz": 75.0,
            "rx": 0.0,
            "ry": 15.0,
            "rz": 0.0,
        }

        self.manual_presets = {
            "slow": {
                "forward": {"linear_x": 0.030, "angular_z": 0.0},
                "back": {"linear_x": -0.025, "angular_z": 0.0},
                "left": {"linear_x": 0.0, "angular_z": 0.18},
                "right": {"linear_x": 0.0, "angular_z": -0.18},
                "turnleft": {"linear_x": 0.0, "angular_z": 0.32},
                "turnright": {"linear_x": 0.0, "angular_z": -0.32},
            },
            "normal": {
                "forward": {"linear_x": 0.050, "angular_z": 0.0},
                "back": {"linear_x": -0.040, "angular_z": 0.0},
                "left": {"linear_x": 0.0, "angular_z": 0.24},
                "right": {"linear_x": 0.0, "angular_z": -0.24},
                "turnleft": {"linear_x": 0.0, "angular_z": 0.42},
                "turnright": {"linear_x": 0.0, "angular_z": -0.42},
            },
            "high": {
                "forward": {"linear_x": 0.065, "angular_z": 0.0},
                "back": {"linear_x": -0.050, "angular_z": 0.0},
                "left": {"linear_x": 0.0, "angular_z": 0.30},
                "right": {"linear_x": 0.0, "angular_z": -0.30},
                "turnleft": {"linear_x": 0.0, "angular_z": 0.52},
                "turnright": {"linear_x": 0.0, "angular_z": -0.52},
            },
        }

    def _post_json(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = payload or {}
        try:
            resp = self.session.post(url, json=data, timeout=self.timeout)
            try:
                body = resp.json()
            except Exception:
                body = {"raw_text": resp.text[:300]}
            print(f"[RobotAPI] POST {url} {data} -> {resp.status_code} {body}")
            return {"ok": bool(resp.ok), "status_code": resp.status_code, "data": body}
        except requests.RequestException as e:
            print(f"[RobotAPI] request error: {e}")
            return {"ok": False, "status_code": 0, "data": {"error": str(e)}}

    def send_command(self, command: str, force: bool = False, **extra) -> bool:
        payload = {"command": command}
        payload.update(extra)

        if not force and self.last_command == command and self.last_payload == payload:
            return True

        result = self._post_json("/control", payload)
        if result["ok"]:
            self.last_command = command
            self.last_payload = payload
        return bool(result["ok"])

    def drive(self, linear_x: float, angular_z: float, force: bool = False) -> bool:
        payload = {
            "linear_x": round(float(linear_x), 4),
            "angular_z": round(float(angular_z), 4),
        }

        if not force and self.last_drive_payload == payload:
            return True

        result = self._post_json("/drive", payload)
        if result["ok"]:
            self.last_drive_payload = payload
        return bool(result["ok"])

    def stop(self, force: bool = False) -> bool:
        self.last_drive_payload = None
        result = self._post_json("/stop", {})
        return bool(result["ok"])

    def _drive_preset(self, name: str) -> bool:
        mode = self.current_speed_mode if self.current_speed_mode in self.manual_presets else "normal"
        preset = self.manual_presets[mode].get(name)
        if preset is None:
            return False
        return self.drive(
            linear_x=preset["linear_x"],
            angular_z=preset["angular_z"],
            force=True,
        )

    def forward(self) -> bool:
        return self._drive_preset("forward")

    def back(self) -> bool:
        return self._drive_preset("back")

    def left(self) -> bool:
        return self._drive_preset("left")

    def right(self) -> bool:
        return self._drive_preset("right")

    def turnleft(self) -> bool:
        return self._drive_preset("turnleft")

    def turnright(self) -> bool:
        return self._drive_preset("turnright")

    def set_speed_mode(self, mode: str, force: bool = False) -> bool:
        mode = str(mode).strip().lower()
        if mode not in {"slow", "normal", "high"}:
            return False

        ok = self.send_command("speed_mode", force=force, mode=mode)
        if ok:
            self.current_speed_mode = mode
        return ok

    def speed_mode(self) -> str:
        return self.current_speed_mode

    def body_adjust(
        self,
        tx: Optional[float] = None,
        ty: Optional[float] = None,
        tz: Optional[float] = None,
        rx: Optional[float] = None,
        ry: Optional[float] = None,
        rz: Optional[float] = None,
        force: bool = False,
    ) -> bool:
        payload = dict(self.body_state)
        if tx is not None:
            payload["tx"] = float(tx)
        if ty is not None:
            payload["ty"] = float(ty)
        if tz is not None:
            payload["tz"] = float(tz)
        if rx is not None:
            payload["rx"] = float(rx)
        if ry is not None:
            payload["ry"] = float(ry)
        if rz is not None:
            payload["rz"] = float(rz)

        ok = self.send_command("body_adjust", force=force, **payload)
        if ok:
            self.body_state = payload
        return ok

    def set_body_pose(self, translation_z: float, attitude_pitch: float, force: bool = False) -> bool:
        payload = {
            "translation_z": float(translation_z),
            "attitude_pitch": float(attitude_pitch),
        }
        result = self._post_json("/pose", payload)
        if result["ok"]:
            self.body_state["tz"] = float(translation_z)
            self.body_state["ry"] = float(attitude_pitch)
            return True

        body = result.get("data", {}) or {}
        if body.get("error") == "pose locked":
            if "translation_z" in body:
                self.body_state["tz"] = float(body["translation_z"])
            if "attitude_pitch" in body:
                self.body_state["ry"] = float(body["attitude_pitch"])
        return False

    def get_body_state(self) -> Dict[str, float]:
        return dict(self.body_state)
