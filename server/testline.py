#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
line_tracking_no_ros.py - Bám đường thẳng màu đen cho robot DOGZILLA S2
====================================================================
Chạy trực tiếp mà không cần ROS 2.
- Python packages: opencv-python, numpy
- PID control cho angular.z, linear.x
- Preview camera và mask
- Thay _send_cmd bằng API robot hoặc socket khi có kết nối thực tế
====================================================================
"""

import cv2
import numpy as np
import time

# ==================================================================
# THÔNG SỐ ĐIỀU CHỈNH (Tuning parameters)
# ==================================================================

CAMERA_INDEX   = 0       # /dev/video0
FRAME_WIDTH    = 320
FRAME_HEIGHT   = 240

ROI_TOP_RATIO  = 0.55    # giữ phần dưới của frame

LOWER_BLACK    = np.array([0, 0, 0])
UPPER_BLACK    = np.array([180, 255, 80])
MIN_CONTOUR_AREA = 300

LINEAR_SPEED   = 0.08    # m/s
KP             = 0.35
KD             = 0.08
MAX_ANGULAR    = 0.8
LOST_LINE_TIMEOUT = 2.0
SHOW_PREVIEW   = True

# ==================================================================
# CLASS LINE TRACKING
# ==================================================================
class LineTracking:
    def __init__(self):
        # Camera
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        if not self.cap.isOpened():
            raise RuntimeError(f"Không mở được camera (index={CAMERA_INDEX})")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        # PID state
        self.prev_error = 0.0
        self.lost_time  = None
        self.running    = True

        print("=== Line Tracking khởi động ===")
        print(f"Camera OK | ROI={ROI_TOP_RATIO:.0%} từ dưới | Kp={KP} Kd={KD} | v={LINEAR_SPEED} m/s")

    # ------------------------------------------------------------------
    def process_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            print("[WARN] Không đọc được frame từ camera!")
            self._send_stop()
            return

        h, w = frame.shape[:2]
        roi_start = int(h * ROI_TOP_RATIO)
        roi = frame[roi_start:h, 0:w]

        # Mask màu đen
        hsv  = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, LOWER_BLACK, UPPER_BLACK)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
        mask   = cv2.erode(mask,  kernel, iterations=1)
        mask   = cv2.dilate(mask, kernel, iterations=2)

        # Contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid = [c for c in contours if cv2.contourArea(c) >= MIN_CONTOUR_AREA]

        if valid:
            self.lost_time = None
            largest = max(valid, key=cv2.contourArea)
            M  = cv2.moments(largest)
            cx = int(M['m10'] / M['m00'])
            center_x = w / 2.0
            error    = (cx - center_x) / center_x

            d_error   = error - self.prev_error
            angular_z = -(KP * error + KD * d_error)
            angular_z = float(np.clip(angular_z, -MAX_ANGULAR, MAX_ANGULAR))
            self.prev_error = error
            speed_factor = max(0.4, 1.0 - abs(error)*0.6)
            linear_x = LINEAR_SPEED * speed_factor

            # Publish lệnh (ở đây chỉ in ra, thay bằng robot API)
            self._send_cmd(linear_x, angular_z)

            direction = "THẲNG" if abs(error)<0.1 else ("TRÁI" if error<0 else "PHẢI")
            print(f"[{direction}] cx={cx:3d} | err={error:+.3f} | v={linear_x:.3f} w={angular_z:+.3f}")

            # Preview
            if SHOW_PREVIEW:
                cv2.drawContours(roi, [largest], -1, (0,255,0), 2)
                cv2.circle(roi, (cx, roi.shape[0]//2), 8, (0,0,255), -1)
                cv2.line(roi, (int(center_x),0), (int(center_x), roi.shape[0]), (255,0,0),1)
                cv2.putText(frame, f"[{direction}] err={error:+.2f}", (5,20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255),1)
        else:
            self.prev_error = 0.0
            if self.lost_time is None:
                self.lost_time = time.time()
                print("[WARN] Mất đường! Đang tìm lại...")
            elapsed = time.time() - self.lost_time
            if elapsed < LOST_LINE_TIMEOUT:
                search_dir = -0.3 if self.prev_error >=0 else 0.3
                self._send_cmd(0.0, search_dir)
                print(f"Tìm đường... {elapsed:.1f}s / {LOST_LINE_TIMEOUT}s")
            else:
                self._send_stop()
                print(f"[ERROR] Không tìm thấy đường sau {LOST_LINE_TIMEOUT:.0f}s → DỪNG.")

            if SHOW_PREVIEW:
                cv2.putText(frame, "MAT DUONG!", (5,20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255),2)

        # Hiển thị frame
        if SHOW_PREVIEW:
            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            cv2.rectangle(frame, (0,roi_start), (w,h), (255,255,0),1)
            frame_small = cv2.resize(frame,(FRAME_WIDTH,FRAME_HEIGHT))
            mask_small  = cv2.resize(mask_bgr,(FRAME_WIDTH//2, FRAME_HEIGHT//2))
            combined = np.zeros_like(frame_small)
            combined[:,:,:] = frame_small
            combined[:FRAME_HEIGHT//2, FRAME_WIDTH//2:] = mask_small
            cv2.imshow("DOGZILLA S2 - Line Tracking", combined)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[INFO] Người dùng nhấn 'q' → thoát.")
                self.running = False

    # ------------------------------------------------------------------
    def _send_cmd(self, linear_x, angular_z):
        # Thay bằng API robot hoặc socket
        print(f"[CMD] linear_x={linear_x:.3f} angular_z={angular_z:.3f}")

    def _send_stop(self):
        self._send_cmd(0.0,0.0)

    def cleanup(self):
        self._send_stop()
        if self.cap.isOpened():
            self.cap.release()
        cv2.destroyAllWindows()
        print("=== Dọn dẹp xong, thoát chương trình ===")


# ==================================================================
# MAIN
# ==================================================================
def main():
    tracker = LineTracking()
    try:
        while tracker.running:
            tracker.process_frame()
            time.sleep(1/30)  # 30Hz
    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C → dừng chương trình.")
    finally:
        tracker.cleanup()


if __name__ == "__main__":
    main()
