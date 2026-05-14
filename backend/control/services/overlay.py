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
        if display_distance_m is None or not math.isfinite(float(display_distance_m)):
            display_distance_m = None
            distance_source = "N/A"

        lateral_x_m = item.lateral_x_m
        forward_z_m = item.forward_z_m
        target_distance_m = item.target_distance_m
        target_x_m = item.target_x_m
        target_z_m = item.target_z_m
        map_x_m = item.map_x_m
        map_y_m = item.map_y_m
        ray_distance_m = item.ray_distance_m

        def fmt(value: float | None, digits: int = 2) -> str:
            if value is None:
                return "N/A"
            try:
                number = float(value)
            except (TypeError, ValueError):
                return "N/A"
            if not math.isfinite(number):
                return "N/A"
            return f"{number:.{digits}f}"

        lines = [
            f"QR: {item.text}",
            f"angle: {item.angle_deg:.1f} deg",
            f"dist : {fmt(display_distance_m)} m",
            f"tx/t: ({fmt(lateral_x_m)}, {fmt(forward_z_m)})",
            f"target: ({fmt(target_x_m)}, {fmt(target_z_m)})",
        ]
        if map_x_m is not None and map_y_m is not None:
            try:
                map_x = float(map_x_m)
                map_y = float(map_y_m)
                lines.append(f"map: ({map_x:.2f}, {map_y:.2f})")
            except (TypeError, ValueError):
                pass
        if ray_distance_m is not None:
            try:
                lines.append(f"ray: {float(ray_distance_m):.2f} m")
            except (TypeError, ValueError):
                pass
        if target_distance_m is not None:
            try:
                lines.append(f"target_dist: {float(target_distance_m):.2f} m")
            except (TypeError, ValueError):
                lines.append("target_dist: N/A")

        yy = y - 55
        for line in lines:
            out = _draw_unicode_text(out, line, (x + 10, yy), font_size=22)
            yy += 26

    return out
