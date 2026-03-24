import requests
from typing import Optional, Dict, Any


class RobotAPIClient:
    def __init__(self, base_url: str, timeout: float = 1.5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

        self.last_command: Optional[str] = None
        self.last_payload: Optional[Dict[str, Any]] = None

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