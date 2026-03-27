import requests
from typing import Optional, Dict, Any


class RobotAPIClient:
    def __init__(self, base_url: str, timeout: float = 1.5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

        self.last_command: Optional[str] = None
        self.last_payload: Optional[Dict[str, Any]] = None
        self.current_speed_mode: str = "normal"

        self.body_state: Dict[str, float] = {
            "tx": 0.0,
            "ty": 0.0,
            "tz": 0.0,
            "rx": 0.0,
            "ry": 0.0,
            "rz": 0.0,
        }

    def _post_control(self, payload: Dict[str, Any]) -> bool:
        url = f"{self.base_url}/control"
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            ok = resp.ok
            text = ""
            try:
                text = resp.text[:200]
            except Exception:
                pass
            print(f"[RobotAPI] POST {url} {payload} -> {resp.status_code} {text}")
            return ok
        except requests.RequestException as e:
            print(f"[RobotAPI] control error: {e}")
            return False

    def send_command(self, command: str, force: bool = False, **extra) -> bool:
        payload = {"command": command}
        payload.update(extra)

        if not force and self.last_command == command and self.last_payload == payload:
            return True

        ok = self._post_control(payload)
        if ok:
            self.last_command = command
            self.last_payload = payload
        return ok

    def stop(self, force: bool = False) -> bool:
        return self.send_command("stop", force=force)

    def forward(self) -> bool:
        return self.send_command("forward")

    def back(self) -> bool:
        return self.send_command("back")

    def left(self) -> bool:
        return self.send_command("left")

    def right(self) -> bool:
        return self.send_command("right")

    def turnleft(self) -> bool:
        return self.send_command("turnleft")

    def turnright(self) -> bool:
        return self.send_command("turnright")

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

    def set_translation_z(self, z_value: float, force: bool = False) -> bool:
        return self.body_adjust(tz=z_value, force=force)

    def set_attitude_pitch(self, pitch_value: float, force: bool = False) -> bool:
        return self.body_adjust(ry=pitch_value, force=force)

    def get_body_state(self) -> Dict[str, float]:
        return dict(self.body_state)