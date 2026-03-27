import cv2
import numpy as np


def process_line_frame(frame):
    h, w = frame.shape[:2]

    roi_top = int(h * 0.35)
    roi = frame[roi_top:h, 0:w]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    _, binary = cv2.threshold(blur, 100, 255, cv2.THRESH_BINARY_INV)

    kernel = np.ones((5, 5), np.uint8)
    morph = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    morph = cv2.morphologyEx(morph, cv2.MORPH_CLOSE, kernel)

    return {
        "roi_top": roi_top,
        "roi": roi,
        "gray": gray,
        "binary": binary,
        "morph": morph,
    }