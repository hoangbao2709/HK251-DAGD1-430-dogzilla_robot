import math
import time
import os
import re
from dataclasses import replace
from typing import Any, Dict

import cv2
import numpy as np

from .ros import ROSClient
from .models import QRItem, DetectionResult
from .qr_detector import detect_qr_items, PYZBAR_AVAILABLE, PYZBAR_IMPORT_ERROR
from .slam_payload import find_first_obstacle_on_ray
from .overlay import draw_overlay

# Django models cho việc lưu event
from ..models import ActionEvent
import logging

logger = logging.getLogger(__name__)

QR_SIZE_M = 0.12
DEADBAND_DEG = 5.0
DETECT_WIDTH = 640
JPEG_QUALITY = 72

QR_LIDAR_HALF_FOV_DEG = float(os.environ.get("QR_LIDAR_HALF_FOV_DEG", "7.0"))
QR_LIDAR_HALF_FOV_RAD = math.radians(QR_LIDAR_HALF_FOV_DEG)
QR_LIDAR_CORRIDOR_WIDTH_M = float(os.environ.get("QR_LIDAR_CORRIDOR_WIDTH_M", "0.10"))
QR_LIDAR_MIN_DISTANCE_M = float(os.environ.get("QR_LIDAR_MIN_DISTANCE_M", "0.12"))
CAMERA_LIDAR_YAW_OFFSET_DEG = float(os.environ.get("CAMERA_LIDAR_YAW_OFFSET_DEG", "0.0"))
CAMERA_LIDAR_YAW_OFFSET_RAD = math.radians(CAMERA_LIDAR_YAW_OFFSET_DEG)

CAMERA_MATRIX = np.array([
    [920.0, 0.0, 640.0],
    [0.0, 920.0, 360.0],
    [0.0, 0.0, 1.0],
], dtype=np.float32)

