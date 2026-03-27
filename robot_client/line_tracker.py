# -*- coding: utf-8 -*-
"""
robot_client/line_tracker.py

Module xử lý ảnh thuần (không biết robot, không gọi HTTP).
Nhận numpy frame BGR, trả về frame đã annotate và tọa độ tâm line.

Tham khảo: follow_line.py + line_common.py từ tài liệu Yahboom 8.12.
"""

import cv2
import numpy as np
import os
import time


# ─────────────────────────────────────────────
# Helpers đọc/ghi HSV config (clone từ line_common.py)
# ─────────────────────────────────────────────

def write_hsv(path: str, hsv_range):
    """Lưu HSV range vào file text."""
    lo, hi = hsv_range
    with open(path, "w") as f:
        f.write(f"{lo[0]}, {lo[1]}, {lo[2]}, {hi[0]}, {hi[1]}, {hi[2]}")


def read_hsv(path: str):
    """Đọc HSV range từ file text. Trả None nếu lỗi."""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        line = f.readline().strip()
    parts = line.split(",")
    if len(parts) != 6:
        return None
    v = [int(x.strip()) for x in parts]
    return (v[0], v[1], v[2]), (v[3], v[4], v[5])


# ─────────────────────────────────────────────
# SimplePID (clone từ line_common.py)
# ─────────────────────────────────────────────

class SimplePID:
    """
    PID controller đơn giản (scalar).
    Kp, Ki, Kd: float
    """
    def __init__(self, kp: float, ki: float, kd: float):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self._integrator = 0.0
        self._last_error = 0.0
        self._last_time = None

    def reset(self):
        self._integrator = 0.0
        self._last_error = 0.0
        self._last_time = None

    def update(self, error: float) -> float:
        now = time.perf_counter()
        if self._last_time is None:
            self._last_time = now
            return 0.0

        dt = now - self._last_time
        if dt <= 0:
            return 0.0

        self._integrator += error * dt
        derivative = (error - self._last_error) / dt
        output = self.kp * error + self.ki * self._integrator + self.kd * derivative

        self._last_error = error
        self._last_time = now
        return output


# ─────────────────────────────────────────────
# LineTracker chính
# ─────────────────────────────────────────────

class LineTracker:
    """
    Phát hiện line trong 1 frame BGR và tính lệch tâm so với giữa ảnh.

    Cách dùng:
        tracker = LineTracker(hsv_range=((0,0,0),(180,255,80)))
        result  = tracker.detect(frame)

    result.circle  = (cx, cy, radius) hoặc None nếu không thấy line
    result.frame   = frame đã vẽ annotation
    result.binary  = ảnh binary mask (để debug)
    result.error_x = cx - frame_width//2  (âm=lệch trái, dương=lệch phải)
    """

    def __init__(
        self,
        hsv_range=None,
        frame_width: int = 640,
        frame_height: int = 480,
        roi_top_fraction: float = 0.5,   # bỏ bao nhiêu phần trên (0.5 = bỏ nửa trên)
        min_contour_area: float = 500.0,
    ):
        self.hsv_range = hsv_range          # ((lo_h,lo_s,lo_v),(hi_h,hi_s,hi_v)) hoặc None
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.roi_top_fraction = roi_top_fraction
        self.min_contour_area = min_contour_area
        self._kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    # ── Calibrate: học HSV từ vùng ROI người dùng chọn ──────────────────
    def learn_hsv_from_roi(self, frame_bgr, roi):
        """
        roi = (x_min, y_min, x_max, y_max)
        Tính HSV range từ vùng đó và lưu vào self.hsv_range.
        Trả về self.hsv_range.
        """
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        x0, y0, x1, y1 = roi
        patch = hsv[y0:y1, x0:x1]
        if patch.size == 0:
            return self.hsv_range

        h_vals = patch[:, :, 0].flatten()
        s_vals = patch[:, :, 1].flatten()
        v_vals = patch[:, :, 2].flatten()

        def _clamp(v, lo_off, hi_off, lo_bound=0, hi_bound=255):
            return max(lo_bound, int(v) - lo_off), min(hi_bound, int(v) + hi_off)

        h_lo, h_hi = _clamp(float(np.min(h_vals)), 5, 5, 0, 180)
        s_lo, _    = _clamp(float(np.min(s_vals)), 20, 0, 0, 255)
        v_lo, _    = _clamp(float(np.min(v_vals)), 20, 0, 0, 255)
        s_hi = 253
        v_hi = 255

        self.hsv_range = ((h_lo, s_lo, v_lo), (h_hi, s_hi, v_hi))
        return self.hsv_range

    # ── Core: phát hiện line ─────────────────────────────────────────────
    def detect(self, frame_bgr):
        """
        Trả về DetectResult.
        """
        result = _DetectResult()
        if self.hsv_range is None:
            result.frame = frame_bgr
            return result

        img = cv2.resize(frame_bgr, (self.frame_width, self.frame_height))
        result.frame = img.copy()

        # Che phần trên (robot chỉ quan tâm đường phía trước ở dưới)
        roi_img = img.copy()
        cut_y = int(self.frame_height * self.roi_top_fraction)
        roi_img[:cut_y, :] = 0

        # BGR → HSV → mask → morphology → binary
        hsv   = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
        lo    = np.array(self.hsv_range[0], dtype=np.uint8)
        hi    = np.array(self.hsv_range[1], dtype=np.uint8)
        mask  = cv2.inRange(hsv, lo, hi)
        color_mask = cv2.bitwise_and(hsv, hsv, mask=mask)
        gray  = cv2.cvtColor(color_mask, cv2.COLOR_BGR2GRAY)
        gray  = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, self._kernel)
        _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
        result.binary = binary

        # Tìm contour lớn nhất
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return result

        # Lọc theo diện tích tối thiểu
        valid = [c for c in contours if cv2.contourArea(c) >= self.min_contour_area]
        if not valid:
            return result

        largest = max(valid, key=cv2.contourArea)
        rect    = cv2.minAreaRect(largest)
        box     = np.int32(cv2.boxPoints(rect))
        (cx, cy), radius = cv2.minEnclosingCircle(box)
        cx, cy, radius = int(cx), int(cy), int(radius)

        # Annotate frame
        cv2.drawContours(result.frame, [box], 0, (255, 0, 0), 2)
        cv2.circle(result.frame, (cx, cy), 5, (255, 0, 255), -1)
        cv2.line(result.frame, (self.frame_width // 2, 0),
                 (self.frame_width // 2, self.frame_height), (0, 255, 0), 1)

        result.circle = (cx, cy, radius)
        result.error_x = cx - self.frame_width // 2
        return result


class _DetectResult:
    """Kết quả phát hiện line."""
    def __init__(self):
        self.circle  = None          # (cx, cy, radius) hoặc None
        self.error_x = 0             # pixel lệch (âm=trái, dương=phải)
        self.frame   = None          # frame đã annotate (numpy array)
        self.binary  = None          # binary mask để debug
