#!/usr/bin/env python3
# encoding: utf-8
"""
follow_line.py  –  chạy trên PC (Windows/Linux)
Lấy camera từ robot qua HTTP stream, điều khiển robot qua HTTP API.
Không cần DOGZILLALib (thư viện đó chỉ có trên Raspberry Pi của robot).
"""

import os
import threading
import time

import cv2 as cv
import numpy as np
import requests

from line_common import ManyImgs, color_follow, read_HSV, write_HSV, simplePID

# ── Cấu hình kết nối robot ─────────────────────────────────────────────────────
ROBOT_BASE_URL    = "http://10.28.128.171:9000"          # Flask server trên robot
CAMERA_SOURCE     = ROBOT_BASE_URL + "/camera"         # HTTP MJPEG stream
USE_REMOTE_CAMERA = True                               # False → dùng webcam local
CAMERA_INDEX      = 0                                  # webcam local (dự phòng)
# ───────────────────────────────────────────────────────────────────────────────


# ── HTTP client điều khiển robot (giống line_tracking/robot_api.py) ───────────
class RobotHTTPClient:
    """Gửi lệnh điều khiển tới robot qua POST /control (JSON)."""

    def __init__(self, base_url: str, timeout: float = 1.5):
        self.base_url = base_url.rstrip("/")
        self.timeout  = timeout
        self.session  = requests.Session()
        self._last_cmd = None

    def _send(self, payload: dict, force: bool = False) -> bool:
        cmd = payload.get("command")
        if not force and cmd == self._last_cmd:
            return True                          # tránh gửi trùng lặp
        url = f"{self.base_url}/control"
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            ok   = resp.ok
        except requests.RequestException as e:
            print(f"[RobotHTTP] Lỗi gửi lệnh: {e}")
            return False
        if ok:
            self._last_cmd = cmd
        return ok

    # ── Lệnh cơ bản ──────────────────────────────────────────────────────────
    def stop(self,  force=False): return self._send({"command": "stop"},      force)
    def forward(self):            return self._send({"command": "forward"})
    def back(self):               return self._send({"command": "back"})
    def left(self):               return self._send({"command": "left"})
    def right(self):              return self._send({"command": "right"})
    def turnleft(self):           return self._send({"command": "turnleft"})
    def turnright(self):          return self._send({"command": "turnright"})

    def turn(self, z_pid: int):
        """
        Chuyển đổi giá trị PID thành lệnh rẽ trái / thẳng / rẽ phải.
        z_pid > 0  → robot cần quay phải
        z_pid < 0  → robot cần quay trái
        """
        THRESHOLD = 15          # ngưỡng (pixels); chỉnh nếu cần
        if z_pid > THRESHOLD:
            return self.turnright()
        elif z_pid < -THRESHOLD:
            return self.turnleft()
        else:
            return self.forward()

    def reset(self):
        """Dừng robot (thay thế dog.reset())."""
        return self.stop(force=True)

    def pace(self, _mode):
        self._send({"command": f"pace_{_mode}"})

    def init_posture(self):
        try:
            self.session.post(
                f"{self.base_url}/control",
                json={"command": "init_posture"},
                timeout=self.timeout,
            )
        except Exception:
            pass
# ─────────────────────────────────────────────────────────────────────────────


