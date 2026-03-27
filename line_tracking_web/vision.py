import cv2
import numpy as np


class LineTracker:
    def __init__(self):
        self.prev_e = 0.0
        self.prev_line_x = None

        self.kp = 0.015
        self.kd = 0.010
        self.deadband = 8

        self.base_speed = 14
        self.min_speed = 6
        self.max_speed = 18
        self.max_turn = 60

        # ===== tham số nhận diện line =====
        self.roi_top_ratio = 0.48      # thấp hơn bản cũ để bỏ bớt vùng xa
        self.binary_thresh = 85        # line đen trên nền sáng
        self.min_contour_area = 1200
        self.min_segment_pixels = 8
        self.max_center_jump = 140     # chống nhảy sang vật đen khác
        self.prefer_center_weight = 0.8
        self.prefer_prev_weight = 1.2

    def _find_segments_on_row(self, binary_img, y):
        row = binary_img[y, :]
        xs = np.where(row > 0)[0]

        if len(xs) == 0:
            return []

        segments = []
        start = xs[0]
        prev = xs[0]

        for x in xs[1:]:
            if x == prev + 1:
                prev = x
            else:
                segments.append((start, prev))
                start = x
                prev = x

        segments.append((start, prev))
        return segments

    def _pick_best_segment(self, binary_img, y, image_center_x):
        segments = self._find_segments_on_row(binary_img, y)
        if not segments:
            return None

        best = None
        best_score = -1e9

        for x1, x2 in segments:
            width = x2 - x1 + 1
            if width < self.min_segment_pixels:
                continue

            cx = (x1 + x2) // 2

            score = 0.0
            score += width * 0.6

            # ưu tiên gần tâm ảnh
            score -= abs(cx - image_center_x) * self.prefer_center_weight

            # ưu tiên gần line frame trước
            if self.prev_line_x is not None:
                score -= abs(cx - self.prev_line_x) * self.prefer_prev_weight

            if score > best_score:
                best_score = score
                best = cx

        return best

    def _score_contour(self, contour, mask_shape, image_center_x):
        h, w = mask_shape[:2]
        x, y, cw, ch = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)

        if area < self.min_contour_area:
            return -1e9

        # contour line nên kéo dài theo chiều dọc
        aspect = ch / max(cw, 1)

        # ưu tiên contour chạm gần đáy ROI
        bottom_dist = abs((y + ch) - h)

        # tâm contour
        M = cv2.moments(contour)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
        else:
            cx = x + cw // 2

        score = 0.0
        score += area * 0.02
        score += aspect * 40.0
        score -= bottom_dist * 2.5
        score -= abs(cx - image_center_x) * 0.8

        if self.prev_line_x is not None:
            jump = abs(cx - self.prev_line_x)
            if jump > self.max_center_jump:
                score -= 300
            score -= jump * 1.0

        return score

    def _select_main_line_mask(self, binary_img):
        contours, _ = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = binary_img.shape[:2]
        center_x = w // 2

        if not contours:
            return np.zeros_like(binary_img), None

        best_contour = None
        best_score = -1e9

        for cnt in contours:
            score = self._score_contour(cnt, binary_img.shape, center_x)
            if score > best_score:
                best_score = score
                best_contour = cnt

        if best_contour is None or best_score < -1e8:
            return np.zeros_like(binary_img), None

        selected = np.zeros_like(binary_img)
        cv2.drawContours(selected, [best_contour], -1, 255, thickness=cv2.FILLED)

        return selected, best_contour

    def process(self, frame):
        h, w = frame.shape[:2]

        # ROI thấp hơn để bỏ bớt nhiễu vùng xa
        roi_top = int(h * self.roi_top_ratio)
        roi = frame[roi_top:h, 0:w]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # tách line đen
        _, binary = cv2.threshold(blur, self.binary_thresh, 255, cv2.THRESH_BINARY_INV)

        kernel_open = np.ones((3, 3), np.uint8)
        kernel_close = np.ones((7, 7), np.uint8)

        morph = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)
        morph = cv2.morphologyEx(morph, cv2.MORPH_CLOSE, kernel_close)

        # chỉ giữ contour line chính
        selected_mask, selected_contour = self._select_main_line_mask(morph)

        rh, rw = selected_mask.shape[:2]
        center_x = rw // 2

        y_bottom = int(rh * 0.88)
        y_mid = int(rh * 0.60)
        y_top = int(rh * 0.30)

        x_bottom = self._pick_best_segment(selected_mask, y_bottom, center_x)
        x_mid = self._pick_best_segment(selected_mask, y_mid, center_x)
        x_top = self._pick_best_segment(selected_mask, y_top, center_x)

        # fallback nếu 1 số hàng không thấy
        if x_bottom is None and x_mid is not None:
            x_bottom = x_mid
        if x_mid is None and x_bottom is not None and x_top is not None:
            x_mid = (x_bottom + x_top) // 2
        if x_top is None and x_mid is not None:
            x_top = x_mid

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

            turn = int(max(-self.max_turn, min(self.max_turn, raw_turn * 25)))

            heading_mag = abs(e_heading) if e_heading is not None else 0
            speed = self.base_speed - int(0.03 * abs(e_used) + 0.02 * heading_mag)
            speed = max(self.min_speed, min(self.max_speed, speed))

            if status == "WEAK_TRACKING":
                speed = min(speed, 8)

            forward = speed

        # cập nhật line trước đó để frame sau bám ổn định hơn
        if x_bottom is not None:
            self.prev_line_x = x_bottom
        elif x_mid is not None:
            self.prev_line_x = x_mid
        elif x_top is not None:
            self.prev_line_x = x_top

        # dùng selected_mask làm morph hiển thị luôn
        debug = {
            "roi_top": int(roi_top),
            "x_bottom": None if x_bottom is None else int(x_bottom),
            "x_mid": None if x_mid is None else int(x_mid),
            "x_top": None if x_top is None else int(x_top),
            "e_lat": None if e_lat is None else int(e_lat),
            "e_heading": None if e_heading is None else int(e_heading),
            "e_mix": None if e_mix is None else float(e_mix),
            "forward": int(forward),
            "turn": int(turn),
            "status": status,
            "roi": roi,
            "gray": gray,
            "binary": binary,
            "morph": selected_mask,
        }

        return debug