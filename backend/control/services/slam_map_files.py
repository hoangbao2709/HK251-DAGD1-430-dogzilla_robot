from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from django.conf import settings  # type: ignore[import-untyped]

from .slam_map_renderer import render_raw_occupancy_grid_png


def _header(headers: Mapping[str, str], name: str, default: str = "") -> str:
    value = headers.get(name)
    if value is not None:
        return value
    return headers.get(name.lower(), default)


def sanitize_map_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(name or "").strip())
    return safe.strip("_")


def sanitize_map_filename(filename: str) -> str:
    safe = str(filename or "").strip().replace("\\", "/").split("/")[-1]
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in safe)


def _safe_robot_id(robot_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(robot_id or "robot").strip()) or "robot"


def saved_slam_map_dir(robot_id: str) -> Path:
    root = Path(getattr(settings, "SLAM_MAP_SAVE_ROOT", Path(settings.BASE_DIR) / "saved_slam_maps"))
    target = root / _safe_robot_id(robot_id)
    target.mkdir(parents=True, exist_ok=True)
    return target


def find_saved_slam_map_file(robot_id: str, filename: str) -> Path | None:
    safe = sanitize_map_filename(filename)
    if not safe:
        return None

    path = saved_slam_map_dir(robot_id) / safe
    if path.is_file():
        return path
    return None


def _parse_raw_map_headers(headers: Mapping[str, str]) -> dict[str, Any]:
    width = int(_header(headers, "X-Map-Width"))
    height = int(_header(headers, "X-Map-Height"))
    resolution = float(_header(headers, "X-Map-Resolution"))
    origin_x = float(_header(headers, "X-Map-Origin-X", "0.0"))
    origin_y = float(_header(headers, "X-Map-Origin-Y", "0.0"))
    frame_id = _header(headers, "X-Map-Frame-Id", "map")

    if width <= 0 or height <= 0 or resolution <= 0:
        raise ValueError("invalid raw map headers")

    side = max(width, height)
    extra = max(4, int(0.03 * side))
    side2 = side + 2 * extra
    pad_left = (side2 - width) // 2
    pad_bottom = (side2 - height) // 2

    return {
        "width": width,
        "height": height,
        "resolution": resolution,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "frame_id": frame_id,
        "map_version": _header(headers, "X-Map-Version", "0"),
        "render_info": {
            "width_cells": side2,
            "height_cells": side2,
            "resolution": resolution,
            "origin_x": origin_x - pad_left * resolution,
            "origin_y": origin_y - pad_bottom * resolution,
            "pad_left_cells": pad_left,
            "pad_bottom_cells": pad_bottom,
        },
    }


def _raw_map_to_pgm(raw_data: bytes, width: int, height: int) -> bytes:
    data = np.frombuffer(raw_data, dtype=np.int8)
    expected = width * height
    if data.size != expected:
        raise ValueError(f"raw map size mismatch: got {data.size}, expected {expected}")

    grid = data.reshape(height, width)
    image = np.full((height, width), 205, dtype=np.uint8)
    image[grid == 0] = 254
    image[grid > 50] = 0

    header = f"P5\n{width} {height}\n255\n".encode("ascii")
    return header + np.flipud(image).tobytes()


def save_raw_slam_map_bundle(
    *,
    robot_id: str,
    name: str,
    raw_data: bytes,
    headers: Mapping[str, str],
) -> dict[str, Any]:
    safe_name = sanitize_map_name(name)
    if not safe_name:
        raise ValueError("map name is required")

    parsed = _parse_raw_map_headers(headers)
    width = int(parsed["width"])
    height = int(parsed["height"])
    resolution = float(parsed["resolution"])
    origin_x = float(parsed["origin_x"])
    origin_y = float(parsed["origin_y"])
    frame_id = str(parsed["frame_id"])

    preview_png = render_raw_occupancy_grid_png(raw_data, headers, robot_id=robot_id)
    pgm_bytes = _raw_map_to_pgm(raw_data, width, height)
    yaml_bytes = (
        f"image: {safe_name}.pgm\n"
        f"resolution: {resolution}\n"
        f"origin: [{origin_x}, {origin_y}, 0.0]\n"
        "negate: 0\n"
        "occupied_thresh: 0.65\n"
        "free_thresh: 0.196\n"
    ).encode("utf-8")

    map_info = {
        "width": width,
        "height": height,
        "resolution": resolution,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "frame_id": frame_id,
    }
    metadata = {
        "format": "slam-live-map-bundle-v1",
        "saved_by": "backend",
        "base_name": safe_name,
        "map_version": parsed["map_version"],
        "map_info": map_info,
        "render_info": parsed["render_info"],
        "files": {
            "preview": "preview.png",
            "occupancy": f"{safe_name}.pgm",
            "metadata_yaml": f"{safe_name}.yaml",
        },
    }

    bundle_name = f"{safe_name}.bundle.zip"
    bundle_path = saved_slam_map_dir(robot_id) / bundle_name
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"))
        zf.writestr("preview.png", preview_png)
        zf.writestr(f"{safe_name}.pgm", pgm_bytes)
        zf.writestr(f"{safe_name}.yaml", yaml_bytes)

    return {
        "success": True,
        "message": f"SAVED {bundle_name}",
        "name": safe_name,
        "bundle": bundle_name,
        "saved_on": "backend",
        "size_bytes": bundle_path.stat().st_size,
    }


def save_preview_slam_map_bundle(
    *,
    robot_id: str,
    name: str,
    preview_png: bytes,
    map_info: Mapping[str, Any] | None,
    render_info: Mapping[str, Any] | None,
) -> dict[str, Any]:
    safe_name = sanitize_map_name(name)
    if not safe_name:
        raise ValueError("map name is required")

    metadata = {
        "format": "slam-live-map-bundle-v1",
        "saved_by": "backend",
        "base_name": safe_name,
        "map_info": dict(map_info or {}),
        "render_info": dict(render_info or {}),
        "files": {
            "preview": "preview.png",
        },
    }

    bundle_name = f"{safe_name}.bundle.zip"
    bundle_path = saved_slam_map_dir(robot_id) / bundle_name
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"))
        zf.writestr("preview.png", preview_png)

    return {
        "success": True,
        "message": f"SAVED {bundle_name}",
        "name": safe_name,
        "bundle": bundle_name,
        "saved_on": "backend",
        "size_bytes": bundle_path.stat().st_size,
        "preview_only": True,
    }
