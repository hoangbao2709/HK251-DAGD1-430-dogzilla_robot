import cv2
import numpy as np


class LineTracker:
    def __init__(self):
        self.prev_e = 0.0

        self.kp = 0.015
        self.kd = 0.010
        self.deadband = 8

        self.base_speed = 14
        self.min_speed = 6
        self.max_speed = 18
        self.max_turn = 60

    def find_line_center_on_row(self, binary_img, y, min_pixels=5):
        row = binary_img[y, :]
        xs = np.where(row > 0)[0]
        if len(xs) < min_pixels:
            return None
        return int(np.mean(xs))

    def process(self, frame):
        h, w = frame.shape[:2]
        roi_top = int(h * 0.35)
        roi = frame[roi_top:h, 0:w]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, binary = cv2.threshold(blur, 100, 255, cv2.THRESH_BINARY_INV)

        kernel = np.ones((5, 5), np.uint8)
        morph = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        morph = cv2.morphologyEx(morph, cv2.MORPH_CLOSE, kernel)

        rh, rw = morph.shape[:2]
        center_x = rw // 2

        y_bottom = int(rh * 0.85)
        y_mid = int(rh * 0.55)
        y_top = int(rh * 0.25)

        x_bottom = self.find_line_center_on_row(morph, y_bottom)
        x_mid = self.find_line_center_on_row(morph, y_mid)
        x_top = self.find_line_center_on_row(morph, y_top)

        if x_bottom is not None:
            e_lat = x_bottom - center_x
        elif x_mid is not None:
            e_lat = x_mid - center_x
        elif x_top is not None:
            e_lat = x_top - center_x
        else:
            e_lat = None

        if x_bottom is not None and x_top is not None:
            e_heading = x_top - x_bottom
        elif x_bottom is not None and x_mid is not None:
            e_heading = x_mid - x_bottom
        elif x_mid is not None and x_top is not None:
            e_heading = x_top - x_mid
        else:
            e_heading = None

        valid_count = sum(v is not None for v in [x_bottom, x_mid, x_top])

        if valid_count == 0:
            status = "NO_LINE"
        elif valid_count == 1:
            status = "WEAK_TRACKING"
        elif valid_count == 2:
            status = "PARTIAL_TRACKING"
        else:
            status = "TRACKING"

        e_mix = None
        if e_lat is not None and e_heading is not None:
            e_mix = 0.7 * e_lat + 0.3 * e_heading
        elif e_lat is not None:
            e_mix = e_lat

        forward = 0
        turn = 0

        if e_mix is not None:
            e_used = 0 if abs(e_mix) < self.deadband else e_mix
            de = e_used - self.prev_e
            raw_turn = self.kp * e_used + self.kd * de
            self.prev_e = e_used

            # turn API:
            # dương = quay phải
            # âm    = quay trái
            turn = int(max(-self.max_turn, min(self.max_turn, raw_turn * 25)))

            heading_mag = abs(e_heading) if e_heading is not None else 0
            speed = self.base_speed - int(0.03 * abs(e_used) + 0.02 * heading_mag)
            speed = max(self.min_speed, min(self.max_speed, speed))

            if status == "WEAK_TRACKING":
                speed = min(speed, 8)

            forward = speed

        debug = {
            "roi_top": roi_top,
            "x_bottom": x_bottom,
            "x_mid": x_mid,
            "x_top": x_top,
            "e_lat": e_lat,
            "e_heading": e_heading,
            "e_mix": e_mix,
            "forward": forward,
            "turn": turn,
            "status": status,
            "roi": roi,
            "gray": gray,
            "binary": binary,
            "morph": morph,
        }
        return debug