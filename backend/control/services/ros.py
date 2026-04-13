from typing import Dict, Any
from urllib.parse import urlparse

import cv2
import requests
from django.conf import settings

from ..models import Robot


class ROSClient:
    """
    Thay vì nói chuyện trực tiếp với ROS2,
    lớp này gọi HTTP tới các service đang chạy trên robot:

    - Dogzilla control/camera:   http://<host>:9000
    - QR service:               http://<host>:8888
    - SLAM/navigation service:  http://<host>:8080

    Robot.addr trong DB vẫn lưu base Dogzilla URL, ví dụ:
        http://192.168.1.50:9000

    Từ đó class này sẽ tự suy ra host và build các URL còn lại.
    """

    def __init__(self, robot_id: str):
        self.robot_id = robot_id
        self.timeout = getattr(settings, "DOGZILLA_TIMEOUT", 5)
        self.stream_timeout = getattr(settings, "DOGZILLA_STREAM_TIMEOUT", 30)
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # Helpers nội bộ
    # ------------------------------------------------------------------
    def _get_robot(self) -> Robot:
        return Robot.objects.get(pk=self.robot_id)

    def _get_base_url(self) -> str:
        """
        Base URL của Dogzilla server từ Robot.addr.
        Ví dụ: http://192.168.1.50:9000
        """
        robot = self._get_robot()
        base = (robot.addr or "").strip().rstrip("/")
        if not base:
            raise RuntimeError(
                f"Robot {self.robot_id} chưa có addr. "
                "Hãy gọi /api/robots/<id>/connect/ trước."
            )
        return base

    def _parse_base(self):
        base = self._get_base_url()
        parsed = urlparse(base)
        scheme = parsed.scheme or "http"
        host = parsed.hostname
        if not host:
            raise RuntimeError("Không parse được host từ robot.addr")
        return scheme, host

    def _build_url(self, port: int, path: str) -> str:
        scheme, host = self._parse_base()
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{scheme}://{host}:{port}{normalized_path}"

    def _get_json(self, path: str) -> Dict[str, Any]:
        """
        GET base_url + path và parse JSON.
        path: "/status", "/health", ...
        """
        url = f"{self._get_base_url()}{path}"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _get_json_by_url(self, url: str) -> Dict[str, Any]:
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post_json_by_url(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.post(url, json=payload, timeout=self.timeout)

        try:
            data = resp.json()
        except Exception:
            data = {
                "success": False,
                "message": resp.text,
            }

        if not resp.ok:
            raise RuntimeError(f"Request failed: {data}")

        return data

    def _post_control(self, payload: Dict[str, Any]) -> None:
        """
        Gửi POST tới /control trên Flask server Dogzilla.
        """
        url = f"{self._get_base_url()}/control"
        resp = self.session.post(url, json=payload, timeout=self.timeout)

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
          - trả kết quả connect cho view
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
        Đọc /status từ Dogzilla server và trả nguyên JSON.
        """
        robot = self._get_robot()

        try:
            s = self._get_json("/status") or {}
        except Exception as e:
            print(f"[ROSClient] get_status() error: {e}")
            s = {}

        if s.get("battery") is None and getattr(robot, "battery", None) is not None:
            s["battery"] = robot.battery

        if s.get("fps") is None and getattr(robot, "fps", None) is not None:
            s["fps"] = robot.fps

        return s

    # ------------------------------------------------------------------
    # 3) FPV / camera stream
    # ------------------------------------------------------------------
    def get_fpv_url(self) -> str:
        """
        Camera stream từ Dogzilla server.
        """
        return f"{self._get_base_url()}/camera"

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

    def stream_slam_map_png(self):
        """
        Lấy map.png từ service SLAM trên cổng 8080.
        """
        url = self._build_url(8080, "/map.png")
        resp = self.session.get(
            url,
            stream=True,
            timeout=(self.timeout, self.stream_timeout),
        )
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # 4) Speed mode
    # ------------------------------------------------------------------
    def set_speed_mode(self, mode: str) -> None:
        """
        Django API đang hỗ trợ "slow" | "normal" | "high".
        Dogzilla server hiện chưa có speed mode global.
        """
        assert mode in ("slow", "normal", "high")
        print(f"[ROSClient] set_speed_mode({mode}) (no-op for Dogzilla server)")

    # ------------------------------------------------------------------
    # 5) Move command
    # ------------------------------------------------------------------
    def move(self, payload: Dict[str, Any]) -> None:
        """
        Map body move từ Django sang lệnh rời rạc của Dogzilla:
          - forward, back, left, right, turnleft, turnright, stop
        """

        def _f(v):
            try:
                return float(v)
            except Exception:
                return 0.0

        vx = _f(payload.get("vx"))
        vy = _f(payload.get("vy"))
        rz = _f(payload.get("rz"))

        mags = [
            (abs(vx), "vx"),
            (abs(vy), "vy"),
            (abs(rz), "rz"),
        ]
        mag, axis = max(mags, key=lambda t: t[0])

        if mag < 1e-3:
            self._post_control({"command": "stop"})
            return

        if axis == "vx":
            cmd = "forward" if vx > 0 else "back"
        elif axis == "vy":
            cmd = "right" if vy > 0 else "left"
        else:
            cmd = "turnleft" if rz > 0 else "turnright"

        self._post_control({"command": cmd})

    # ------------------------------------------------------------------
    # 6) Posture / Behavior / Lidar / Body adjust / Stabilizing
    # ------------------------------------------------------------------
    def posture(self, name: str) -> None:
        self._post_control({"command": "posture", "name": name})

    def behavior(self, name: str) -> None:
        self._post_control({"command": "behavior", "name": name})

    def lidar(self, action: str) -> None:
        assert action in ("start", "stop")
        self._post_control({"command": "lidar", "action": action})

    def body_adjust(self, sliders: Dict[str, float]) -> None:
        payload: Dict[str, Any] = {"command": "body_adjust"}
        payload.update(sliders)
        self._post_control(payload)

    def stabilizing_mode(self, action: str) -> None:
        assert action in ("on", "off", "toggle")
        payload: Dict[str, Any] = {
            "command": "stabilizing_mode",
            "action": action,
        }
        self._post_control(payload)

    # ------------------------------------------------------------------
    # 7) Base URL cho QR / SLAM
    # ------------------------------------------------------------------

    def _build_slam_base_url(self) -> str:
        """
        SLAM / navigation service đang chạy ở cổng 8080.
        """
        return self._build_url(8080, "")

    def get_slam_state(self) -> Dict[str, Any]:
        url = f"{self._build_slam_base_url()}/state"
        return self._get_json_by_url(url)

    def get_points(self) -> Dict[str, Any]:
        """
        Lấy danh sách marker/point đã lưu trên robot.
        Endpoint gốc: GET /points
        """
        url = f"{self._build_slam_base_url()}/points"
        return self._get_json_by_url(url)

    def create_point(self, name: str, x: float, y: float, yaw: float = 0.0) -> Dict[str, Any]:
        """
        Lưu point mới trên robot.
        Endpoint gốc: POST /points
        """
        url = f"{self._build_slam_base_url()}/points"
        payload = {
            "name": name,
            "x": x,
            "y": y,
            "yaw": yaw,
        }
        return self._post_json_by_url(url, payload)

    def delete_point(self, name: str) -> Dict[str, Any]:
        """
        Xóa point trên robot.
        Theo code test ngoài của bạn: POST /delete_point
        """
        url = f"{self._build_slam_base_url()}/delete_point"
        payload = {"name": name}
        return self._post_json_by_url(url, payload)

    def go_to_point(self, name: str) -> Dict[str, Any]:
        """
        Đi tới point đã lưu sẵn theo tên.
        Theo code test ngoài của bạn: POST /go_to_point
        """
        url = f"{self._build_slam_base_url()}/go_to_point"
        payload = {"name": name}
        return self._post_json_by_url(url, payload)

    def go_to_marker(
        self,
        label: str,
        x: float,
        y: float,
        yaw: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Đi trực tiếp tới marker/toạ độ.
        Chức năng cũ được giữ lại, nhưng sửa lại cho đúng service.
        Endpoint đúng phải là SLAM/navigation service, không phải QR service.
        """
        url = f"{self._build_slam_base_url()}/go_to_marker"
        payload = {
            "label": label,
            "x": x,
            "y": y,
            "yaw": yaw,
        }
        return self._post_json_by_url(url, payload)