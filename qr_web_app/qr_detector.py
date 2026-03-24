import math
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from models import QRItem, DetectionResult


def order_points_from_polygon(polygon):
    pts = np.array([[p.x, p.y] for p in polygon], dtype=np.float32)

    if len(pts) != 4:
        x, y, w, h = cv2.boundingRect(pts.astype(np.int32))
        pts = np.array([
            [x, y],
            [x + w, y],
            [x + w, y + h],
            [x, y + h],
        ], dtype=np.float32)

    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)

    top_left = pts[np.argmin(s)]
    bottom_right = pts[np.argmax(s)]
    top_right = pts[np.argmin(d)]
    bottom_left = pts[np.argmax(d)]

    return np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)


def get_qr_object_points(qr_size_m):
    s = qr_size_m / 2.0
    return np.array([
        [-s, -s, 0.0],
        [ s, -s, 0.0],
        [ s,  s, 0.0],
        [-s,  s, 0.0],
    ], dtype=np.float32)


def estimate_pose(img_points, camera_matrix, dist_coeffs, qr_size_m):
    obj_points = get_qr_object_points(qr_size_m)

    success, rvec, tvec = cv2.solvePnP(
        obj_points,
        img_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_IPPE_SQUARE
    )

    if not success:
        success, rvec, tvec = cv2.solvePnP(
            obj_points,
            img_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )

    if not success:
        return False, None, None

    return True, rvec, tvec


def classify_direction(angle_deg, deadband_deg=5.0):
    if angle_deg > deadband_deg:
        return "right"
    if angle_deg < -deadband_deg:
        return "left"
    return "center"


def detect_qr_items(frame, camera_matrix, dist_coeffs, qr_size_m, deadband_deg=5.0):
    decoded = decode(frame)
    items = []

    for qr in decoded:
        try:
            qr_text = qr.data.decode("utf-8").strip()
        except Exception:
            qr_text = str(qr.data)

        qr_type = qr.type

        if qr.polygon and len(qr.polygon) >= 4:
            img_points = order_points_from_polygon(qr.polygon)
        else:
            x, y, w, h = qr.rect
            img_points = np.array([
                [x, y],
                [x + w, y],
                [x + w, y + h],
                [x, y + h],
            ], dtype=np.float32)

        ok, rvec, tvec = estimate_pose(img_points, camera_matrix, dist_coeffs, qr_size_m)
        if not ok:
            continue

        tx = float(tvec[0][0])
        tz = float(tvec[2][0])

        angle_rad = math.atan2(tx, tz)
        angle_deg = math.degrees(angle_rad)
        distance_m = math.sqrt(tx * tx + tz * tz)
        direction = classify_direction(angle_deg, deadband_deg)

        center = np.mean(img_points, axis=0).astype(int)

        item = QRItem(
            text=qr_text,
            qr_type=qr_type,
            angle_deg=angle_deg,
            angle_rad=angle_rad,
            distance_m=distance_m,
            lateral_x_m=tx,
            forward_z_m=tz,
            direction=direction,
            center_px=(int(center[0]), int(center[1])),
            corners=img_points.astype(int).tolist(),
        )
        items.append(item)

    return DetectionResult(ok=len(items) > 0, items=items)