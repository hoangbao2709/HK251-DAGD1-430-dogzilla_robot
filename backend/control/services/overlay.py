from pathlib import Path
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/arialuni.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf"),
]


def _load_unicode_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_unicode_text(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    *,
    font_size: int = 20,
    fill: tuple[int, int, int] = (255, 255, 255),
    stroke_fill: tuple[int, int, int] = (0, 0, 0),
    stroke_width: int = 2,
) -> np.ndarray:
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)
    font = _load_unicode_font(font_size)
    draw.text(
        origin,
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


def draw_overlay(frame, detection_result):
    out = frame.copy()

    if not detection_result.ok:
        return out

    for item in detection_result.items:
        corners = item.corners

        for i in range(4):
            p1 = tuple(corners[i])
            p2 = tuple(corners[(i + 1) % 4])
            cv2.line(out, p1, p2, (0, 255, 0), 2)

        cv2.circle(out, item.center_px, 6, (255, 0, 0), -1)

        x, y = item.center_px
        display_distance_m = item.lidar_distance_m
        distance_source = "LiDAR"
        try:
            display_distance_m = float(display_distance_m)
        except (TypeError, ValueError):
            display_distance_m = item.distance_m
            distance_source = "camera"
        else:
            if not math.isfinite(display_distance_m):
                display_distance_m = item.distance_m
                distance_source = "camera"

        angle_rad = float(item.angle_rad)
        lateral_x_m = display_distance_m * math.sin(angle_rad)
        forward_z_m = display_distance_m * math.cos(angle_rad)
        target_distance_m = max(display_distance_m + 0.35, 0.65)
        target_x_m = target_distance_m * math.sin(angle_rad)
        target_z_m = target_distance_m * math.cos(angle_rad)
        lines = [
            f"QR: {item.text}",
            f"angle: {item.angle_deg:.1f} deg",
            f"dist : {display_distance_m:.2f} m",
            f"tx/tz: ({lateral_x_m:.2f}, {forward_z_m:.2f})",
            f"target: ({target_x_m:.2f}, {target_z_m:.2f})",
        ]

        yy = y - 55
        for line in lines:
            out = _draw_unicode_text(out, line, (x + 10, yy), font_size=22)
            yy += 26

    return out
