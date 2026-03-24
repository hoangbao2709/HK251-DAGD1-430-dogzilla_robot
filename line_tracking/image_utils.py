import cv2
import numpy as np
from config import THRESHOLD_BINARY, MIN_SEGMENT_WIDTH


def build_mask(roi):
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    _, mask = cv2.threshold(gray, THRESHOLD_BINARY, 255, cv2.THRESH_BINARY_INV)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def get_segments_on_row(mask, y, min_width=MIN_SEGMENT_WIDTH):
    h, _ = mask.shape[:2]
    y = max(0, min(h - 1, y))

    row = mask[y, :]
    xs = np.where(row > 0)[0]

    if len(xs) == 0:
        return []

    segments = []
    start = xs[0]
    prev = xs[0]

    for x in xs[1:]:
        if x - prev > 1:
            if prev - start + 1 >= min_width:
                cx = (start + prev) // 2
                segments.append((int(start), int(prev), int(cx)))
            start = x
        prev = x

    if prev - start + 1 >= min_width:
        cx = (start + prev) // 2
        segments.append((int(start), int(prev), int(cx)))

    return segments


def filter_segments_in_window(segments, x_center, half_width):
    x_min = int(x_center - half_width)
    x_max = int(x_center + half_width)

    filtered = []
    for x1, x2, cx in segments:
        if x_min <= cx <= x_max:
            filtered.append((x1, x2, cx))
    return filtered