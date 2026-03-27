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
    MID_SCAN_RATIO,
    TOP_SCAN_RATIO,
    KP,
    KD,
    LINEAR_SPEED,
    MAX_ANGULAR,
    SMOOTHING_ALPHA_NORMAL,
    SMOOTHING_ALPHA_JUNCTION,
    TURNING_SMOOTHING_ALPHA,
    JUNCTION_SPEED_SCALE,
    ERROR_DEADBAND_PX,
    ERROR_SMOOTH_ALPHA,
    MAX_ANGULAR_STEP,
    APPROACH_BIAS_PIXELS,
    PREPARE_BIAS_PIXELS,
    TURN_BIAS_PIXELS,
    APPROACH_HOLD_FRAMES,
    JUNCTION_HOLD_FRAMES,
    COMMIT_TURN_FRAMES,
    LINE_WIDTH_APPROACH_RATIO,
    MID_WIDTH_APPROACH_RATIO,
    TOP_LOST_MIN_FRAMES,
    CROSS_WIDE_THRESHOLD,
    APPROACH_SPEED_SCALE,
    TURN_SPEED_SCALE,
    COMMIT_LINEAR_SCALE,
)
from image_utils import build_mask, get_segments_on_row, filter_segments_in_window


class LineTrackingServer:
    def __init__(self):
        self.lock = threading.Lock()

        self.cap = None
        self.running = False

        self.frame = None
        self.annotated_frame = None

        self.turn_choice = "straight"

        self.prev_error = 0.0
        self.prev_smooth_error = 0.0
        self.prev_angular_z = 0.0

        self.prev_target_x = None
        self.prev_target_y = None
        self.prev_target_vx = 0.0
        self.prev_target_vy = 0.0

        self.last_good_target_x = None
        self.last_good_target_y = None
        self.last_good_time = 0.0

        self.waiting_at_junction = False

        self.junction_hold_frames = 0
        self.approach_hold_frames = 0
        self.commit_turn_frames = 0
        self.top_lost_frames = 0
        self.line_lost_frames = 0

        self.normal_line_width = None
        self.turn_state = "follow"

        self.result = {
            "found": False,
            "junction": False,
            "cross": False,
            "approach": False,
            "waiting_at_junction": False,
            "turn_choice": self.turn_choice,
            "target_x": None,
            "target_y": None,
            "error": 0.0,
            "error_px": 0,
            "linear_x": 0.0,
            "angular_z": 0.0,
            "base_center": None,
            "mode": "idle",
            "turn_state": self.turn_state,
            "action_label": "STOP",
            "confidence": 0.0,
        }

    def set_turn_choice(self, choice):
        if choice in ["left", "straight", "right"]:
            with self.lock:
                self.turn_choice = choice
                if choice == "straight" and self.commit_turn_frames == 0:
                    self.turn_state = "follow"

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

    def _predict_center(self, image_center):
        if self.prev_target_x is None:
            return image_center
        pred = self.prev_target_x + self.prev_target_vx * 1.2
        return int(pred)

    def _segment_width(self, seg):
        return int(seg[1] - seg[0] + 1)

    def _segment_score(self, seg, ref_x, prefer_side=None, image_center=None):
        x1, x2, cx = seg
        width = self._segment_width(seg)

        dist_score = abs(cx - ref_x) * 1.0

        width_penalty = 0.0
        if self.normal_line_width is not None and self.normal_line_width > 1:
            ratio = width / max(self.normal_line_width, 1.0)
            if ratio < 0.45:
                width_penalty += 45.0
            elif ratio > 2.4:
                width_penalty += min(120.0, (ratio - 2.4) * 80.0)

        huge_penalty = 0.0
        if width >= CROSS_WIDE_THRESHOLD:
            huge_penalty += 90.0

        side_bonus = 0.0
        if prefer_side == "left" and image_center is not None:
            side_bonus = -55.0 if cx < image_center else 35.0
        elif prefer_side == "right" and image_center is not None:
            side_bonus = -55.0 if cx > image_center else 35.0

        return dist_score + width_penalty + huge_penalty + side_bonus

    def _pick_best_segment(self, segments, ref_x, prefer_side=None, image_center=None):
        if not segments:
            return None
        return min(
            segments,
            key=lambda seg: self._segment_score(seg, ref_x, prefer_side, image_center),
        )

    def _update_normal_line_width(self, seg_bottom, base_center):
        if not seg_bottom:
            return

        main_seg = self._pick_best_segment(seg_bottom, base_center)
        if main_seg is None:
            return

        width = self._segment_width(main_seg)
        if width <= 0:
            return

        if self.normal_line_width is None:
            self.normal_line_width = float(width)
        else:
            self.normal_line_width = 0.94 * self.normal_line_width + 0.06 * width

    def _filter_suspicious_segments(self, segments, base_center, image_center, window_half_width):
        if not segments:
            return []

        filtered = []
        for seg in segments:
            width = self._segment_width(seg)
            cx = seg[2]

            if width < 6:
                continue

            if width > max(CROSS_WIDE_THRESHOLD * 1.35, 360):
                continue

            if self.normal_line_width is not None:
                ratio = width / max(self.normal_line_width, 1.0)
                if ratio > 3.2 and abs(cx - base_center) > window_half_width * 0.85:
                    continue

            if abs(cx - image_center) > image_center + 20:
                continue

            filtered.append(seg)

        return filtered

    def detect_structure(self, seg_top, seg_mid, seg_bottom, image_center):
        junction = False
        cross = False

        if len(seg_top) >= 2:
            junction = True

        if len(seg_mid) >= 2 and len(seg_bottom) >= 1:
            junction = True
            left_count = sum(1 for s in seg_mid if s[2] < image_center)
            right_count = sum(1 for s in seg_mid if s[2] > image_center)
            if left_count > 0 and right_count > 0:
                cross = True

        for x1, x2, cx in seg_mid:
            if (x2 - x1 + 1) >= CROSS_WIDE_THRESHOLD:
                junction = True
                cross = True
                break

        return junction, cross

    def detect_approach_turn(self, seg_top, seg_mid, seg_bottom, base_center, turn_choice):
        if turn_choice == "straight":
            self.top_lost_frames = 0
            return False

        if not seg_bottom:
            self.top_lost_frames = 0
            return False

        bottom_main = self._pick_best_segment(seg_bottom, base_center)
        mid_main = self._pick_best_segment(seg_mid, base_center) if seg_mid else None

        bottom_w = self._segment_width(bottom_main) if bottom_main is not None else 0
        mid_w = self._segment_width(mid_main) if mid_main is not None else 0

        if len(seg_top) == 0:
            self.top_lost_frames += 1
        else:
            self.top_lost_frames = 0

        normal_w = self.normal_line_width or max(bottom_w, 1)
        width_expand = bottom_w > normal_w * LINE_WIDTH_APPROACH_RATIO
        mid_expand = mid_w > 0 and mid_w > normal_w * MID_WIDTH_APPROACH_RATIO
        top_lost = self.top_lost_frames >= TOP_LOST_MIN_FRAMES

        return width_expand or mid_expand or top_lost

    def _choose_branch_segment(self, segments, turn_choice, image_center, ref_x):
        if not segments:
            return None

        ordered = sorted(segments, key=lambda s: s[2])

        if turn_choice == "left":
            left_side = [s for s in ordered if s[2] < image_center]
            if left_side:
                return self._pick_best_segment(left_side, ref_x, "left", image_center)
            return ordered[0]

        if turn_choice == "right":
            right_side = [s for s in ordered if s[2] > image_center]
            if right_side:
                return self._pick_best_segment(right_side, ref_x, "right", image_center)
            return ordered[-1]

        return self._pick_best_segment(ordered, image_center, None, image_center)

    def _fuse_target(self, bottom_choice, mid_choice, top_choice, y_bottom, y_mid, y_top, turn_choice, state_hint, w):
        pts = []

        if bottom_choice is not None:
            pts.append((bottom_choice[2], y_bottom, 0.52))
        if mid_choice is not None:
            pts.append((mid_choice[2], y_mid, 0.28))
        if top_choice is not None:
            pts.append((top_choice[2], y_top, 0.20))

        if not pts:
            return None, None

        if state_hint == "approach_turn":
            if turn_choice == "left":
                pts.append((max(0, pts[0][0] - APPROACH_BIAS_PIXELS), y_mid, 0.30))
            elif turn_choice == "right":
                pts.append((min(w - 1, pts[0][0] + APPROACH_BIAS_PIXELS), y_mid, 0.30))

        elif state_hint == "prepare_turn":
            if top_choice is not None:
                if turn_choice == "left":
                    pts.append((max(0, top_choice[2] - PREPARE_BIAS_PIXELS), y_top, 0.55))
                elif turn_choice == "right":
                    pts.append((min(w - 1, top_choice[2] + PREPARE_BIAS_PIXELS), y_top, 0.55))

        elif state_hint == "turning":
            base_x = bottom_choice[2] if bottom_choice is not None else (mid_choice[2] if mid_choice is not None else top_choice[2])
            if turn_choice == "left":
                pts.append((max(0, base_x - TURN_BIAS_PIXELS), y_mid, 0.95))
            elif turn_choice == "right":
                pts.append((min(w - 1, base_x + TURN_BIAS_PIXELS), y_mid, 0.95))

        weight_sum = sum(p[2] for p in pts)
        tx = int(sum(p[0] * p[2] for p in pts) / max(weight_sum, 1e-6))
        ty = int(sum(p[1] * p[2] for p in pts) / max(weight_sum, 1e-6))
        return tx, ty

    def choose_target_point(self, mask, turn_choice):
        h, w = mask.shape[:2]
        image_center = w // 2

        y_bottom = int(h * BOTTOM_SCAN_RATIO)
        y_mid = int(h * MID_SCAN_RATIO)
        y_top = int(h * TOP_SCAN_RATIO)

        pred_center = self._predict_center(image_center)
        base_center = int(np.clip(pred_center, 0, w - 1))

        seg_bottom_all = get_segments_on_row(mask, y_bottom)
        seg_mid_all = get_segments_on_row(mask, y_mid)
        seg_top_all = get_segments_on_row(mask, y_top)

        seg_bottom_all = self._filter_suspicious_segments(
            seg_bottom_all, base_center, image_center, SEARCH_WINDOW_HALF_WIDTH
        )
        seg_mid_all = self._filter_suspicious_segments(
            seg_mid_all, base_center, image_center, JUNCTION_WINDOW_HALF_WIDTH
        )
        seg_top_all = self._filter_suspicious_segments(
            seg_top_all, base_center, image_center, JUNCTION_WINDOW_HALF_WIDTH
        )

        seg_bottom = filter_segments_in_window(seg_bottom_all, base_center, SEARCH_WINDOW_HALF_WIDTH)
        if not seg_bottom and seg_bottom_all:
            seg_bottom = seg_bottom_all

        seg_mid = filter_segments_in_window(seg_mid_all, base_center, JUNCTION_WINDOW_HALF_WIDTH)
        if not seg_mid and seg_mid_all:
            seg_mid = seg_mid_all

        seg_top = filter_segments_in_window(seg_top_all, base_center, JUNCTION_WINDOW_HALF_WIDTH)
        if not seg_top and seg_top_all:
            seg_top = seg_top_all

        self._update_normal_line_width(seg_bottom, base_center)

        bottom_choice = self._pick_best_segment(seg_bottom, base_center, None, image_center)
        mid_choice = self._pick_best_segment(seg_mid, base_center, None, image_center)

        junction_detected, cross_detected = self.detect_structure(seg_top, seg_mid, seg_bottom, image_center)
        approach_detected = self.detect_approach_turn(
            seg_top, seg_mid, seg_bottom, base_center, turn_choice
        )

        if junction_detected:
            top_choice = self._choose_branch_segment(seg_top, turn_choice, image_center, base_center)
        else:
            top_choice = self._pick_best_segment(seg_top, base_center, None, image_center)

        state_hint = "follow"

        if cross_detected and turn_choice in ("left", "right"):
            state_hint = "turning"
        elif junction_detected and turn_choice in ("left", "right"):
            state_hint = "prepare_turn"
        elif approach_detected and turn_choice in ("left", "right"):
            state_hint = "approach_turn"

        target_x, target_y = self._fuse_target(
            bottom_choice, mid_choice, top_choice,
            y_bottom, y_mid, y_top,
            turn_choice, state_hint, w
        )

        if target_x is not None and state_hint == "follow" and not junction_detected:
            x_min = max(0, base_center - SEARCH_WINDOW_HALF_WIDTH)
            x_max = min(w - 1, base_center + SEARCH_WINDOW_HALF_WIDTH)
            target_x = int(np.clip(target_x, x_min, x_max))

        support_count = int(bottom_choice is not None) + int(mid_choice is not None) + int(top_choice is not None)
        confidence = 0.0
        if support_count == 1:
            confidence = 0.45
        elif support_count == 2:
            confidence = 0.72
        elif support_count >= 3:
            confidence = 0.92

        if junction_detected:
            confidence = min(1.0, confidence + 0.04)

        return {
            "target_x": target_x,
            "target_y": target_y,
            "junction": junction_detected,
            "cross": cross_detected,
            "approach": approach_detected,
            "seg_top": seg_top,
            "seg_mid": seg_mid,
            "seg_bottom": seg_bottom,
            "base_center": base_center,
            "y_top": y_top,
            "y_mid": y_mid,
            "y_bottom": y_bottom,
            "image_center": image_center,
            "state_hint": state_hint,
            "confidence": float(confidence),
        }

    def smooth_target(self, raw_x, raw_y, turn_state):
        if raw_x is None or raw_y is None:
            return None, None

        if turn_state in ("prepare_turn", "turning", "commit_turn"):
            alpha = TURNING_SMOOTHING_ALPHA
        elif turn_state == "approach_turn":
            alpha = min(0.84, SMOOTHING_ALPHA_JUNCTION)
        elif turn_state != "follow":
            alpha = SMOOTHING_ALPHA_JUNCTION
        else:
            alpha = SMOOTHING_ALPHA_NORMAL

        if self.prev_target_x is None:
            smooth_x = int(raw_x)
            smooth_y = int(raw_y)
        else:
            smooth_x = int(alpha * self.prev_target_x + (1.0 - alpha) * raw_x)
            smooth_y = int(alpha * self.prev_target_y + (1.0 - alpha) * raw_y)

        self.prev_target_vx = 0.80 * self.prev_target_vx + 0.20 * (smooth_x - (self.prev_target_x if self.prev_target_x is not None else smooth_x))
        self.prev_target_vy = 0.80 * self.prev_target_vy + 0.20 * (smooth_y - (self.prev_target_y if self.prev_target_y is not None else smooth_y))

        self.prev_target_x = smooth_x
        self.prev_target_y = smooth_y

        self.last_good_target_x = smooth_x
        self.last_good_target_y = smooth_y
        self.last_good_time = time.time()

        return smooth_x, smooth_y

    def _recover_target_when_lost(self, roi_w, roi_h):
        if self.last_good_target_x is None or self.last_good_target_y is None:
            return None, None

        if self.line_lost_frames > 8:
            return None, None

        rx = int(np.clip(self.last_good_target_x + self.prev_target_vx * min(self.line_lost_frames, 4), 0, roi_w - 1))
        ry = int(np.clip(self.last_good_target_y + self.prev_target_vy * min(self.line_lost_frames, 4), 0, roi_h - 1))
        return rx, ry

    def compute_action_label(self, error):
        ae = abs(error)
        if ae < 0.05:
            return "STRAIGHT"
        if error > 0.24:
            return "RIGHT_HARD"
        if error > 0.10:
            return "RIGHT_SOFT"
        if error < -0.24:
            return "LEFT_HARD"
        if error < -0.10:
            return "LEFT_SOFT"
        return "STRAIGHT"

    def compute_control(self, roi_width, target_x, turn_state):
        center_x = roi_width / 2.0

        # luôn khởi tạo error_px trước khi dùng
        error_px = int(target_x - center_x)

        if abs(error_px) <= ERROR_DEADBAND_PX:
            error_px = 0

        raw_error = error_px / max(center_x, 1.0)
        error = ERROR_SMOOTH_ALPHA * self.prev_smooth_error + (1.0 - ERROR_SMOOTH_ALPHA) * raw_error
        d_error = error - self.prev_error

        self.prev_error = error
        self.prev_smooth_error = error

        angular_z = -(KP * error + KD * d_error)

        if turn_state == "approach_turn":
            angular_z *= 1.10
            base_speed = LINEAR_SPEED * APPROACH_SPEED_SCALE
            mode = "approach"
        elif turn_state in ("prepare_turn", "turning", "commit_turn"):
            angular_z *= 1.22
            base_speed = LINEAR_SPEED * TURN_SPEED_SCALE
            mode = "turn"
        elif turn_state != "follow":
            angular_z *= 1.10
            base_speed = LINEAR_SPEED * JUNCTION_SPEED_SCALE
            mode = "junction"
        else:
            base_speed = LINEAR_SPEED
            mode = "follow"

        angular_z = float(np.clip(angular_z, -MAX_ANGULAR, MAX_ANGULAR))

        delta = angular_z - self.prev_angular_z
        delta = float(np.clip(delta, -MAX_ANGULAR_STEP, MAX_ANGULAR_STEP))
        angular_z = float(np.clip(self.prev_angular_z + delta, -MAX_ANGULAR, MAX_ANGULAR))
        self.prev_angular_z = angular_z

        ae_px = abs(error_px)

        if turn_state in ("prepare_turn", "turning", "commit_turn"):
            if ae_px < 30:
                linear_scale = 0.62
            elif ae_px < 70:
                linear_scale = 0.48
            elif ae_px < 120:
                linear_scale = 0.34
            else:
                linear_scale = 0.22
        else:
            if ae_px < 18:
                linear_scale = 1.00
            elif ae_px < 40:
                linear_scale = 0.72
            elif ae_px < 70:
                linear_scale = 0.48
            elif ae_px < 110:
                linear_scale = 0.28
            else:
                linear_scale = 0.12

        linear_x = float(base_speed * linear_scale)
        action_label = self.compute_action_label(error)

        return {
            "error": float(error),
            "error_px": int(error_px),
            "linear_x": linear_x,
            "angular_z": angular_z,
            "mode": mode,
            "action_label": action_label,
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
        roi_h, roi_w = roi.shape[:2]

        mask = build_mask(roi)
        choice_info = self.choose_target_point(mask, self.turn_choice)

        raw_target_x = choice_info["target_x"]
        raw_target_y = choice_info["target_y"]
        junction_detected = choice_info["junction"]
        cross_detected = choice_info["cross"]
        approach_detected = choice_info["approach"]
        confidence = choice_info["confidence"]

        seg_top = choice_info["seg_top"]
        seg_mid = choice_info["seg_mid"]
        seg_bottom = choice_info["seg_bottom"]

        base_center = choice_info["base_center"]
        y_top = choice_info["y_top"]
        y_mid = choice_info["y_mid"]
        y_bottom = choice_info["y_bottom"]
        image_center = choice_info["image_center"]
        state_hint = choice_info["state_hint"]

        if approach_detected and self.turn_choice in ("left", "right"):
            self.approach_hold_frames = APPROACH_HOLD_FRAMES
        else:
            self.approach_hold_frames = max(0, self.approach_hold_frames - 1)

        if junction_detected:
            self.junction_hold_frames = JUNCTION_HOLD_FRAMES
        else:
            self.junction_hold_frames = max(0, self.junction_hold_frames - 1)

        if state_hint == "turning" and self.turn_choice in ("left", "right"):
            self.commit_turn_frames = max(self.commit_turn_frames, COMMIT_TURN_FRAMES)

        if self.commit_turn_frames > 0:
            self.commit_turn_frames -= 1

        if self.turn_choice in ("left", "right"):
            if state_hint in ("approach_turn", "prepare_turn", "turning"):
                self.turn_state = state_hint
            elif self.commit_turn_frames > 0 and state_hint == "follow":
                self.turn_state = "commit_turn"
            elif self.junction_hold_frames == 0 and self.approach_hold_frames == 0 and self.commit_turn_frames == 0:
                self.turn_state = "follow"
        else:
            if self.junction_hold_frames == 0 and self.approach_hold_frames == 0 and self.commit_turn_frames == 0:
                self.turn_state = "follow"

        effective_special = (
            junction_detected
            or cross_detected
            or (self.approach_hold_frames > 0)
            or (self.junction_hold_frames > 0)
            or (self.commit_turn_frames > 0 and self.turn_choice in ("left", "right"))
        )

        self.waiting_at_junction = effective_special

        smooth_target_x, smooth_target_y = None, None
        recovered = False

        if raw_target_x is not None and raw_target_y is not None:
            self.line_lost_frames = 0
            smooth_target_x, smooth_target_y = self.smooth_target(raw_target_x, raw_target_y, self.turn_state)
        else:
            self.line_lost_frames += 1
            recovered_x, recovered_y = self._recover_target_when_lost(roi_w, roi_h)
            if recovered_x is not None and recovered_y is not None and self.commit_turn_frames == 0:
                smooth_target_x, smooth_target_y = recovered_x, recovered_y
                recovered = True

        result = {
            "found": False,
            "junction": effective_special,
            "cross": cross_detected,
            "approach": approach_detected or (self.approach_hold_frames > 0),
            "waiting_at_junction": effective_special,
            "turn_choice": self.turn_choice,
            "target_x": None,
            "target_y": None,
            "error": 0.0,
            "error_px": 0,
            "linear_x": 0.0,
            "angular_z": 0.0,
            "base_center": int(base_center),
            "mode": "search",
            "turn_state": self.turn_state,
            "action_label": "STOP",
            "confidence": float(confidence),
        }

        mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        mask_small = cv2.resize(mask_bgr, (260, 150))
        annotated[10:160, w - 270:w - 10] = mask_small
        cv2.rectangle(annotated, (w - 270, 10), (w - 10, 160), (255, 255, 255), 1)
        cv2.putText(annotated, "MASK", (w - 250, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

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
            control = self.compute_control(roi.shape[1], smooth_target_x, self.turn_state)

            result = {
                "found": True,
                "junction": effective_special,
                "cross": cross_detected,
                "approach": approach_detected or (self.approach_hold_frames > 0),
                "waiting_at_junction": effective_special,
                "turn_choice": self.turn_choice,
                "target_x": int(smooth_target_x),
                "target_y": int(smooth_target_y + roi_start),
                "error": control["error"],
                "error_px": control["error_px"],
                "linear_x": control["linear_x"],
                "angular_z": control["angular_z"],
                "base_center": int(base_center),
                "mode": "recover" if recovered else control["mode"],
                "turn_state": self.turn_state,
                "action_label": "RECOVER" if recovered else control["action_label"],
                "confidence": float(confidence if not recovered else max(0.25, confidence * 0.6)),
            }

            if raw_target_x is not None and raw_target_y is not None:
                cv2.circle(roi, (raw_target_x, raw_target_y), 5, (0, 0, 255), -1)

            color_ring = (0, 255, 255) if recovered else (255, 255, 255)
            color_core = (0, 165, 255) if recovered else (0, 255, 0)

            cv2.circle(roi, (smooth_target_x, smooth_target_y), 10, color_ring, 2)
            cv2.circle(roi, (smooth_target_x, smooth_target_y), 3, color_core, -1)

            cv2.putText(
                annotated,
                f"FOUND | err={control['error']:.3f} err_px={control['error_px']} lin={control['linear_x']:.3f} ang={control['angular_z']:.3f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.60,
                (0, 255, 0),
                2,
            )
            cv2.putText(
                annotated,
                f"target=({smooth_target_x},{smooth_target_y}) action={result['action_label']} state={self.turn_state} conf={result['confidence']:.2f}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.60,
                (0, 255, 255),
                2,
            )

        elif self.commit_turn_frames > 0 and self.turn_choice in ("left", "right"):
            self.prev_error = 0.0
            self.prev_smooth_error = 0.0
            self.turn_state = "commit_turn"

            forced_angular = -0.42 if self.turn_choice == "right" else 0.42
            forced_linear = LINEAR_SPEED * TURN_SPEED_SCALE * COMMIT_LINEAR_SCALE

            result = {
                "found": True,
                "junction": True,
                "cross": cross_detected,
                "approach": True,
                "waiting_at_junction": True,
                "turn_choice": self.turn_choice,
                "target_x": None,
                "target_y": None,
                "error": 0.0,
                "error_px": 0,
                "linear_x": float(forced_linear),
                "angular_z": float(forced_angular),
                "base_center": int(base_center),
                "mode": "commit_turn",
                "turn_state": self.turn_state,
                "action_label": "COMMIT_RIGHT" if self.turn_choice == "right" else "COMMIT_LEFT",
                "confidence": 0.60,
            }

            cv2.putText(
                annotated,
                "TEMP LOST | COMMIT TURN",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 165, 255),
                2,
            )

        else:
            self.prev_error = 0.0
            self.prev_smooth_error = 0.0
            self.prev_angular_z = 0.0
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

        cv2.putText(
            annotated,
            f"LOST={self.line_lost_frames} | NORMAL_W={0 if self.normal_line_width is None else int(self.normal_line_width)}",
            (10, 118),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.60,
            (220, 220, 220),
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