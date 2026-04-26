import time
from typing import Any, Dict

import cv2
import numpy as np

from .ros import ROSClient
from .models import QRItem, DetectionResult
from .qr_detector import detect_qr_items, PYZBAR_AVAILABLE, PYZBAR_IMPORT_ERROR
from .overlay import draw_overlay

# Django models cho việc lưu event
from ..models import ActionEvent
import logging

logger = logging.getLogger(__name__)

QR_SIZE_M = 0.12
DEADBAND_DEG = 5.0
TARGET_PUSH_M = 0.35
MIN_TARGET_DISTANCE_M = 0.65
DETECT_WIDTH = 640
JPEG_QUALITY = 72

CAMERA_MATRIX = np.array([
    [920.0, 0.0, 640.0],
    [0.0, 920.0, 360.0],
    [0.0, 0.0, 1.0],
], dtype=np.float32)

DIST_COEFFS = np.array([0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)

# Trạng thái tracking QR per robot
qr_tracking_state: dict[str, dict] = {}


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
            "lateral_x_m": item_dict["lateral_x_m"],
            "forward_z_m": item_dict["forward_z_m"],
        },
        "target": {
            "x_m": item_dict["target_x_m"],
            "z_m": item_dict["target_z_m"],
            "distance_m": item_dict["target_distance_m"],
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

    result: DetectionResult = detect_qr_items(
        frame=frame,
        camera_matrix=CAMERA_MATRIX,
        dist_coeffs=DIST_COEFFS,
        qr_size_m=QR_SIZE_M,
        deadband_deg=DEADBAND_DEG,
        target_push_m=TARGET_PUSH_M,
        min_target_distance_m=MIN_TARGET_DISTANCE_M,
        detect_width=DETECT_WIDTH,
    )

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

    return {
        "ok": True,
        "text": first["text"],
        "angle_deg": first["angle_deg"],
        "angle_rad": first["angle_rad"],
        "distance_m": first["distance_m"],
        "lateral_x_m": first["lateral_x_m"],
        "forward_z_m": first["forward_z_m"],
        "target_x_m": first["target_x_m"],
        "target_z_m": first["target_z_m"],
        "target_distance_m": first["target_distance_m"],
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

            result: DetectionResult = detect_qr_items(
                frame=frame,
                camera_matrix=CAMERA_MATRIX,
                dist_coeffs=DIST_COEFFS,
                qr_size_m=QR_SIZE_M,
                deadband_deg=DEADBAND_DEG,
                target_push_m=TARGET_PUSH_M,
                min_target_distance_m=MIN_TARGET_DISTANCE_M,
                detect_width=DETECT_WIDTH,
            )

            # Tracking metrics ngay cả trong video stream
            update_qr_tracking_state(robot_id, result.items)

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
