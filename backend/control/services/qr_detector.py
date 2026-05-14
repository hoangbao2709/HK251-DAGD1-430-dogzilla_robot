import math
import cv2
import numpy as np
from .models import QRItem, DetectionResult

try:
    from pyzbar.pyzbar import decode as pyzbar_decode  # type: ignore[import-untyped]
    PYZBAR_AVAILABLE = True
    PYZBAR_IMPORT_ERROR = None
except Exception as exc:
    pyzbar_decode = None
    PYZBAR_AVAILABLE = False
    PYZBAR_IMPORT_ERROR = str(exc)


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


def build_effective_camera_matrix(camera_matrix, frame_shape):
    """
    Scale intrinsic matrix theo kích thước frame thực tế.
    Ma trận config hiện tại đang ngầm cho frame chuẩn 1280x720
    vì cx=640, cy=360. Nếu stream thực tế là 640x360 thì phải scale,
    nếu không mọi điểm gần như luôn nằm bên trái tâm ảnh.
    """
    h, w = frame_shape[:2]

    ref_cx = float(camera_matrix[0, 2])
    ref_cy = float(camera_matrix[1, 2])
    ref_w = ref_cx * 2.0 if ref_cx > 0 else float(w)
    ref_h = ref_cy * 2.0 if ref_cy > 0 else float(h)

    sx = float(w) / ref_w if ref_w > 1e-6 else 1.0
    sy = float(h) / ref_h if ref_h > 1e-6 else 1.0

    k = camera_matrix.astype(np.float32).copy()
    k[0, 0] *= sx
    k[0, 2] *= sx
    k[1, 1] *= sy
    k[1, 2] *= sy
    return k


def estimate_pose(img_points, camera_matrix, dist_coeffs, qr_size_m):
    obj_points = get_qr_object_points(qr_size_m)

    success, rvec, tvec = cv2.solvePnP(
        obj_points,
        img_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE
    )

    if not success:
        success, rvec, tvec = cv2.solvePnP(
            obj_points,
            img_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_IPPE_SQUARE
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


def normalize_forward_pose(tz):
    return abs(tz)


def compute_lateral_from_image_center(center_x_px, tz, camera_matrix):
    fx = float(camera_matrix[0, 0])
    cx = float(camera_matrix[0, 2])

    # Công thức pinhole: X = (u - cx) / fx * Z
    tx = ((float(center_x_px) - cx) / fx) * tz
    return tx


def compute_target_point(tx, tz):
    return None, None, None


def preprocess_for_qr(frame, detect_width=640):
    h, w = frame.shape[:2]

    if w > detect_width:
        scale = detect_width / float(w)
        resized = cv2.resize(frame, (int(w * scale), int(h * scale)))
    else:
        scale = 1.0
        resized = frame.copy()

    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    return gray, scale


def _build_pyzbar_rect(polygon):
    pts = np.array([[p.x, p.y] for p in polygon], dtype=np.float32)
    x, y, w, h = cv2.boundingRect(pts.astype(np.int32))
    return x, y, w, h


def _decode_with_opencv(gray):
    detector = cv2.QRCodeDetector()
    detected = detector.detectAndDecodeMulti(gray)

    if len(detected) == 4:
        retval, decoded_info, points, _ = detected
    else:
        decoded_info, points, _ = detected
        retval = bool(decoded_info)

    if not retval or points is None:
        return []

    decoded_items = []
    for text, quad in zip(decoded_info, points):
        if quad is None:
            continue

        quad = np.array(quad, dtype=np.float32).reshape(-1, 2)
        if quad.shape[0] < 4:
            continue

        polygon = [
            type("Point", (), {"x": float(pt[0]), "y": float(pt[1])})()
            for pt in quad[:4]
        ]
        rect = _build_pyzbar_rect(polygon)
        payload = text if text else ""
        decoded_items.append(
            type(
                "DecodedQR",
                (),
                {
                    "data": payload.encode("utf-8"),
                    "type": "QRCODE",
                    "polygon": polygon,
                    "rect": rect,
                },
            )()
        )

    return decoded_items


def decode_qr_fast(frame, detect_width=640):
    gray, scale = preprocess_for_qr(frame, detect_width=detect_width)
    if PYZBAR_AVAILABLE and pyzbar_decode is not None:
        decoded = pyzbar_decode(gray)
    else:
        decoded = _decode_with_opencv(gray)
    return decoded, scale


def detect_qr_items(
    frame,
    camera_matrix,
    dist_coeffs,
    qr_size_m,
    deadband_deg=5.0,
    detect_width=640,
):
    decoded, scale = decode_qr_fast(frame, detect_width=detect_width)
    items = []
    effective_camera_matrix = build_effective_camera_matrix(camera_matrix, frame.shape)

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

        if scale > 0:
            img_points = img_points / scale

        ok, rvec, tvec = estimate_pose(img_points, effective_camera_matrix, dist_coeffs, qr_size_m)
        if not ok:
            continue

        tz_raw = float(tvec[2][0])
        tz = normalize_forward_pose(tz_raw)

        center = np.mean(img_points, axis=0)
        center_x = float(center[0])
        center_y = float(center[1])

        tx = compute_lateral_from_image_center(center_x, tz, effective_camera_matrix)

        angle_rad = math.atan2(tx, tz)
        angle_deg = math.degrees(angle_rad)
        # Camera/PnP only provides a provisional range estimate.
        direction = classify_direction(angle_deg, deadband_deg)

        target_x, target_z, target_distance = compute_target_point(tx, tz)

        item = QRItem(
            text=qr_text,
            qr_type=qr_type,
            angle_deg=angle_deg,
            angle_rad=angle_rad,
            distance_m=None,
            lateral_x_m=None,
            forward_z_m=None,
            target_x_m=target_x,
            target_z_m=target_z,
            target_distance_m=target_distance,
            direction=direction,
            center_px=(int(center_x), int(center_y)),
            corners=img_points.astype(int).tolist(),
            camera_distance_m=None,
            lidar_distance_m=None,
        )
        items.append(item)

    items.sort(
        key=lambda it: it.lidar_distance_m
        if it.lidar_distance_m is not None and math.isfinite(float(it.lidar_distance_m))
        else float("inf")
    )
    return DetectionResult(ok=len(items) > 0, items=items)
