import math
import time
from typing import Any

from ..models import QRLocalizationMetric, Robot
from .qr_detect import detect_qr_state_once
from .ros import ROSClient


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _angle_error_deg(est: float | None, gt: float | None) -> float | None:
    if est is None or gt is None:
        return None
    diff = math.radians(est - gt)
    return abs(math.degrees(math.atan2(math.sin(diff), math.cos(diff))))


def _distance_error(est: float | None, gt: float | None) -> float | None:
    if est is None or gt is None:
        return None
    return abs(est - gt)


def _point_error(
    est_x: float | None,
    est_y: float | None,
    gt_x: float | None,
    gt_y: float | None,
) -> float | None:
    if est_x is None or est_y is None or gt_x is None or gt_y is None:
        return None
    return math.hypot(est_x - gt_x, est_y - gt_y)


def _world_from_relative(
    pose: dict[str, Any] | None,
    forward_m: float | None,
    lateral_m: float | None,
) -> tuple[float | None, float | None]:
    if not pose or not pose.get("ok") or forward_m is None or lateral_m is None:
        return None, None

    x = _finite_float(pose.get("x"))
    y = _finite_float(pose.get("y"))
    theta = _finite_float(pose.get("theta")) or 0.0
    if x is None or y is None:
        return None, None

    world_x = x + math.cos(theta) * forward_m + math.sin(theta) * lateral_m
    world_y = y + math.sin(theta) * forward_m - math.cos(theta) * lateral_m
    return world_x, world_y


def _extract_ground_truth(body: dict[str, Any]) -> dict[str, float | None]:
    gt = body.get("ground_truth") or body.get("gt") or {}
    return {
        "distance_m": _finite_float(gt.get("distance_m")),
        "angle_deg": _finite_float(gt.get("angle_deg")),
        "x": _finite_float(gt.get("x")),
        "y": _finite_float(gt.get("y")),
    }


def _extract_nav(body: dict[str, Any]) -> dict[str, float | None]:
    nav = body.get("nav") or {}
    return {
        "goal_x": _finite_float(nav.get("goal_x")),
        "goal_y": _finite_float(nav.get("goal_y")),
        "stop_x": _finite_float(nav.get("stop_x")),
        "stop_y": _finite_float(nav.get("stop_y")),
    }


def _extract_manual_estimate(body: dict[str, Any]) -> dict[str, Any] | None:
    est = body.get("estimate")
    if not isinstance(est, dict):
        return None
    lidar_distance = _finite_float(est.get("lidar_distance_m"))
    distance_m = lidar_distance
    distance_source = "lidar" if lidar_distance is not None else str(est.get("distance_source") or "")
    if distance_m is None and distance_source == "lidar":
        distance_m = _finite_float(est.get("distance_m"))
    return {
        "detected": bool(est.get("detected", True)),
        "qr_text": str(est.get("qr_text") or est.get("text") or ""),
        "distance_m": distance_m,
        "distance_source": distance_source,
        "camera_distance_m": None,
        "lidar_distance_m": lidar_distance if lidar_distance is not None else distance_m,
        "angle_deg": _finite_float(est.get("angle_deg")),
        "lateral_x_m": _finite_float(est.get("lateral_x_m")),
        "forward_z_m": _finite_float(est.get("forward_z_m")),
        "world_x": _finite_float(est.get("x")),
        "world_y": _finite_float(est.get("y")),
    }


def _auto_capture_estimate(robot_id: str) -> tuple[dict[str, Any], dict[str, Any], float, float]:
    detect_started = time.perf_counter()
    qr_data = detect_qr_state_once(robot_id)
    detect_time_ms = (time.perf_counter() - detect_started) * 1000.0

    slam_started = time.perf_counter()
    slam_state = ROSClient(robot_id).get_slam_state_for_ui(include_scan_points=False)
    slam_time_ms = (time.perf_counter() - slam_started) * 1000.0

    position = qr_data.get("position_json") or {}
    qr = position.get("qr") or {}
    pos = position.get("position") or {}
    pose = slam_state.get("pose") or {}

    lateral = _finite_float(pos.get("lateral_x_m"))
    forward = _finite_float(pos.get("forward_z_m"))
    world_x, world_y = _world_from_relative(pose, forward, lateral)

    return (
        {
            "detected": bool(position.get("detected")),
            "qr_text": str(qr.get("text") or qr_data.get("text") or ""),
            "distance_m": _finite_float(pos.get("distance_m")),
            "distance_source": str(pos.get("distance_source") or ""),
            "camera_distance_m": _finite_float(
                ((position.get("camera_position") or {}) if isinstance(position, dict) else {}).get("distance_m")
            ),
            "lidar_distance_m": _finite_float(
                ((position.get("lidar") or {}) if isinstance(position, dict) else {}).get("distance_m")
            ),
            "angle_deg": _finite_float(pos.get("angle_deg")),
            "lateral_x_m": lateral,
            "forward_z_m": forward,
            "world_x": world_x,
            "world_y": world_y,
        },
        slam_state,
        detect_time_ms,
        slam_time_ms,
    )


