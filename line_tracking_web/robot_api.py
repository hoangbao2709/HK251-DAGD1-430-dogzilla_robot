import requests


class RobotAPI:
    def __init__(self, base_url="http://10.28.129.110:8000", timeout=0.2):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self):
        try:
            r = requests.get(f"{self.base_url}/health", timeout=self.timeout)
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def send_move(self, forward, turn):
        payload = {
            "action": "move",
            "forward": int(forward),
            "turn": int(turn),
        }
        try:
            r = requests.post(
                f"{self.base_url}/control",
                json=payload,
                timeout=self.timeout
            )
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stop(self):
        try:
            r = requests.post(
                f"{self.base_url}/control",
                json={"action": "stop"},
                timeout=self.timeout
            )
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}