DIST_COEFFS = np.array([0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)

# Trạng thái tracking QR per robot
qr_tracking_state: dict[str, dict] = {}


def _item_with_lidar_ray_hit(
    item: QRItem,
    ray_distance_m: float,
    map_x_m: float | None,
    map_y_m: float | None,
    ray_angle_rad: float,
) -> QRItem:
    """
    LiDAR supplies the first obstacle hit along the QR ray on the 2D map.
    We keep both the local robot-frame coordinates and the map hit position.
    """
    lateral_x_m = ray_distance_m * math.sin(ray_angle_rad)
    forward_z_m = ray_distance_m * math.cos(ray_angle_rad)
    target_distance_m = ray_distance_m
    target_x_m = lateral_x_m
    target_z_m = forward_z_m

    return replace(
        item,
        distance_m=ray_distance_m,
        lateral_x_m=lateral_x_m,
        forward_z_m=forward_z_m,
        target_x_m=target_x_m,
        target_z_m=target_z_m,
        target_distance_m=target_distance_m,
        camera_distance_m=item.camera_distance_m if item.camera_distance_m is not None else item.distance_m,
        lidar_distance_m=ray_distance_m,
        map_x_m=map_x_m,
        map_y_m=map_y_m,
        ray_distance_m=ray_distance_m,
        ray_angle_rad=ray_angle_rad,
    )


def _safe_qr_point_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", (text or "").strip())
    cleaned = cleaned.strip("_-")
    return f"qr__{cleaned}" if cleaned else "qr__target"


def _publish_qr_target(robot_id: str, item_dict: Dict[str, Any]) -> None:
    map_x_m = item_dict.get("map_x_m")
    map_y_m = item_dict.get("map_y_m")
    ray_angle_rad = item_dict.get("ray_angle_rad")
    if map_x_m is None or map_y_m is None:
        return

    try:
        x = float(map_x_m)
        y = float(map_y_m)
        yaw = float(ray_angle_rad if ray_angle_rad is not None else item_dict.get("angle_rad", 0.0))
    except (TypeError, ValueError):
        return

    try:
        ROSClient(robot_id).set_qr_target(
            name=_safe_qr_point_name(str(item_dict.get("text") or "")),
            x=x,
            y=y,
            yaw=yaw,
            text=str(item_dict.get("text") or ""),
            distance_source=str(item_dict.get("distance_source") or "lidar"),
            distance_m=float(item_dict.get("ray_distance_m") or item_dict.get("distance_m") or 0.0),
            map_x_m=x,
            map_y_m=y,
            ray_angle_rad=yaw,
        )
    except Exception as exc:
        logger.warning("Failed to publish qr target for %s: %s", robot_id, exc)


def _detect_and_enrich_qr_items(robot_id: str, frame: np.ndarray) -> DetectionResult:
    result: DetectionResult = detect_qr_items(
        frame=frame,
        camera_matrix=CAMERA_MATRIX,
        dist_coeffs=DIST_COEFFS,
        qr_size_m=QR_SIZE_M,
        deadband_deg=DEADBAND_DEG,
        detect_width=DETECT_WIDTH,
    )
    return enrich_detection_result_with_lidar(robot_id, result)


def enrich_detection_result_with_lidar(robot_id: str, result: DetectionResult) -> DetectionResult:
    """
    Recompute range-related QR overlay values from LiDAR when a matching scan
    point exists for the QR bearing.
    """
    if not result.ok or not result.items:
        return result

    try:
        slam_state = ROSClient(robot_id).get_slam_state_for_ui(
            include_scan_points=True,
            max_scan_points=240,
        )
        pose = slam_state.get("pose") or {}
        scan_points = (slam_state.get("scan") or {}).get("points") or []
    except Exception as exc:
        logger.warning("QR overlay LiDAR enrichment failed for %s: %s", robot_id, exc)
        return result

    if not pose.get("ok") or not scan_points:
        return result

    enriched_items: list[QRItem] = []
    for item in result.items:
        lidar_point = find_first_obstacle_on_ray(
            pose,
            scan_points,
            float(item.angle_rad),
            bearing_offset_rad=CAMERA_LIDAR_YAW_OFFSET_RAD,
            corridor_width_m=QR_LIDAR_CORRIDOR_WIDTH_M,
            min_distance_m=QR_LIDAR_MIN_DISTANCE_M,
        )
        if not lidar_point:
            enriched_items.append(item)
            continue

        try:
            lidar_beam_distance_m = float(lidar_point["dist"])
        except (TypeError, ValueError):
            enriched_items.append(item)
            continue

        if not math.isfinite(lidar_beam_distance_m):
            enriched_items.append(item)
            continue

        ray_distance_m = float(lidar_point.get("ray_distance_m", lidar_beam_distance_m))
        if not math.isfinite(ray_distance_m) or ray_distance_m <= 0.0:
            enriched_items.append(item)
            continue

        ray_angle_rad = float(lidar_point.get("ray_angle_rad", item.angle_rad))
        map_x_m = lidar_point.get("x")
        map_y_m = lidar_point.get("y")
        enriched_items.append(
            _item_with_lidar_ray_hit(
                item,
                ray_distance_m,
                float(map_x_m) if map_x_m is not None else None,
                float(map_y_m) if map_y_m is not None else None,
                ray_angle_rad,
            )
        )

    enriched_items.sort(key=lambda item: item.distance_m)
    return DetectionResult(ok=result.ok, items=enriched_items)


def save_qr_metric_event(robot_id: str, event_type: str, detail: str = "", payload: dict | None = None):
    try:
        from ..models import ActionEvent, Robot
        robot, _ = Robot.objects.get_or_create(pk=robot_id)
        ActionEvent.objects.create(
            robot=robot,
            event="qr_scan_metric",
            status=event_type,
            detail=detail,
            payload=payload or {},
            severity="Info",
        )
        logger.info(f"[QR METRIC] Saved {event_type} for {robot_id}")
    except Exception as e:
        logger.warning(f"Failed to save qr_scan_metric event for {robot_id}: {e}")


def update_qr_tracking_state(robot_id: str, detected_items: list[QRItem]):
    """Chỉ cập nhật trạng thái in_view, KHÔNG log Attempt/Success ở đây."""
    global qr_tracking_state
    if robot_id not in qr_tracking_state:
        qr_tracking_state[robot_id] = {
            "current_text": None,
            "in_view": False,
        }

    state = qr_tracking_state[robot_id]
    current_text = detected_items[0].text.strip() if detected_items else None

    state["in_view"] = bool(current_text)
    state["current_text"] = current_text
    qr_tracking_state[robot_id] = state


def get_current_qr_state(robot_id: str) -> dict:
    """Cho views.py biết QR hiện tại có đang được thấy không."""
    return qr_tracking_state.get(robot_id, {"in_view": False, "current_text": None})


def qr_item_to_dict(item: QRItem) -> Dict[str, Any]:
    distance_source = "lidar"
    if item.lidar_distance_m is None or not math.isfinite(float(item.lidar_distance_m)):
        distance_source = "camera"
    return {
        "text": item.text,
        "qr_type": item.qr_type,
        "angle_deg": item.angle_deg,
        "angle_rad": item.angle_rad,
        "distance_m": item.distance_m,
        "lateral_x_m": item.lateral_x_m,
        "forward_z_m": item.forward_z_m,
        "target_x_m": item.target_x_m,
        "target_z_m": item.target_z_m,
        "target_distance_m": item.target_distance_m,
        "direction": item.direction,
        "center_px": item.center_px,
        "corners": item.corners,
        "camera_distance_m": item.camera_distance_m,
        "lidar_distance_m": item.lidar_distance_m,
        "map_x_m": item.map_x_m,
        "map_y_m": item.map_y_m,
        "ray_distance_m": item.ray_distance_m,
        "ray_angle_rad": item.ray_angle_rad,
        "distance_source": distance_source,
    }


def build_empty_position_payload() -> Dict[str, Any]:
    return {
        "detected": False,
        "qr": None,
        "position": None,
        "target": None,
        "image": None,
        "timestamp": time.time(),
    }


def build_position_payload(item_dict: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "detected": True,
        "qr": {
            "text": item_dict["text"],
            "type": item_dict["qr_type"],
            "direction": item_dict["direction"],
        },
        "position": {
            "angle_deg": item_dict["angle_deg"],
            "angle_rad": item_dict["angle_rad"],
            "distance_m": item_dict["distance_m"],
            "distance_source": item_dict["distance_source"],
            "lateral_x_m": item_dict["lateral_x_m"],
            "forward_z_m": item_dict["forward_z_m"],
        },
        "target": {
            "x_m": item_dict["target_x_m"],
            "z_m": item_dict["target_z_m"],
            "distance_m": item_dict["target_distance_m"],
            "distance_source": item_dict["distance_source"],
        },
        "target_map": {
            "x_m": item_dict["map_x_m"],
            "y_m": item_dict["map_y_m"],
            "distance_m": item_dict["ray_distance_m"],
            "distance_source": item_dict["distance_source"],
        },
        "image": {
            "center_px": {
                "x": int(item_dict["center_px"][0]),
                "y": int(item_dict["center_px"][1]),
            },
            "corners": item_dict["corners"],
        },
        "timestamp": time.time(),
    }


def detect_qr_state_once(robot_id: str) -> Dict[str, Any]:
    client = ROSClient(robot_id)
    frame = client.get_frame()

    if frame is None:
        return {
            "ok": False,
            "items": [],
            "position_json": build_empty_position_payload(),
            "timestamp": time.time(),
            "error": "Cannot read frame from robot camera",
        }

    result = _detect_and_enrich_qr_items(robot_id, frame)

    # === TRACKING QR METRICS ===
    update_qr_tracking_state(robot_id, result.items)

    if not result.ok or not result.items:
        warning = None
        if not PYZBAR_AVAILABLE and PYZBAR_IMPORT_ERROR:
            warning = (
                "pyzbar/libzbar is unavailable, using OpenCV QR fallback. "
                f"Original import error: {PYZBAR_IMPORT_ERROR}"
            )
        return {
            "ok": False,
            "items": [],
            "position_json": build_empty_position_payload(),
            "timestamp": time.time(),
            "warning": warning,
        }

    items = [qr_item_to_dict(item) for item in result.items]
    first = items[0]
    _publish_qr_target(robot_id, first)

    return {
        "ok": True,
        "text": first["text"],
        "angle_deg": first["angle_deg"],
        "angle_rad": first["angle_rad"],
        "distance_m": first["distance_m"],
        "distance_source": first["distance_source"],
        "lateral_x_m": first["lateral_x_m"],
        "forward_z_m": first["forward_z_m"],
        "target_x_m": first["target_x_m"],
        "target_z_m": first["target_z_m"],
        "target_distance_m": first["target_distance_m"],
        "map_x_m": first["map_x_m"],
        "map_y_m": first["map_y_m"],
        "ray_distance_m": first["ray_distance_m"],
        "ray_angle_rad": first["ray_angle_rad"],
        "direction": first["direction"],
        "items": items,
        "position_json": build_position_payload(first),
        "timestamp": time.time(),
    }


def generate_qr_video_frames(robot_id: str):
    client = ROSClient(robot_id)
    stream_url = client.get_fpv_url()

    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open robot camera stream: {stream_url}")

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)]

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            result = _detect_and_enrich_qr_items(robot_id, frame)

            # Tracking metrics ngay cả trong video stream
            update_qr_tracking_state(robot_id, result.items)
            if result.ok and result.items:
                _publish_qr_target(robot_id, qr_item_to_dict(result.items[0]))

            vis = draw_overlay(frame, result)

            ok, buffer = cv2.imencode(".jpg", vis, encode_param)
            if not ok:
                continue

            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
    finally:
        cap.release()