def _save_point_to_docker_if_requested(
    robot_id: str,
    body: dict[str, Any],
    slam_state: dict[str, Any],
    estimate: dict[str, Any],
) -> dict[str, Any]:
    save_cfg = body.get("save_point") or body.get("docker_save") or {}
    if not isinstance(save_cfg, dict) or not bool(save_cfg.get("enabled", False)):
        return {
            "requested": False,
            "time_ms": _finite_float(body.get("docker_save_time_ms")),
            "success": body.get("docker_save_success")
            if isinstance(body.get("docker_save_success"), bool)
            else None,
            "error": str(body.get("docker_save_error") or ""),
            "result": None,
        }

    name = str(save_cfg.get("name") or body.get("label") or estimate.get("qr_text") or "").strip()
    if not name:
        return {
            "requested": True,
            "time_ms": 0.0,
            "success": False,
            "error": "save_point.name is required",
            "result": None,
        }

    x = _finite_float(save_cfg.get("x"))
    y = _finite_float(save_cfg.get("y"))
    yaw = _finite_float(save_cfg.get("yaw"))

    if x is None or y is None:
        obstacle = slam_state.get("nearest_obstacle_ahead") or {}
        x = _finite_float(obstacle.get("x"))
        y = _finite_float(obstacle.get("y"))

    if x is None or y is None:
        x = estimate.get("world_x")
        y = estimate.get("world_y")

    if x is None or y is None:
        return {
            "requested": True,
            "time_ms": 0.0,
            "success": False,
            "error": "Cannot resolve point coordinate for docker save",
            "result": None,
        }

    pose = slam_state.get("pose") or {}
    if yaw is None and pose.get("ok"):
        robot_x = _finite_float(pose.get("x"))
        robot_y = _finite_float(pose.get("y"))
        if robot_x is not None and robot_y is not None:
            yaw = math.atan2(y - robot_y, x - robot_x)
    if yaw is None:
        yaw = 0.0

    client = ROSClient(robot_id)
    started = time.perf_counter()
    try:
        result = client.create_point(name=name, x=x, y=y, yaw=yaw)
        save_time_ms = (time.perf_counter() - started) * 1000.0
        return {
            "requested": True,
            "time_ms": save_time_ms,
            "success": True,
            "error": "",
            "result": result,
            "point": {"name": name, "x": x, "y": y, "yaw": yaw},
        }
    except Exception as exc:
        save_time_ms = (time.perf_counter() - started) * 1000.0
        return {
            "requested": True,
            "time_ms": save_time_ms,
            "success": False,
            "error": str(exc),
            "result": None,
            "point": {"name": name, "x": x, "y": y, "yaw": yaw},
        }


def create_qr_localization_metric(robot_id: str, body: dict[str, Any]) -> QRLocalizationMetric:
    total_started = time.perf_counter()
    robot, _ = Robot.objects.get_or_create(pk=robot_id)
    gt = _extract_ground_truth(body)
    nav = _extract_nav(body)
    manual_est = _extract_manual_estimate(body)

    capture_payload: dict[str, Any] = {}
    slam_state: dict[str, Any] = {}
    elapsed_ms = _finite_float(body.get("processing_time_ms"))
    detect_time_ms = _finite_float(body.get("qr_detect_time_ms"))

    if manual_est is None:
        estimate, slam_state, auto_detect_ms, slam_time_ms = _auto_capture_estimate(robot_id)
        if detect_time_ms is None:
            detect_time_ms = auto_detect_ms
        capture_payload["auto_capture"] = True
        capture_payload["slam_fetch_time_ms"] = slam_time_ms
    else:
        estimate = manual_est
        capture_payload["auto_capture"] = False

    save_result = _save_point_to_docker_if_requested(robot_id, body, slam_state, estimate)
    if elapsed_ms is None:
        elapsed_ms = (time.perf_counter() - total_started) * 1000.0

    pose = slam_state.get("pose") or {}
    distance_est = estimate.get("distance_m")
    distance_source = str(estimate.get("distance_source") or "")
    camera_distance_est = estimate.get("camera_distance_m")
    lidar_distance_est = estimate.get("lidar_distance_m")
    if not distance_source:
        if lidar_distance_est is not None and distance_est == lidar_distance_est:
            distance_source = "lidar"
    distance_gt = gt["distance_m"]
    angle_est = estimate.get("angle_deg")
    angle_gt = gt["angle_deg"]
    world_est_x = estimate.get("world_x")
    world_est_y = estimate.get("world_y")

    row = QRLocalizationMetric.objects.create(
        robot=robot,
        label=str(body.get("label") or ""),
        trial_name=str(body.get("trial_name") or body.get("trial") or ""),
        source=str(body.get("source") or "manual"),
        detected=bool(estimate.get("detected")),
        qr_text=str(estimate.get("qr_text") or ""),
        distance_gt_m=distance_gt,
        distance_est_m=distance_est,
        distance_error_m=_distance_error(distance_est, distance_gt),
        distance_source=distance_source,
        camera_distance_est_m=camera_distance_est,
        lidar_distance_est_m=lidar_distance_est,
        angle_gt_deg=angle_gt,
        angle_est_deg=angle_est,
        angle_error_deg=_angle_error_deg(angle_est, angle_gt),
        qr_world_gt_x=gt["x"],
        qr_world_gt_y=gt["y"],
        qr_world_est_x=world_est_x,
        qr_world_est_y=world_est_y,
        qr_world_error_m=_point_error(world_est_x, world_est_y, gt["x"], gt["y"]),
        nav_goal_x=nav["goal_x"],
        nav_goal_y=nav["goal_y"],
        nav_stop_x=nav["stop_x"],
        nav_stop_y=nav["stop_y"],
        nav_error_m=_point_error(nav["stop_x"], nav["stop_y"], nav["goal_x"], nav["goal_y"]),
        robot_pose_x=_finite_float(pose.get("x")),
        robot_pose_y=_finite_float(pose.get("y")),
        robot_pose_theta=_finite_float(pose.get("theta")),
        qr_lateral_x_m=estimate.get("lateral_x_m"),
        qr_forward_z_m=estimate.get("forward_z_m"),
        processing_time_ms=elapsed_ms,
        qr_detect_time_ms=detect_time_ms,
        docker_save_time_ms=save_result.get("time_ms"),
        docker_save_success=save_result.get("success"),
        docker_save_error=str(save_result.get("error") or ""),
        payload={
            **capture_payload,
            "request": body,
            "estimate": estimate,
            "slam_pose": pose,
            "docker_save": save_result,
        },
    )
    return row


