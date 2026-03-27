# -*- coding: utf-8 -*-
"""
robot_client/line_tracking_runner.py

Script chạy line tracking từ PC:
  1. Kéo MJPEG stream từ Flask server trên robot
  2. Xử lý từng frame bằng LineTracker (OpenCV + HSV)
  3. Tính PID → gửi lệnh điều khiển về robot qua HTTP POST

Cách chạy:
    python -m robot_client.line_tracking_runner

Options:
    --ip   <url>   URL của dogzilla Flask server, mặc định từ config/MongoDB
    --dry-run      In lệnh ra màn hình, KHÔNG gửi HTTP (test offline)
    --no-display   Không hiển thị cửa sổ OpenCV (chạy headless)
    --hsv-file     Đường dẫn file HSV, mặc định: LineFollowHSV.txt trong thư mục này

Phím tắt trong cửa sổ OpenCV:
    Space  → bắt đầu tracking (giống follow_line.py gốc)
    i      → về chế độ identify (đọc HSV từ file)
    r      → reset PID + về calibrate
    q      → thoát
    Chuột click-drag trên ảnh → calibrate màu line khi ở chế độ 'init'
"""

import argparse
import os
import sys
import time
import threading
import requests
import cv2
import numpy as np
from typing import Optional

# Thêm thư mục gốc vào path (để import robot_client)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from robot_client.line_tracker import LineTracker, SimplePID, read_hsv, write_hsv
from robot_client.camera import _HTTPMjpegCapture

# ─────────────────────────────────────────────
# Config mặc định
# ─────────────────────────────────────────────
DEFAULT_HSV_FILE = os.path.join(_HERE, "LineFollowHSV.txt")

# HSV mặc định cho line ĐEN trên nền sáng (chỉnh lại khi calibrate)
DEFAULT_HSV_LOWER = (0,   0,   0)
DEFAULT_HSV_UPPER = (180, 255, 60)

# PID: gain điều chỉnh steering (turn)
# error = center_x_line - 320  → PID → turn_value
PID_KP = 0.03
PID_KI = 0.0
PID_KD = 0.01

# Tốc độ tiến khi đang tracking
FORWARD_STEP = 15

# Giới hạn turn_value gửi sang robot
TURN_MAX = 70

# Khoảng lặp (giây)
LOOP_INTERVAL = 0.033   # ~30 fps


# ─────────────────────────────────────────────
# Gửi lệnh HTTP tới Flask server
# ─────────────────────────────────────────────

class RobotController:
    def __init__(self, base_url: str, dry_run: bool = False, timeout: float = 2.0):
        self.base_url = base_url.rstrip("/")
        self.dry_run  = dry_run
        self.timeout  = timeout
        self._session = requests.Session()
        self._lock    = threading.Lock()

    def _post(self, payload: dict):
        if self.dry_run:
            print(f"[DRY-RUN] POST /control {payload}")
            return
        url = f"{self.base_url}/control"
        try:
            with self._lock:
                r = self._session.post(url, json=payload, timeout=self.timeout)
            if not r.ok:
                print(f"[Controller] ERROR {r.status_code}: {r.text[:100]}")
        except requests.RequestException as e:
            print(f"[Controller] Request failed: {e}")

    def forward(self, step: int = FORWARD_STEP):
        self._post({"command": "forward", "step": step})

    def turn(self, value: int):
        """
        value > 0 → quay phải (line lệch phải)
        value < 0 → quay trái (line lệch trái)
        Dùng lệnh 'turn' (đã thêm vào Flask server).
        """
        self._post({"command": "turn", "value": int(value)})

    def stop(self):
        self._post({"command": "stop"})

    # Robot init (chỉ gửi stop, không gửi setz, pace để tương thích 100% Robot API)
    def dog_init(self):
        self._post({"command": "stop"})
        time.sleep(0.05)


# ─────────────────────────────────────────────
# Xử lý chuột để calibrate HSV
# ─────────────────────────────────────────────