def open_capture():
    """Mở cv.VideoCapture từ camera robot (HTTP) hoặc webcam local."""
    if USE_REMOTE_CAMERA:
        cap = cv.VideoCapture(CAMERA_SOURCE)
    else:
        cap = cv.VideoCapture(CAMERA_INDEX)
        cv_edition = cv.__version__
        if cv_edition[0] == '3':
            cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*'XVID'))
        else:
            cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter.fourcc('M', 'J', 'P', 'G'))
        cap.set(cv.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


# ── Logic theo dõi đường ─────────────────────────────────────────────────────
class LineDetect:
    def __init__(self):
        self.img        = None
        self.circle     = ()
        self.hsv_range  = ()
        self.Roi_init   = ()
        self.scale      = 1000

        self.dyn_update    = True
        self.select_flags  = False
        self.Track_state   = 'identify'
        self.windows_name  = 'frame'
        self.color         = color_follow()
        self.cols, self.rows = 0, 0
        self.Mouse_XY      = (0, 0)

        # Đường dẫn file HSV – cùng thư mục với script
        _dir = os.path.dirname(os.path.abspath(__file__))
        self.hsv_text = os.path.join(_dir, "LineFollowHSV.text")

        self.FollowLinePID = (10, 0, 20)
        self.PID_init()

        # Giới hạn tần suất gửi lệnh (giây) – tăng lên để robot di chuyển chậm hơn
        self.CMD_INTERVAL = 0.6         # s giữa 2 lệnh liên tiếp (tăng để robot đi chậm hơn)
        self._last_execute_time = 0.0

        # ── Thay DOGZILLALib bằng HTTP client ──
        self.dog = RobotHTTPClient(ROBOT_BASE_URL)
        self.dog_init()

    # ── Điều khiển robot ────────────────────────────────────────────────────
    def execute(self, point_x, point_y, radius):
        # Throttle: không gửi lệnh quá nhanh
        now = time.time()
        if now - self._last_execute_time < self.CMD_INTERVAL:
            return
        self._last_execute_time = now

        [z_pid, _] = self.PID_controller.update([(point_x - 320), 0])
        print("point_x:%d  point_y:%d  radius:%d  z_pid:%d"
              % (point_x, point_y, radius, int(z_pid)))
        self.dog.turn(int(z_pid))

    def cancel(self):
        self.dog.reset()

    def dog_init(self):
        self.dog.stop(force=True)
        time.sleep(0.01)
        self.dog.pace("slow")
        time.sleep(0.01)
        self.dog.init_posture()

    # ── Xử lý frame ─────────────────────────────────────────────────────────
    def process(self, rgb_img, action):
        binary  = []

        # Tăng sáng ảnh bằng phần mềm (bù camera tối)
        # alpha: độ tương phản (1.0 = giữ nguyên), beta: độ sáng thêm (0-100)
        rgb_img = cv.convertScaleAbs(rgb_img, alpha=1.4, beta=40)

        rgb_img = cv.resize(rgb_img, (640, 480))

        if action == 32:                                        # Space → bắt đầu chạy
            self.Track_state = 'tracking'
            self.dog.pace("slow")       # đảm bảo robot ở chế độ chậm nhất
            time.sleep(0.05)
            self.dog.forward()
        elif action in (ord('i'), 105): self.Track_state = "identify"
        elif action in (ord('r'), 114): self.Reset()

        if self.Track_state == 'init':
            cv.namedWindow(self.windows_name, cv.WINDOW_AUTOSIZE)
            cv.setMouseCallback(self.windows_name, self.onMouse, 0)
            if self.select_flags:
                cv.line(rgb_img, self.cols, self.rows, (255, 0, 0), 2)
                cv.rectangle(rgb_img, self.cols, self.rows, (0, 255, 0), 2)
                if self.Roi_init[0] != self.Roi_init[2] and self.Roi_init[1] != self.Roi_init[3]:
                    rgb_img, self.hsv_range = self.color.Roi_hsv(rgb_img, self.Roi_init)
                    self.dyn_update = True
                else:
                    self.Track_state = 'init'

        elif self.Track_state == "identify":
            if os.path.exists(self.hsv_text):
                self.hsv_range = read_HSV(self.hsv_text)
            else:
                self.Track_state = 'init'

        if self.Track_state != 'init' and len(self.hsv_range) != 0:
            rgb_img, binary, self.circle = self.color.line_follow(rgb_img, self.hsv_range)
            if self.dyn_update:
                write_HSV(self.hsv_text, self.hsv_range)
                self.dyn_update = False

        if self.Track_state == 'tracking':
            if len(self.circle) != 0:
                threading.Thread(
                    target=self.execute,
                    args=(self.circle[0], self.circle[1], self.circle[2]),
                    daemon=True,
                ).start()

        return rgb_img, binary

    # ── Chuột ────────────────────────────────────────────────────────────────
    def onMouse(self, event, x, y, flags, param):
        if event == 1:
            self.Track_state  = 'init'
            self.select_flags = True
            self.Mouse_XY     = (x, y)
        if event == 4:
            self.select_flags = False
            self.Track_state  = 'mouse'
        if self.select_flags:
            self.cols     = min(self.Mouse_XY[0], x), min(self.Mouse_XY[1], y)
            self.rows     = max(self.Mouse_XY[0], x), max(self.Mouse_XY[1], y)
            self.Roi_init = (self.cols[0], self.cols[1], self.rows[0], self.rows[1])

    def Reset(self):
        self.PID_init()
        self.Track_state = 'init'
        self.hsv_range   = ()
        self.dog_init()

    def PID_init(self):
        self.PID_controller = simplePID(
            [0, 0],
            [self.FollowLinePID[0] / self.scale, 0],
            [self.FollowLinePID[1] / self.scale, 0],
            [self.FollowLinePID[2] / self.scale, 0],
        )
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == '__main__':
    line_detect = LineDetect()

    capture = open_capture()
    if not capture.isOpened():
        src = CAMERA_SOURCE if USE_REMOTE_CAMERA else str(CAMERA_INDEX)
        raise RuntimeError(f"Không mở được camera: {src}")
    print("Camera opened:", CAMERA_SOURCE if USE_REMOTE_CAMERA else CAMERA_INDEX)
    print("Nhấn [Space] để bắt đầu theo dõi đường | [i] identify | [r] reset | [q] thoát")

    fail_count = 0
    while True:
        start = time.time()
        ret, frame = capture.read()

        # ── Xử lý mất frame / reconnect ─────────────────────────────────────
        if not ret or frame is None:
            fail_count += 1
            if fail_count % 10 == 1:
                print(f"[WARN] Không đọc được frame (fail_count={fail_count})")
            if USE_REMOTE_CAMERA and fail_count >= 20:
                print("[INFO] Thử reconnect camera stream...")
                try:
                    capture.release()
                except Exception:
                    pass
                time.sleep(1.0)
                capture = open_capture()
                fail_count = 0
            time.sleep(0.05)
            continue
        fail_count = 0
        # ────────────────────────────────────────────────────────────────────

        action = cv.waitKey(10) & 0xFF
        frame, binary = line_detect.process(frame, action)

        end = time.time()
        fps = 1 / max(end - start, 1e-6)
        cv.putText(frame, f"FPS : {int(fps)}", (30, 30),
                   cv.FONT_HERSHEY_SIMPLEX, 0.6, (100, 200, 200), 1)

        if len(binary) != 0:
            cv.imshow('frame', ManyImgs(1, ([frame, binary])))
        else:
            cv.imshow('frame', frame)

        if action in (ord('q'), 113):
            line_detect.cancel()
            break

    capture.release()
    cv.destroyAllWindows()
