# control/services/ros.py
# Hoặc control/ros.py nếu bạn không dùng folder services

from typing import Dict, Any
import requests
import cv2
import numpy as np
from django.conf import settings
from ..models import Robot


class ROSClient:
    """
    Thay vì nói chuyện trực tiếp với ROS2,
    lớp này sẽ gọi HTTP tới Flask server Dogzilla (server bạn gửi lúc trước).

    Mặc định:
      - Địa chỉ server Dogzilla của từng robot được lưu trong Robot.addr
      - ConnectView sẽ nhận "addr" từ frontend và lưu vào Robot.addr
      - Các method còn lại đọc Robot.addr để biết base URL.
    """

    def __init__(self, robot_id: str):
        self.robot_id = robot_id
        self.timeout = getattr(settings, "DOGZILLA_TIMEOUT", 5)
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # Helpers nội bộ
    # ------------------------------------------------------------------
    def _get_robot(self) -> Robot:
        return Robot.objects.get(pk=self.robot_id)

    def _get_base_url(self) -> str:
        """
        Lấy base URL của Dogzilla server từ Robot.addr.
        Ví dụ: http://192.168.1.50:9000
        """
        robot = self._get_robot()
        base = (robot.addr or "").strip().rstrip("/")
        if not base:
            # Chưa connect => chưa có addr
            raise RuntimeError(
                f"Robot {self.robot_id} chưa có addr. "
                "Hãy gọi /api/robots/<id>/connect/ trước."
            )
        return base

    def _get_json(self, path: str) -> Dict[str, Any]:
        """
        GET base_url + path  và parse JSON.
        path: "/status", "/health", ...
        """
        base = self._get_base_url()
        url = f"{base}{path}"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post_control(self, payload: Dict[str, Any]) -> None:
        """
        Gửi POST tới /control trên Flask server Dogzilla.
        payload dạng:
          {"command": "forward"}
          {"command": "setz", "value": 100}
          {"command": "setpitch", "value": -5}
          ...
        """
        base = self._get_base_url()
        url = f"{base}/control"
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        # Nếu muốn log:
        try:
            text = resp.text[:200]
        except Exception:
            text = "<binary>"
        print(f"[ROSClient] POST {url} {payload} -> {resp.status_code} {text}")
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # 1) Connect
    # ------------------------------------------------------------------
    def connect(self, addr: str) -> Dict[str, Any]:
        """
        Frontend gửi addr (VD: 'http://192.168.1.50:9000').
        Ta:
          - làm sạch addr
          - thử ping /health trên Flask server Dogzilla
          - trả kết quả connect cho view (view sẽ lưu robot.addr)
        """
        addr_clean = (addr or "").strip().rstrip("/")
        if not addr_clean:
            return {"connected": False, "error": "addr is empty"}

        url = f"{addr_clean}/health"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            ok = resp.ok
            print(f"[ROSClient] connect() ping {url} -> {resp.status_code}")
            return {"connected": ok, "addr": addr_clean}
        except requests.RequestException as e:
            print(f"[ROSClient] connect() error: {e}")
            return {"connected": False, "error": str(e), "addr": addr_clean}

    # ------------------------------------------------------------------
    # 2) Status
    # ------------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        """
        Đọc /status từ Flask server Dogzilla và TRẢ NGUYÊN JSON của nó.

        Flask /status hiện tại trả kiểu:

        {
          "robot_connected": true,
          "turn_speed_range": [-70, 70],
          "step_default": 8,
          "z_range": [75, 110],
          "z_current": 105,
          "pitch_range": [-30.0, 30.0],
          "pitch_current": 0.0,
          "battery": 73,
          "fw": "4.0.1-Y",
          "fps": 30,
          "system": {
            "cpu_percent": 100,
            "disk": "SDC:67% -> 53.0GB",
            "ip": "x.x.x.x",
            "ram": "RAM:69% -> 4.0GB",
            "time": "13:57:02"
          }
        }
        """
        robot = self._get_robot()

        try:
            s = self._get_json("/status") or {}
        except Exception as e:
            print(f"[ROSClient] get_status() error: {e}")
            s = {}

        # fallback battery/fps từ DB nếu server không trả
        if s.get("battery") is None and getattr(robot, "battery", None) is not None:
            s["battery"] = robot.battery

        if s.get("fps") is None and getattr(robot, "fps", None) is not None:
            s["fps"] = robot.fps

        return s

    # ------------------------------------------------------------------
    # 3) FPV (camera stream)
    # ------------------------------------------------------------------
    def get_fpv_url(self) -> str:
        """
        Frontend sẽ dùng URL này để nhúng stream.
        Với Dogzilla Flask server:
          - /camera: stream MJPEG
          - /frame : single JPEG (nếu cần)
        Ở đây trả về /camera.
        """
        base = self._get_base_url()
        return f"{base}/camera"
    def get_frame(self):
        stream_url = self.get_fpv_url()
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            print(f"[ROSClient] Không mở được camera {stream_url}")
            return None
        ret, frame = cap.read()
        cap.release()
        if not ret:
            print("[ROSClient] Không đọc được frame")
            return None
        return frame
    # ------------------------------------------------------------------
    # 4) Speed mode
    # ------------------------------------------------------------------
    def set_speed_mode(self, mode: str) -> None:
        """
        Django API đang hỗ trợ "slow" | "normal" | "high".
        Flask server Dogzilla hiện không có khái niệm speed mode global,
        nên tạm thời mình để no-op (không làm gì).
        Bạn có thể sau này map sang step_default hoặc speed riêng nếu muốn.
        """
        assert mode in ("slow", "normal", "high")
        print(f"[ROSClient] set_speed_mode({mode}) (no-op for Dogzilla server)")

    # ------------------------------------------------------------------
    # 5) Move command
    # ------------------------------------------------------------------
    def move(self, payload: Dict[str, Any]) -> None:
        """
        Body từ Django view:
          {
            "vx": 0.1, "vy": 0.0, "vz": 0.0,
            "rx": 0.0, "ry": 0.0, "rz": 0.3
          }

        Dogzilla Flask server chỉ có lệnh rời rạc:
          - forward, back, left, right, turnleft, turnright, stop

        Ở đây ta sẽ:
          - lấy vx, vy, rz
          - chọn thành phần có độ lớn lớn nhất
          - map sang 1 lệnh tương ứng
        """

        def _f(v):
            try:
                return float(v)
            except Exception:
                return 0.0

        vx = _f(payload.get("vx"))
        vy = _f(payload.get("vy"))
        rz = _f(payload.get("rz"))

        # Nếu rất nhỏ -> dừng
        mags = [
            (abs(vx), "vx"),
            (abs(vy), "vy"),
            (abs(rz), "rz"),
        ]
        mag, axis = max(mags, key=lambda t: t[0])
        if mag < 1e-3:
            self._post_control({"command": "stop"})
            return

        # Map sang lệnh Dogzilla
        if axis == "vx":
            cmd = "forward" if vx > 0 else "back"
        elif axis == "vy":
            cmd = "right" if vy > 0 else "left"
        else:
            cmd = "turnleft" if rz > 0 else "turnright"

        self._post_control({"command": cmd})

    # ------------------------------------------------------------------
    # 6) Posture / Behavior / Lidar / Body adjust
    #    Hiện server Flask của bạn chưa có API tương ứng, nên tạm thời
    #    để no-op hoặc sau này có thể map sang control khác.
    # ------------------------------------------------------------------
    def posture(self, name: str) -> None:
        """
        Ví dụ name: 'Stand_Up', 'Lie_Down', ...
        Gửi sang Flask: {"command": "posture", "name": name}
        """
        payload = {"command": "posture", "name": name}
        self._post_control(payload)

    def behavior(self, name: str) -> None:
        """
        Ví dụ name: 'Wave_Hand', 'Pee', 'Turn_Roll', ...
        Gửi sang Flask: {"command": "behavior", "name": name}
        """
        payload = {"command": "behavior", "name": name}
        self._post_control(payload)

    def lidar(self, action: str) -> None:
        """
        action: 'start' | 'stop'
        Gửi sang Flask: {"command": "lidar", "action": action}
        """
        assert action in ("start", "stop")
        payload = {"command": "lidar", "action": action}
        self._post_control(payload)

    def body_adjust(self, sliders: Dict[str, float]) -> None:
        """
        sliders: {"tx":..., "ty":..., "tz":..., "rx":..., "ry":..., "rz":...}
        Gửi thẳng sang Flask, để server map sang translation/attitude.
        """
        payload: Dict[str, Any] = {"command": "body_adjust"}
        payload.update(sliders)
        self._post_control(payload)
        
    def stabilizing_mode(self, action: str) -> None:
        """
        action: 'on' | 'off' | 'toggle'
        Gửi sang Flask: {"command": "stabilizing_mode", "action": action}
        """

        assert action in ("on", "off", "toggle")
        payload: Dict[str, Any] = {
            "command": "stabilizing_mode",
            "action": action,
        }
        self._post_control(payload)