class MouseROI:
    def __init__(self):
        self.start    = None
        self.end      = None
        self.drawing  = False
        self.done     = False   # True khi user thả chuột

    def callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.start   = (x, y)
            self.end     = (x, y)
            self.drawing = True
            self.done    = False
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.end = (x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            self.end     = (x, y)
            self.drawing = False
            self.done    = True

    def get_roi(self):
        """Trả về (x0,y0,x1,y1) đã chuẩn hóa, hoặc None nếu chưa chọn."""
        if self.start is None or self.end is None:
            return None
        x0, y0 = self.start
        x1, y1 = self.end
        return (min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1))

    def draw_rect(self, frame):
        roi = self.get_roi()
        if roi:
            x0, y0, x1, y1 = roi
            cv2.rectangle(frame, (x0,y0), (x1,y1), (0,255,0), 2)


# ─────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────

def run(base_url: str, dry_run: bool, display: bool, hsv_file: str):
    print(f"[Runner] Robot URL : {base_url}")
    print(f"[Runner] DRY-RUN   : {dry_run}")
    print(f"[Runner] HSV file  : {hsv_file}")
    print()

    # Khởi controller
    ctrl = RobotController(base_url, dry_run=dry_run)

    # Khởi PID (mỗi lần tracking mới → reset)
    pid = SimplePID(PID_KP, PID_KI, PID_KD)

    # Khởi tracker
    hsv_range = read_hsv(hsv_file)
    if hsv_range:
        print(f"[Runner] Loaded HSV range: lo={hsv_range[0]}  hi={hsv_range[1]}")
    else:
        print("[Runner] Không tìm thấy file HSV → vào chế độ 'init' để calibrate")

    tracker = LineTracker(hsv_range=hsv_range)

    # Kéo stream
    camera_url = f"{base_url}/camera"
    print(f"[Runner] Connecting to stream: {camera_url}")
    cap = _HTTPMjpegCapture(url=camera_url)
    if not cap.open():
        print("[Runner] ERROR: Không kết nối được stream camera!")
        print("         Kiểm tra robot đang chạy Flask server và IP đúng chưa.")
        return

    print("[Runner] Stream OK!")
    print()
    print("─" * 50)
    print("Phím tắt:")
    print("  Space  → Bắt đầu tracking")
    print("  i      → Chế độ identify (load HSV từ file)")
    print("  r      → Reset (calibrate lại)")
    print("  q      → Thoát")
    print("  [Kéo chuột trên ảnh ở chế độ init để chọn màu line]")
    print("─" * 50)

    # State
    #   'init'       → đang chọn ROI calibrate
    #   'identify'   → load HSV từ file, chờ Space
    #   'tracking'   → đang chạy
    state = "identify" if hsv_range else "init"

    mouse  = MouseROI()
    window = "Line Tracking [PC]"

    if display:
        cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(window, mouse.callback)

    ctrl.dog_init()

    try:
        while True:
            t0 = time.perf_counter()

            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue

            frame = cv2.resize(frame, (640, 480))

            # ── Phím bấm ──────────────────────────────────────────
            key = cv2.waitKey(1) & 0xFF if display else 0xFF

            if key == ord('q') or key == 113:
                print("[Runner] Thoát.")
                ctrl.stop()
                break

            elif key == 32:   # Space → bắt đầu tracking
                state = "tracking"
                pid.reset()
                ctrl.forward(FORWARD_STEP)
                print("[Runner] >>> TRACKING bắt đầu")

            elif key == ord('i') or key == 105:
                state = "identify"
                ctrl.stop()
                hsv_range = read_hsv(hsv_file)
                if hsv_range:
                    tracker.hsv_range = hsv_range
                    print(f"[Runner] Reloaded HSV: {hsv_range}")
                else:
                    state = "init"
                    print("[Runner] Không có file HSV → vào chế độ init")

            elif key == ord('r') or key == 114:
                state = "init"
                ctrl.stop()
                pid.reset()
                tracker.hsv_range = None
                mouse.start = mouse.end = None
                mouse.done  = False
                ctrl.dog_init()
                print("[Runner] Reset → vào chế độ calibrate")

            # ── Chế độ init: calibrate HSV bằng chuột ────────────
            if state == "init":
                display_frame = frame.copy()
                mouse.draw_rect(display_frame)
                cv2.putText(display_frame, "MODE: CALIBRATE  (kéo chuột chọn màu line)",
                            (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)

                if mouse.done:
                    roi = mouse.get_roi()
                    if roi and roi[0] != roi[2] and roi[1] != roi[3]:
                        hsv_range = tracker.learn_hsv_from_roi(frame, roi)
                        write_hsv(hsv_file, hsv_range)
                        print(f"[Runner] Đã học HSV: lo={hsv_range[0]}  hi={hsv_range[1]}  → lưu vào {hsv_file}")
                        state = "identify"
                        mouse.done = False

                if display:
                    cv2.imshow(window, display_frame)
                continue   # bỏ qua detect khi đang calibrate

            # ── Chế độ identify: hiển thị nhưng chưa gửi lệnh ───
            result = tracker.detect(frame)
            display_frame = result.frame.copy() if result.frame is not None else frame.copy()

            if state == "identify":
                cv2.putText(display_frame, "MODE: IDENTIFY  [Space] để bắt đầu",
                            (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 2)

            # ── Chế độ tracking: PID + gửi lệnh ─────────────────
            elif state == "tracking":
                if result.circle is not None:
                    cx, cy, rad = result.circle
                    error = result.error_x   # âm=line ở trái, dương=line ở phải

                    turn_raw   = pid.update(error)
                    turn_value = int(np.clip(turn_raw, -TURN_MAX, TURN_MAX))

                    # Gửi lệnh đồng thời trong thread để không block loop
                    def _send(tv=turn_value):
                        ctrl.turn(tv)
                    threading.Thread(target=_send, daemon=True).start()

                    # Vẽ thêm info debug
                    cv2.putText(display_frame, f"MODE: TRACKING", (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 100), 2)
                    cv2.putText(display_frame, f"error={error:+d}  turn={turn_value:+d}",
                                (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
                    cv2.putText(display_frame, f"line @ ({cx},{cy})",
                                (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                else:
                    # Mất line → dừng robot
                    ctrl.stop()
                    cv2.putText(display_frame, "LINE LOST — dừng robot",
                                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)

            # ── FPS overlay ───────────────────────────────────────
            elapsed = time.perf_counter() - t0
            fps = 1.0 / elapsed if elapsed > 0 else 0
            cv2.putText(display_frame, f"FPS: {fps:.0f}",
                        (10, display_frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 200), 1)

            if display:
                # Nếu có binary mask, ghép cạnh nhau để debug
                if result.binary is not None:
                    b3 = cv2.cvtColor(result.binary, cv2.COLOR_GRAY2BGR)
                    b3 = cv2.resize(b3, (display_frame.shape[1], display_frame.shape[0]))
                    combined = np.hstack([display_frame, b3])
                    cv2.imshow(window, combined)
                else:
                    cv2.imshow(window, display_frame)

            # ── Điều chỉnh nhịp loop đúng interval ───────────────
            sleep_t = LOOP_INTERVAL - (time.perf_counter() - t0)
            if sleep_t > 0:
                time.sleep(sleep_t)

    finally:
        cap.release()
        if display:
            cv2.destroyAllWindows()
        ctrl.stop()
        print("[Runner] Đã dừng.")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def _load_base_url(ip_arg: Optional[str]) -> str:
    if ip_arg:
        return ip_arg.rstrip("/")
    # Thử lấy từ config MongoDB (như robot_client/config.py)
    try:
        from robot_client import config
        return config.BASE_URL.rstrip("/")
    except Exception as e:
        print(f"[Runner] Không đọc được config: {e}")
        print("         Dùng --ip để chỉ định URL robot Flask server, VD:")
        print("         python -m robot_client.line_tracking_runner --ip http://192.168.1.50:9000")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Line tracking on PC → send commands to robot")
    parser.add_argument("--ip",          default=None,  help="URL của Flask server trên robot, VD: http://192.168.1.50:9000")
    parser.add_argument("--dry-run",     action="store_true", help="In lệnh ra màn hình, KHÔNG gửi HTTP")
    parser.add_argument("--no-display",  action="store_true", help="Không hiển thị cửa sổ OpenCV")
    parser.add_argument("--hsv-file",    default=DEFAULT_HSV_FILE, help=f"File lưu HSV (mặc định: {DEFAULT_HSV_FILE})")
    args = parser.parse_args()

    base_url = _load_base_url(args.ip)
    run(
        base_url  = base_url,
        dry_run   = args.dry_run,
        display   = not args.no_display,
        hsv_file  = args.hsv_file,
    )


if __name__ == "__main__":
    main()
