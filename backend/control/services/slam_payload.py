import math
from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def downsample_points(points: list[dict[str, float]], max_points: int) -> list[dict[str, float]]:
    if max_points <= 0 or len(points) <= max_points:
        return points

    step = max(1, math.ceil(len(points) / max_points))
    sampled = points[::step]
    if points and sampled[-1] != points[-1]:
        sampled.append(points[-1])

    if len(sampled) <= max_points:
        return sampled

    return sampled[: max_points - 1] + [points[-1]]


def scan_points_from_raw_scan(scan: dict[str, Any], max_points: int = 120) -> list[dict[str, float]]:
    raw = scan.get("raw") or {}
    transform = scan.get("transform") or {}
    samples = raw.get("samples") or []

    if not isinstance(samples, list) or not samples:
        points = scan.get("points") or []
        if not isinstance(points, list):
            return []
        valid_points = [
            {"x": _as_float(point.get("x")), "y": _as_float(point.get("y"))}
            for point in points
            if isinstance(point, dict)
        ]
        return downsample_points(valid_points, max_points)

    tx = _as_float(transform.get("x"))
    ty = _as_float(transform.get("y"))
    yaw = _as_float(transform.get("yaw"))
    cy = math.cos(yaw)
    sy = math.sin(yaw)

    range_min = _as_float(raw.get("range_min"), 0.0)
    range_max = _as_float(raw.get("range_max"), float("inf"))

    points: list[dict[str, float]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue

        rng = _as_float(sample.get("range"), float("nan"))
        if not math.isfinite(rng) or rng < range_min or rng > range_max:
            continue

        angle = _as_float(sample.get("angle"))
        lx = rng * math.cos(angle)
        ly = rng * math.sin(angle)

        points.append(
            {
                "x": tx + cy * lx - sy * ly,
                "y": ty + sy * lx + cy * ly,
            }
        )

    return downsample_points(points, max_points)


def find_nearest_obstacle_ahead(
    pose: dict[str, Any] | None,
    scan_points: list[dict[str, float]],
    *,
    half_fov_rad: float = 0.35,
    min_distance_m: float = 0.05,
) -> dict[str, float] | None:
    if not pose or not pose.get("ok") or not scan_points:
        return None

    rx = _as_float(pose.get("x"))
    ry = _as_float(pose.get("y"))
    yaw = _as_float(pose.get("theta"))

    best: dict[str, float] | None = None
    best_dist = float("inf")

    for point in scan_points:
        dx = _as_float(point.get("x")) - rx
        dy = _as_float(point.get("y")) - ry
        dist = math.hypot(dx, dy)
        if not math.isfinite(dist) or dist < min_distance_m:
            continue

        diff = abs(normalize_angle(math.atan2(dy, dx) - yaw))
        if diff <= half_fov_rad and dist < best_dist:
            best_dist = dist
            best = {
                "x": _as_float(point.get("x")),
                "y": _as_float(point.get("y")),
                "dist": dist,
            }

    return best


def _first_path(paths: dict[str, Any]) -> list[dict[str, float]]:
    for key in ("a_star", "received_plan", "plan", "nav2", "local_plan"):
        value = paths.get(key)
        if isinstance(value, list) and value:
            return [
                {"x": _as_float(point.get("x")), "y": _as_float(point.get("y"))}
                for point in value
                if isinstance(point, dict)
            ]
    return []


def build_slam_ui_state(
    state: dict[str, Any],
    *,
    include_scan_points: bool = True,
    max_scan_points: int = 120,
    max_path_points: int = 240,
) -> dict[str, Any]:
    pose = state.get("pose") or {}
    scan = state.get("scan") or {}
    paths = state.get("paths") or {}

    scan_points = (
        scan_points_from_raw_scan(scan, max_points=max_scan_points)
        if include_scan_points and bool(scan.get("ok"))
        else []
    )
    path_points = downsample_points(_first_path(paths), max_path_points)
    nearest = find_nearest_obstacle_ahead(pose, scan_points)

    return {
        "map_version": state.get("map_version"),
        "render_info": state.get("render_info"),
        "pose": pose,
        "goal": state.get("goal") or {},
        "paths": {
            "a_star": path_points,
        },
        "scan": {
            "ok": bool(scan.get("ok")) and bool(scan_points),
            "points": scan_points,
            "stamp": scan.get("stamp"),
            "frame_id": scan.get("frame_id") or "",
        },
        "nearest_obstacle_ahead": nearest,
        "status": state.get("status") or {},
    }
