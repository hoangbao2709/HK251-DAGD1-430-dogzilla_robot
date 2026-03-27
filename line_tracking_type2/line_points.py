import cv2
import numpy as np


def find_line_center_on_row(binary_img, y, min_pixels=5):
    row = binary_img[y, :]
    xs = np.where(row > 0)[0]

    if len(xs) < min_pixels:
        return None

    return int(np.mean(xs))


def extract_line_points(morph):
    rh, rw = morph.shape[:2]

    y_bottom = int(rh * 0.85)
    y_mid = int(rh * 0.55)
    y_top = int(rh * 0.25)

    x_bottom = find_line_center_on_row(morph, y_bottom)
    x_mid = find_line_center_on_row(morph, y_mid)
    x_top = find_line_center_on_row(morph, y_top)

    return {
        "x_bottom": x_bottom,
        "x_mid": x_mid,
        "x_top": x_top,
        "y_bottom": y_bottom,
        "y_mid": y_mid,
        "y_top": y_top,
        "image_center_x": rw // 2,
        "width": rw,
        "height": rh,
    }


def draw_line_points(morph, points, errors):
    view = cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR)

    rw = points["width"]
    rh = points["height"]

    x_bottom = points["x_bottom"]
    x_mid = points["x_mid"]
    x_top = points["x_top"]

    y_bottom = points["y_bottom"]
    y_mid = points["y_mid"]
    y_top = points["y_top"]

    center_x = points["image_center_x"]

    cv2.line(view, (center_x, 0), (center_x, rh), (255, 0, 0), 2)

    cv2.line(view, (0, y_bottom), (rw, y_bottom), (0, 255, 255), 1)
    cv2.line(view, (0, y_mid), (rw, y_mid), (0, 255, 255), 1)
    cv2.line(view, (0, y_top), (rw, y_top), (0, 255, 255), 1)

    pts = []

    if x_bottom is not None:
        cv2.circle(view, (x_bottom, y_bottom), 6, (0, 0, 255), -1)
        pts.append((x_bottom, y_bottom))

    if x_mid is not None:
        cv2.circle(view, (x_mid, y_mid), 6, (0, 255, 0), -1)
        pts.append((x_mid, y_mid))

    if x_top is not None:
        cv2.circle(view, (x_top, y_top), 6, (255, 0, 255), -1)
        pts.append((x_top, y_top))

    for i in range(len(pts) - 1):
        cv2.line(view, pts[i], pts[i + 1], (255, 255, 0), 2)

    cv2.putText(view, f"x_bottom={x_bottom}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(view, f"x_mid={x_mid}", (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(view, f"x_top={x_top}", (10, 75),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.putText(view, f"status={errors['status']}", (10, 105),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(view, f"e_lat={errors['e_lat']}", (10, 130),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(view, f"e_heading={errors['e_heading']}", (10, 155),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(view, f"e_mix={errors['e_mix']}", (10, 180),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    return view