def metric_to_dict(metric: QRLocalizationMetric) -> dict[str, Any]:
    return {
        "id": metric.id,
        "robot_id": metric.robot_id,
        "created_at": metric.created_at.isoformat() if metric.created_at else None,
        "label": metric.label,
        "trial_name": metric.trial_name,
        "source": metric.source,
        "detected": metric.detected,
        "qr_text": metric.qr_text,
        "distance": {
            "gt_m": metric.distance_gt_m,
            "est_m": metric.distance_est_m,
            "error_m": metric.distance_error_m,
            "source": metric.distance_source,
            "camera_est_m": metric.camera_distance_est_m,
            "lidar_est_m": metric.lidar_distance_est_m,
        },
        "angle": {
            "gt_deg": metric.angle_gt_deg,
            "est_deg": metric.angle_est_deg,
            "error_deg": metric.angle_error_deg,
        },
        "qr_world": {
            "gt_x": metric.qr_world_gt_x,
            "gt_y": metric.qr_world_gt_y,
            "est_x": metric.qr_world_est_x,
            "est_y": metric.qr_world_est_y,
            "error_m": metric.qr_world_error_m,
        },
        "navigation": {
            "goal_x": metric.nav_goal_x,
            "goal_y": metric.nav_goal_y,
            "stop_x": metric.nav_stop_x,
            "stop_y": metric.nav_stop_y,
            "error_m": metric.nav_error_m,
        },
        "robot_pose": {
            "x": metric.robot_pose_x,
            "y": metric.robot_pose_y,
            "theta": metric.robot_pose_theta,
        },
        "qr_relative": {
            "lateral_x_m": metric.qr_lateral_x_m,
            "forward_z_m": metric.qr_forward_z_m,
        },
        "processing_time_ms": metric.processing_time_ms,
        "timing": {
            "processing_time_ms": metric.processing_time_ms,
            "qr_detect_time_ms": metric.qr_detect_time_ms,
            "docker_save_time_ms": metric.docker_save_time_ms,
        },
        "docker_save": {
            "success": metric.docker_save_success,
            "error": metric.docker_save_error,
        },
    }


def summarize_qr_localization_metrics(queryset) -> dict[str, Any]:
    rows = list(queryset)
    total = len(rows)
    detected = sum(1 for row in rows if row.detected)

    def avg(field: str) -> float | None:
        values = [getattr(row, field) for row in rows if getattr(row, field) is not None]
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    return {
        "total": total,
        "detected": detected,
        "success_rate_pct": round((detected / total) * 100.0, 2) if total else 0.0,
        "avg_distance_error_m": avg("distance_error_m"),
        "avg_angle_error_deg": avg("angle_error_deg"),
        "avg_qr_world_error_m": avg("qr_world_error_m"),
        "avg_nav_error_m": avg("nav_error_m"),
        "avg_processing_time_ms": avg("processing_time_ms"),
        "avg_qr_detect_time_ms": avg("qr_detect_time_ms"),
        "avg_docker_save_time_ms": avg("docker_save_time_ms"),
    }
