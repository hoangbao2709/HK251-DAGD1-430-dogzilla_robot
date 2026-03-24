import cv2
import numpy as np
import threading
import time

from config import (
    CAMERA_INDEX,
    CAMERA_SOURCE,
    USE_REMOTE_CAMERA,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    ROI_TOP_RATIO,
    SEARCH_WINDOW_HALF_WIDTH,
    JUNCTION_WINDOW_HALF_WIDTH,
    BOTTOM_SCAN_RATIO,
    TOP_SCAN_RATIO,
    KP,
    KD,
    LINEAR_SPEED,
    MAX_ANGULAR,
    SMOOTHING_ALPHA_NORMAL,
    SMOOTHING_ALPHA_JUNCTION,
    JUNCTION_SPEED_SCALE,
)
from image_utils import build_mask, get_segments_on_row, filter_segments_in_window


MID_SCAN_RATIO = 0.58
TURN_BIAS_PIXELS = 120
CROSS_BIAS_PIXELS = 220
JUNCTION_HOLD_FRAMES = 14


class LineTrackingServer:
    def __init__(self):
        self.lock = threading.Lock()

        self.cap = None
        self.running = False

        self.frame = None
        self.annotated_frame = None

        self.turn_choice = "straight"

        self.prev_error = 0.0
        self.prev_target_x = None
        self.prev_target_y = None

        self.waiting_at_junction = False
        self.junction_hold_frames = 0
        self.turn_state = "follow"   # follow | prepare_turn | turning

        self.result = {
            "found": False,
            "junction": False,
            "cross": False,
            "waiting_at_junction": False,
            "turn_choice": self.turn_choice,
            "target_x": None,
            "target_y": None,
            "error": 0.0,
            "linear_x": 0.0,
            "angular_z": 0.0,
            "base_center": None,
            "mode": "idle",
            "turn_state": self.turn_state,
        }

    def set_turn_choice(self, choice):
        if choice in ["left", "straight", "right"]:
            with self.lock:
                self.turn_choice = choice

    def start_camera(self):
        if USE_REMOTE_CAMERA:
            self.cap = cv2.VideoCapture(CAMERA_SOURCE)
        else:
            self.cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

        if not self.cap.isOpened():
            source_info = CAMERA_SOURCE if USE_REMOTE_CAMERA else CAMERA_INDEX
            raise RuntimeError(f"Không mở được camera với source: {source_info}")

        if not USE_REMOTE_CAMERA:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        time.sleep(1.0)

        ok, frame = self.cap.read()
        if not ok or frame is None:
            self.cap.release()
            source_info = CAMERA_SOURCE if USE_REMOTE_CAMERA else CAMERA_INDEX
            raise RuntimeError(f"Mở được camera nhưng không đọc được frame từ source: {source_info}")

        print("Camera opened successfully")
        print("Camera source:", CAMERA_SOURCE if USE_REMOTE_CAMERA else CAMERA_INDEX)
        print("Test frame shape:", frame.shape)

        self.frame = frame.copy()
        self.annotated_frame = frame.copy()

        self.running = True
        threading.Thread(target=self.update_loop, daemon=True).start()

    def smooth_target(self, raw_x, raw_y, special_zone):
        if raw_x is None or raw_y is None:
            self.prev_target_x = None
            self.prev_target_y = None
            return None, None

        alpha = SMOOTHING_ALPHA_JUNCTION if special_zone else SMOOTHING_ALPHA_NORMAL

        if self.prev_target_x is None:
            smooth_x = raw_x
        else:
            smooth_x = int(alpha * self.prev_target_x + (1.0 - alpha) * raw_x)

        if self.prev_target_y is None:
            smooth_y = raw_y
        else:
            smooth_y = int(alpha * self.prev_target_y + (1.0 - alpha) * raw_y)

        self.prev_target_x = smooth_x
        self.prev_target_y = smooth_y

        return smooth_x, smooth_y

    def detect_structure(self, seg_top, seg_mid, seg_bottom, image_center):
        """
        Phân biệt:
        - normal line
        - junction
        - cross intersection
        """
        junction = False
        cross = False

        if len(seg_top) >= 2:
            junction = True

        # dấu hiệu ngã tư: giữa ảnh có thanh ngang rộng + dưới vẫn có thân dọc
        if len(seg_mid) >= 2 and len(seg_bottom) >= 1:
            cross = True
            junction = True

        # nếu có 1 segment giữa rất rộng cũng xem như giao cắt
        for x1, x2, cx in seg_mid:
            if (x2 - x1) > 220:
                cross = True
                junction = True
                break

        return junction, cross

    def choose_branch_segment(self, segments, turn_choice, image_center):
        if not segments:
            return None

        segments = sorted(segments, key=lambda s: s[2])

        if turn_choice == "left":
            return segments[0]
        if turn_choice == "right":
            return segments[-1]
        return min(segments, key=lambda s: abs(s[2] - image_center))

    def choose_target_point(self, mask, turn_choice):
        h, w = mask.shape[:2]
        image_center = w // 2

        y_bottom = int(h * BOTTOM_SCAN_RATIO)
        y_mid = int(h * MID_SCAN_RATIO)
        y_top = int(h * TOP_SCAN_RATIO)

        seg_bottom_all = get_segments_on_row(mask, y_bottom)
        seg_mid_all = get_segments_on_row(mask, y_mid)
        seg_top_all = get_segments_on_row(mask, y_top)

        if self.prev_target_x is not None:
            base_center = int(self.prev_target_x)
        else:
            base_center = image_center

        seg_bottom = filter_segments_in_window(
            seg_bottom_all, base_center, SEARCH_WINDOW_HALF_WIDTH
        )
        if not seg_bottom and seg_bottom_all:
            seg_bottom = seg_bottom_all

        seg_mid = filter_segments_in_window(
            seg_mid_all, base_center, JUNCTION_WINDOW_HALF_WIDTH
        )
        if not seg_mid and seg_mid_all:
            seg_mid = seg_mid_all

        seg_top = filter_segments_in_window(
            seg_top_all, base_center, JUNCTION_WINDOW_HALF_WIDTH
        )
        if not seg_top and seg_top_all:
            seg_top = seg_top_all

        bottom_choice = None
        if seg_bottom:
            bottom_choice = min(seg_bottom, key=lambda s: abs(s[2] - base_center))

        junction_detected, cross_detected = self.detect_structure(
            seg_top, seg_mid, seg_bottom, image_center
        )

        top_choice = self.choose_branch_segment(seg_top, turn_choice, image_center)

        target_x = None
        target_y = None

        # ===== CASE 1: bình thường =====
        if not junction_detected:
            if bottom_choice is not None:
                target_x = int(bottom_choice[2])
                target_y = int(y_bottom)

        # ===== CASE 2: ngã rẽ / chữ Y =====
        elif junction_detected and not cross_detected:
            if top_choice is not None and bottom_choice is not None:
                if turn_choice in ["left", "right"]:
                    alpha = 0.78
                else:
                    alpha = 0.58

                target_x = int(alpha * top_choice[2] + (1.0 - alpha) * bottom_choice[2])
                target_y = int(alpha * y_top + (1.0 - alpha) * y_bottom)
            elif top_choice is not None:
                target_x = int(top_choice[2])
                target_y = int(y_top)
            elif bottom_choice is not None:
                target_x = int(bottom_choice[2])
                target_y = int(y_bottom)

        # ===== CASE 3: ngã tư =====
        else:
            # nếu rẽ phải / trái thì phải tạo bias mạnh
            if bottom_choice is not None:
                base_x = bottom_choice[2]
            else:
                base_x = base_center

            if turn_choice == "right":
                if self.turn_state == "follow":
                    target_x = int(base_x + TURN_BIAS_PIXELS)
                    self.turn_state = "prepare_turn"
                else:
                    target_x = int(base_x + CROSS_BIAS_PIXELS)
                    self.turn_state = "turning"

                target_x = min(w - 1, target_x)
                target_y = int(y_mid)

            elif turn_choice == "left":
                if self.turn_state == "follow":
                    target_x = int(base_x - TURN_BIAS_PIXELS)
                    self.turn_state = "prepare_turn"
                else:
                    target_x = int(base_x - CROSS_BIAS_PIXELS)
                    self.turn_state = "turning"

                target_x = max(0, target_x)
                target_y = int(y_mid)

            else:
                # đi thẳng thì vẫn bám giữa
                if bottom_choice is not None:
                    target_x = int(bottom_choice[2])
                    target_y = int(y_bottom)
                elif top_choice is not None:
                    target_x = int(top_choice[2])
                    target_y = int(y_top)

        # clamp bình thường
        if target_x is not None and not junction_detected:
            x_min = max(0, base_center - SEARCH_WINDOW_HALF_WIDTH)
            x_max = min(w - 1, base_center + SEARCH_WINDOW_HALF_WIDTH)
            target_x = int(np.clip(target_x, x_min, x_max))

        return {
            "target_x": target_x,
            "target_y": target_y,
            "junction": junction_detected,
            "cross": cross_detected,
            "seg_top": seg_top,
            "seg_mid": seg_mid,
            "seg_bottom": seg_bottom,
            "base_center": base_center,
            "y_top": y_top,
            "y_mid": y_mid,
            "y_bottom": y_bottom,
            "image_center": image_center,
        }

    def compute_control(self, roi_width, target_x, special_zone):
        center_x = roi_width / 2.0
        error = (target_x - center_x) / center_x
        d_error = error - self.prev_error
        self.prev_error = error

        angular_z = float(np.clip(-(KP * error + KD * d_error), -MAX_ANGULAR, MAX_ANGULAR))

        if special_zone:
            angular_z = float(np.clip(angular_z * 1.20, -MAX_ANGULAR, MAX_ANGULAR))
            base_speed = LINEAR_SPEED * JUNCTION_SPEED_SCALE
            mode = "junction"
        else:
            base_speed = LINEAR_SPEED
            mode = "follow"

        linear_x = float(base_speed * max(0.35, 1.0 - abs(error) * 0.7))

        return {
            "error": float(error),
            "linear_x": linear_x,
            "angular_z": angular_z,
            "mode": mode,
        }

    def draw_segments(self, roi, segs, y, color_line, color_dot):
        for x1, x2, cx in segs:
            cv2.line(roi, (x1, y), (x2, y), color_line, 3)
            cv2.circle(roi, (cx, y), 4, color_dot, -1)

    def draw_windows(self, roi, base_center):
        h, w = roi.shape[:2]

        normal_left = max(0, base_center - SEARCH_WINDOW_HALF_WIDTH)
        normal_right = min(w - 1, base_center + SEARCH_WINDOW_HALF_WIDTH)

        junction_left = max(0, base_center - JUNCTION_WINDOW_HALF_WIDTH)
        junction_right = min(w - 1, base_center + JUNCTION_WINDOW_HALF_WIDTH)

        cv2.line(roi, (normal_left, 0), (normal_left, h), (180, 180, 180), 1)
        cv2.line(roi, (normal_right, 0), (normal_right, h), (180, 180, 180), 1)

        cv2.line(roi, (junction_left, 0), (junction_left, h), (80, 200, 255), 1)
        cv2.line(roi, (junction_right, 0), (junction_right, h), (80, 200, 255), 1)

    def process_frame(self, frame):
        original = frame.copy()
        annotated = frame.copy()

        h, w = annotated.shape[:2]
        roi_start = int(h * ROI_TOP_RATIO)
        roi = annotated[roi_start:h, :]

        mask = build_mask(roi)

        choice_info = self.choose_target_point(mask, self.turn_choice)

        raw_target_x = choice_info["target_x"]
        raw_target_y = choice_info["target_y"]
        junction_detected = choice_info["junction"]
        cross_detected = choice_info["cross"]
        seg_top = choice_info["seg_top"]
        seg_mid = choice_info["seg_mid"]
        seg_bottom = choice_info["seg_bottom"]
        base_center = choice_info["base_center"]
        y_top = choice_info["y_top"]
        y_mid = choice_info["y_mid"]
        y_bottom = choice_info["y_bottom"]
        image_center = choice_info["image_center"]

        if junction_detected:
            self.junction_hold_frames = JUNCTION_HOLD_FRAMES
        else:
            self.junction_hold_frames = max(0, self.junction_hold_frames - 1)
            if self.junction_hold_frames == 0:
                self.turn_state = "follow"

        effective_special = junction_detected or (self.junction_hold_frames > 0)
        self.waiting_at_junction = effective_special

        smooth_target_x, smooth_target_y = self.smooth_target(
            raw_target_x, raw_target_y, effective_special
        )

        result = {
            "found": False,
            "junction": effective_special,
            "cross": cross_detected,
            "waiting_at_junction": effective_special,
            "turn_choice": self.turn_choice,
            "target_x": None,
            "target_y": None,
            "error": 0.0,
            "linear_x": 0.0,
            "angular_z": 0.0,
            "base_center": int(base_center),
            "mode": "search",
            "turn_state": self.turn_state,
        }

        cv2.rectangle(annotated, (0, roi_start), (w, h), (255, 255, 0), 2)
        cv2.line(annotated, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)

        cv2.line(roi, (0, y_bottom), (roi.shape[1], y_bottom), (255, 0, 255), 1)
        cv2.line(roi, (0, y_mid), (roi.shape[1], y_mid), (0, 255, 255), 1)
        cv2.line(roi, (0, y_top), (roi.shape[1], y_top), (0, 165, 255), 1)

        self.draw_windows(roi, base_center)
        self.draw_segments(roi, seg_bottom, y_bottom, (255, 0, 255), (255, 0, 255))
        self.draw_segments(roi, seg_mid, y_mid, (0, 255, 255), (0, 255, 255))
        self.draw_segments(roi, seg_top, y_top, (0, 165, 255), (0, 165, 255))
        cv2.line(roi, (image_center, 0), (image_center, roi.shape[0]), (255, 0, 0), 2)

        if smooth_target_x is not None and smooth_target_y is not None:
            control = self.compute_control(roi.shape[1], smooth_target_x, effective_special)

            result = {
                "found": True,
                "junction": effective_special,
                "cross": cross_detected,
                "waiting_at_junction": effective_special,
                "turn_choice": self.turn_choice,
                "target_x": int(smooth_target_x),
                "target_y": int(smooth_target_y + roi_start),
                "error": control["error"],
                "linear_x": control["linear_x"],
                "angular_z": control["angular_z"],
                "base_center": int(base_center),
                "mode": control["mode"],
                "turn_state": self.turn_state,
            }

            if raw_target_x is not None and raw_target_y is not None:
                cv2.circle(roi, (raw_target_x, raw_target_y), 5, (0, 0, 255), -1)

            cv2.circle(roi, (smooth_target_x, smooth_target_y), 10, (255, 255, 255), 2)
            cv2.circle(roi, (smooth_target_x, smooth_target_y), 3, (0, 255, 0), -1)

            cv2.putText(
                annotated,
                f"FOUND | err={control['error']:.3f} lin={control['linear_x']:.3f} ang={control['angular_z']:.3f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2,
            )
            cv2.putText(
                annotated,
                f"target=({smooth_target_x},{smooth_target_y}) cross={cross_detected} state={self.turn_state}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 255),
                2,
            )
        else:
            self.prev_error = 0.0
            cv2.putText(
                annotated,
                "LINE NOT FOUND",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )

        cv2.putText(
            annotated,
            f"TURN: {self.turn_choice.upper()}",
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

        return original, annotated, result

    def update_loop(self):
        fail_count = 0

        while self.running:
            ret, frame = self.cap.read()

            if not ret or frame is None:
                fail_count += 1
                if fail_count % 10 == 1:
                    print(f"[WARN] Không đọc được frame. fail_count={fail_count}")

                if USE_REMOTE_CAMERA and fail_count >= 20:
                    print("[INFO] Thử reconnect camera stream...")
                    try:
                        self.cap.release()
                    except Exception:
                        pass

                    time.sleep(1.0)
                    self.cap = cv2.VideoCapture(CAMERA_SOURCE)
                    fail_count = 0

                time.sleep(0.05)
                continue

            fail_count = 0
            raw_frame, annotated, result = self.process_frame(frame)

            with self.lock:
                self.frame = raw_frame
                self.annotated_frame = annotated
                self.result = result

            time.sleep(0.02)