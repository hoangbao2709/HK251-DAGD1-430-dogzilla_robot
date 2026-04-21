import json
from typing import Dict, Any
from urllib.parse import urlparse
import time

import cv2
import requests
from django.conf import settings  # type: ignore[import-untyped]
import numpy as np
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
        self.session.trust_env = False

    # ------------------------------------------------------------------
    # Helpers nội bộ
    # ------------------------------------------------------------------
    def _get_robot(self) -> Robot:
        robot, _ = Robot.objects.get_or_create(
            pk=self.robot_id,
            defaults={
                "name": self.robot_id.replace("-", " ").title(),
            },
        )
        return robot

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

    def _get_response(self, path: str, *, stream: bool = False):
        url = f"{self._get_base_url()}{path}"
        timeout = (self.timeout, self.stream_timeout) if stream else self.timeout
        resp = self.session.get(url, timeout=timeout, stream=stream)
        resp.raise_for_status()
        return resp

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

    def _post_control_with_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self._get_base_url()}/control"
        resp = self.session.post(url, json=payload, timeout=self.timeout)

        try:
            data = resp.json()
        except Exception:
            data = {
                "ok": resp.ok,
                "status_code": resp.status_code,
                "message": resp.text,
            }

        print(f"[ROSClient] POST {url} {payload} -> {resp.status_code}")
        resp.raise_for_status()
        return data

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

    def get_root_info(self) -> Dict[str, Any]:
        return self._get_json("/")

    def get_health(self) -> Dict[str, Any]:
        return self._get_json("/health")

    def get_test_page(self):
        return self._get_response("/test")

    def get_frame_response(self):
        return self._get_response("/frame")

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
        frame_url = f"{self._get_base_url()}/frame"

        try:
            resp = self.session.get(frame_url, timeout=(self.timeout, self.stream_timeout))
            resp.raise_for_status()

            data = np.frombuffer(resp.content, dtype=np.uint8)
            frame = cv2.imdecode(data, cv2.IMREAD_COLOR)

            if frame is None:
                print(f"[ROSClient] Decode frame failed from {frame_url}")
                return None

            return frame

        except Exception as e:
            print(f"[ROSClient] Không lấy được frame từ {frame_url}: {e}")
            return None

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
        self._post_control(
            {
                "command": "speed_mode",
                "mode": mode,
            }
        )

    def set_pace_mode(self, mode: str) -> None:
        assert mode in ("slow", "normal", "high")
        self._post_control(
            {
                "command": "pace",
                "mode": mode,
            }
        )

    # ------------------------------------------------------------------
    # 5) Move command
    # ------------------------------------------------------------------
    def move(self, payload: Dict[str, Any]) -> None:
        """
        Map body move từ Django sang lệnh rời rạc của Dogzilla:
          - forward, back, left, right, turnleft, turnright, stop
        """

        command = str(payload.get("command", "")).strip()
        if command in {"forward", "back", "left", "right", "turnleft", "turnright", "stop"}:
            allowed_keys = {"command", "step", "speed", "mode"}
            forwarded = {k: payload[k] for k in allowed_keys if k in payload}
            self._post_control(forwarded)
            return

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

        forwarded_payload: Dict[str, Any] = {"command": cmd}
        if "mode" in payload:
            forwarded_payload["mode"] = payload.get("mode")
        if axis == "rz" and "speed" in payload:
            forwarded_payload["speed"] = payload.get("speed")
        elif axis != "rz" and "step" in payload:
            forwarded_payload["step"] = payload.get("step")

        self._post_control(forwarded_payload)

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

    def reset_lidar(self, wait_seconds: float | None = None) -> float:
        delay = wait_seconds
        if delay is None:
            delay = float(getattr(settings, "LIDAR_RESET_DELAY_SECONDS", 1.0))
        delay = max(0.0, float(delay))

        self.lidar("stop")
        time.sleep(delay)
        self.lidar("start")
        return delay

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

    def z_control(self, payload: Dict[str, Any]) -> None:
        command = str(payload.get("command", "")).strip()
        assert command in ("setz", "adjustz")

        forwarded: Dict[str, Any] = {"command": command}
        if command == "setz":
            forwarded["value"] = payload.get("value")
        else:
            forwarded["delta"] = payload.get("delta")

        self._post_control(forwarded)


    def attitude_control(self, payload: Dict[str, Any]) -> None:
        command = str(payload.get("command", "")).strip()
        value_commands = {"setroll", "setpitch", "setyaw"}
        delta_commands = {"adjustroll", "adjustpitch", "adjustyaw"}
        assert command in value_commands | delta_commands

        forwarded: Dict[str, Any] = {"command": command}
        if command in value_commands:
            forwarded["value"] = payload.get("value")
        else:
            forwarded["delta"] = payload.get("delta")

        self._post_control(forwarded)
        
    def gait_type(self, mode: str) -> None:
        assert mode in ("trot", "walk", "high_walk")
        self._post_control({"command": "gait_type", "mode": mode})

    def perform(self, action: str) -> None:
        assert action in ("on", "off")
        self._post_control({"command": "perform", "action": action})

    def mark_time(self, value: int | float) -> None:
        self._post_control({"command": "mark_time", "value": value})

    def reset(self) -> None:
        self._post_control({"command": "reset"})

    def get_control_status(self) -> Dict[str, Any]:
        return self._post_control_with_response({"command": "status"})

    def raw_control(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post_control_with_response(payload)

    def get_network_metrics(self, samples: int = 5) -> Dict[str, Any]:
        """
        Best-effort network telemetry between Django backend and robot server.
        Measures:
        - latency/jitter/loss from repeated GET /health probes
        - downlink from a bounded GET /frame stream
        - uplink from POST /control with a valid status command payload
        """
        samples = max(1, min(int(samples), 10))
        health_url = f"{self._get_base_url()}/health"
        control_url = f"{self._get_base_url()}/control"
        frame_url = f"{self._get_base_url()}/frame"
        probe_size_bytes = 32 * 1024
        frame_sample_bytes = 256 * 1024

        def _score_ratio(value: float | None, good: float, bad: float) -> float:
            if value is None:
                return 0.0
            if value <= good:
                return 1.0
            if value >= bad:
                return 0.0
            return 1.0 - ((value - good) / (bad - good))

        def _throughput_score(value: float | None, target_kbps: float) -> float:
            if value is None or value <= 0:
                return 0.0
            return min(1.0, value / target_kbps)

        latencies_ms: list[float] = []
        failures = 0

        for _ in range(samples):
            resp = None
            started = time.perf_counter()
            try:
                resp = self.session.get(health_url, timeout=self.timeout)
                resp.raise_for_status()
                _ = resp.content
                latencies_ms.append((time.perf_counter() - started) * 1000.0)
            except Exception:
                failures += 1
            finally:
                try:
                    resp.close()
                except Exception:
                    pass

        latency_ms = round(sum(latencies_ms) / len(latencies_ms), 2) if latencies_ms else None
        if len(latencies_ms) > 1:
            jitter_ms = round(
                sum(abs(latencies_ms[i] - latencies_ms[i - 1]) for i in range(1, len(latencies_ms)))
                / (len(latencies_ms) - 1),
                2,
            )
        else:
            jitter_ms = 0.0 if latencies_ms else None

        packet_loss_pct = round((failures / samples) * 100.0, 2)

        downlink_kbps = None
        resp = None
        try:
            started = time.perf_counter()
            resp = self.session.get(
                frame_url,
                timeout=(self.timeout, self.stream_timeout),
                stream=True,
            )
            resp.raise_for_status()
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded >= frame_sample_bytes:
                    break
            elapsed = max(time.perf_counter() - started, 1e-3)
            downlink_kbps = round((downloaded * 8.0) / 1000.0 / elapsed, 2)
        except Exception:
            downlink_kbps = None
        finally:
            try:
                resp.close()
            except Exception:
                pass

        uplink_kbps = None
        resp = None
        try:
            probe_payload = {
                "command": "status",
                "probe": "uplink",
                "blob": "x" * probe_size_bytes,
            }
            probe_body = json.dumps(probe_payload, ensure_ascii=False).encode("utf-8")
            started = time.perf_counter()
            resp = self.session.post(
                control_url,
                json=probe_payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            elapsed = max(time.perf_counter() - started, 1e-3)
            uplink_kbps = round((len(probe_body) * 8.0) / 1000.0 / elapsed, 2)
        except Exception:
            uplink_kbps = None
        finally:
            try:
                resp.close()
            except Exception:
                pass

        reliability_score = _score_ratio(packet_loss_pct, good=0.0, bad=20.0)
        latency_score = _score_ratio(latency_ms, good=25.0, bad=250.0)
        jitter_score = _score_ratio(jitter_ms, good=5.0, bad=120.0)
        downlink_score = _throughput_score(downlink_kbps, target_kbps=8000.0)
        uplink_score = _throughput_score(uplink_kbps, target_kbps=4000.0)

        signal_quality = round(
            (reliability_score * 40.0)
            + (latency_score * 25.0)
            + (jitter_score * 15.0)
            + (downlink_score * 12.0)
            + (uplink_score * 8.0)
        )
        signal_quality = max(0, min(100, signal_quality))

        return {
            "uplink_kbps": uplink_kbps,
            "downlink_kbps": downlink_kbps,
            "latency_ms": latency_ms,
            "jitter_ms": jitter_ms,
            "packet_loss_pct": packet_loss_pct,
            "signal_quality": signal_quality,
        }

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

    def get_slam_status(self) -> Dict[str, Any]:
        url = f"{self._build_slam_base_url()}/slam_status"
        return self._get_json_by_url(url)

    def get_evaluation_metrics(
        self,
        *,
        full: bool = True,
        trajectory: bool = False,
        pose_traces: bool = False,
        reference_trajectory: bool = False,
    ) -> Dict[str, Any]:
        url = f"{self._build_slam_base_url()}/metrics"
        params: Dict[str, Any] = {}
        if full:
            params["full"] = 1
        else:
            if trajectory:
                params["trajectory"] = 1
            if pose_traces:
                params["pose_traces"] = 1
            if reference_trajectory:
                params["reference_trajectory"] = 1

        resp = self.session.get(url, params=params or None, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_robot_pose(self) -> Dict[str, Any]:
        state = self.get_slam_state() or {}
        pose = state.get("pose") or {}
        return pose

    def clear_navigation(self) -> Dict[str, Any]:
        url = f"{self._build_slam_base_url()}/clear_path"
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
