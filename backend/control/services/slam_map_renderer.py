from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Mapping

import cv2
import numpy as np

_CACHE_LOCK = threading.Lock()
_PNG_CACHE: "OrderedDict[tuple, bytes]" = OrderedDict()
_MAX_CACHE_ITEMS = 8


def _header(headers: Mapping[str, str], name: str, default: str = "") -> str:
    value = headers.get(name)
    if value is not None:
        return value
    return headers.get(name.lower(), default)


def _map_cache_key(
    robot_id: str,
    headers: Mapping[str, str],
    raw_data: bytes,
) -> tuple:
    return (
        robot_id,
        _header(headers, "X-Map-Version", "0"),
        _header(headers, "X-Map-Width", "0"),
        _header(headers, "X-Map-Height", "0"),
        _header(headers, "X-Map-Resolution", "0"),
        _header(headers, "X-Map-Origin-X", "0"),
        _header(headers, "X-Map-Origin-Y", "0"),
        len(raw_data),
    )


def render_raw_occupancy_grid_png(
    raw_data: bytes,
    headers: Mapping[str, str],
    *,
    robot_id: str = "",
) -> bytes:
    """
    Render robot OccupancyGrid bytes on the backend.

    The robot sends int8 row-major OccupancyGrid data only. This function does
    the image padding/color conversion that used to happen on docker-robot.
    """
    cache_key = _map_cache_key(robot_id, headers, raw_data)
    with _CACHE_LOCK:
        cached = _PNG_CACHE.get(cache_key)
        if cached is not None:
            _PNG_CACHE.move_to_end(cache_key)
            return cached

    width = int(_header(headers, "X-Map-Width"))
    height = int(_header(headers, "X-Map-Height"))
    resolution = float(_header(headers, "X-Map-Resolution", "0.0"))

    if width <= 0 or height <= 0 or resolution <= 0:
        raise ValueError("invalid raw map headers")

    data = np.frombuffer(raw_data, dtype=np.int8)
    expected = width * height
    if data.size != expected:
        raise ValueError(f"raw map size mismatch: got {data.size}, expected {expected}")

    grid = data.reshape(height, width)

    side = max(width, height)
    extra = max(4, int(0.03 * side))
    side2 = side + 2 * extra
    pad_left = (side2 - width) // 2
    pad_bottom = (side2 - height) // 2

    image = np.full((side2, side2), 82, dtype=np.uint8)
    map_image = np.full((height, width), 153, dtype=np.uint8)
    map_image[grid == 0] = 242
    map_image[grid > 50] = 5

    image[pad_bottom:pad_bottom + height, pad_left:pad_left + width] = map_image
    image = np.flipud(image)

    ok, encoded = cv2.imencode(
        ".png",
        image,
        [int(cv2.IMWRITE_PNG_COMPRESSION), 3],
    )
    if not ok:
        raise RuntimeError("failed to encode rendered map png")

    png = encoded.tobytes()
    with _CACHE_LOCK:
        _PNG_CACHE[cache_key] = png
        _PNG_CACHE.move_to_end(cache_key)
        while len(_PNG_CACHE) > _MAX_CACHE_ITEMS:
            _PNG_CACHE.popitem(last=False)

    return png
