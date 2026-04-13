import time
import cv2
from flask import Flask, Response, jsonify, render_template

from config import (
    CAMERA_SOURCE,
    CAMERA_MATRIX,
    DIST_COEFFS,
    QR_SIZE_M,
    DEADBAND_DEG,
    FLASK_HOST,
    FLASK_PORT,
    FLIP_FRAME,
    TARGET_PUSH_M,
    MIN_TARGET_DISTANCE_M,
    DETECT_INTERVAL_SEC,
    LOST_HOLD_SEC,
    SMOOTH_ALPHA,
    DETECT_WIDTH,
    JPEG_QUALITY,
)
from state import latest_state
from camera import create_camera, read_frame
from qr_detector import detect_qr_items
from overlay import draw_overlay


app = Flask(__name__, template_folder="templates")
cap = create_camera(CAMERA_SOURCE)

last_detect_time = 0.0
last_good_result = None
last_good_time = 0.0


def ema(prev, new, alpha):
    return prev * (1.0 - alpha) + new * alpha


def qr_item_to_dict(item):
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


def smooth_item(prev_item, new_item, alpha):
    if prev_item is None:
        return qr_item_to_dict(new_item)

    if prev_item["text"] != new_item.text:
        return qr_item_to_dict(new_item)

    angle_deg = ema(prev_item["angle_deg"], new_item.angle_deg, alpha)
    angle_rad = ema(prev_item["angle_rad"], new_item.angle_rad, alpha)
    distance_m = ema(prev_item["distance_m"], new_item.distance_m, alpha)
    lateral_x_m = ema(prev_item["lateral_x_m"], new_item.lateral_x_m, alpha)
    forward_z_m = ema(prev_item["forward_z_m"], new_item.forward_z_m, alpha)
    target_x_m = ema(prev_item["target_x_m"], new_item.target_x_m, alpha)
    target_z_m = ema(prev_item["target_z_m"], new_item.target_z_m, alpha)
    target_distance_m = ema(prev_item["target_distance_m"], new_item.target_distance_m, alpha)

    center_px = (
        int(ema(prev_item["center_px"][0], new_item.center_px[0], alpha)),
        int(ema(prev_item["center_px"][1], new_item.center_px[1], alpha)),
    )

    prev_corners = prev_item["corners"]
    new_corners = new_item.corners
    corners = []
    for i in range(min(len(prev_corners), len(new_corners))):
        corners.append([
            int(ema(prev_corners[i][0], new_corners[i][0], alpha)),
            int(ema(prev_corners[i][1], new_corners[i][1], alpha)),
        ])

    if angle_deg > DEADBAND_DEG:
        direction = "right"
    elif angle_deg < -DEADBAND_DEG:
        direction = "left"
    else:
        direction = "center"

    return {
        "text": new_item.text,
        "qr_type": new_item.qr_type,
        "angle_deg": angle_deg,
        "angle_rad": angle_rad,
        "distance_m": distance_m,
        "lateral_x_m": lateral_x_m,
        "forward_z_m": forward_z_m,
        "target_x_m": target_x_m,
        "target_z_m": target_z_m,
        "target_distance_m": target_distance_m,
        "direction": direction,
        "center_px": center_px,
        "corners": corners,
    }


def build_position_payload(item_dict):
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


def build_empty_position_payload():
    return {
        "detected": False,
        "qr": None,
        "position": None,
        "target": None,
        "image": None,
        "timestamp": time.time(),
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/qr_state")
def qr_state():
    return jsonify(latest_state)


@app.route("/qr_position")
def qr_position():
    return jsonify(latest_state.get("position_json") or build_empty_position_payload())


def apply_state_from_item(item_dict):
    latest_state["ok"] = True
    latest_state["text"] = item_dict["text"]
    latest_state["angle_deg"] = item_dict["angle_deg"]
    latest_state["angle_rad"] = item_dict["angle_rad"]
    latest_state["distance_m"] = item_dict["distance_m"]
    latest_state["lateral_x_m"] = item_dict["lateral_x_m"]
    latest_state["forward_z_m"] = item_dict["forward_z_m"]
    latest_state["target_x_m"] = item_dict["target_x_m"]
    latest_state["target_z_m"] = item_dict["target_z_m"]
    latest_state["target_distance_m"] = item_dict["target_distance_m"]
    latest_state["direction"] = item_dict["direction"]
    latest_state["items"] = [item_dict]
    latest_state["timestamp"] = time.time()
    latest_state["position_json"] = build_position_payload(item_dict)


def apply_empty_state():
    latest_state["ok"] = False
    latest_state["text"] = ""
    latest_state["angle_deg"] = 0.0
    latest_state["angle_rad"] = 0.0
    latest_state["distance_m"] = 0.0
    latest_state["lateral_x_m"] = 0.0
    latest_state["forward_z_m"] = 0.0
    latest_state["target_x_m"] = 0.0
    latest_state["target_z_m"] = 0.0
    latest_state["target_distance_m"] = 0.0
    latest_state["direction"] = "none"
    latest_state["items"] = []
    latest_state["timestamp"] = time.time()
    latest_state["position_json"] = build_empty_position_payload()


def build_visual_result(frame):
    global last_detect_time, last_good_result, last_good_time

    now = time.time()
    should_detect = (now - last_detect_time) >= DETECT_INTERVAL_SEC

    if should_detect:
        last_detect_time = now

        result = detect_qr_items(
            frame=frame,
            camera_matrix=CAMERA_MATRIX,
            dist_coeffs=DIST_COEFFS,
            qr_size_m=QR_SIZE_M,
            deadband_deg=DEADBAND_DEG,
            target_push_m=TARGET_PUSH_M,
            min_target_distance_m=MIN_TARGET_DISTANCE_M,
            detect_width=DETECT_WIDTH,
        )

        if result.ok and result.items:
            prev_item = latest_state["items"][0] if latest_state["items"] else None
            smoothed = smooth_item(prev_item, result.items[0], SMOOTH_ALPHA)

            apply_state_from_item(smoothed)
            last_good_result = {
                "ok": True,
                "items": [smoothed],
            }
            last_good_time = now
        else:
            if last_good_result is not None and (now - last_good_time) <= LOST_HOLD_SEC:
                apply_state_from_item(last_good_result["items"][0])
            else:
                apply_empty_state()

    if latest_state["ok"] and latest_state["items"]:
        class _Obj:
            pass

        vis_result = _Obj()
        vis_result.ok = True
        vis_result.items = []

        for item in latest_state["items"]:
            obj = _Obj()
            obj.text = item["text"]
            obj.qr_type = item["qr_type"]
            obj.angle_deg = item["angle_deg"]
            obj.angle_rad = item["angle_rad"]
            obj.distance_m = item["distance_m"]
            obj.lateral_x_m = item["lateral_x_m"]
            obj.forward_z_m = item["forward_z_m"]
            obj.target_x_m = item["target_x_m"]
            obj.target_z_m = item["target_z_m"]
            obj.target_distance_m = item["target_distance_m"]
            obj.direction = item["direction"]
            obj.center_px = item["center_px"]
            obj.corners = item["corners"]
            vis_result.items.append(obj)

        return vis_result

    class _Empty:
        ok = False
        items = []

    return _Empty()


def generate_frames():
    if not cap.isOpened():
        raise RuntimeError("Cannot open camera")

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)]

    try:
        while True:
            ok, frame = read_frame(cap, flip_frame=FLIP_FRAME)
            if not ok:
                continue

            result_for_overlay = build_visual_result(frame)
            vis = draw_overlay(frame, result_for_overlay)

            ret, buffer = cv2.imencode(".jpg", vis, encode_param)
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
    except GeneratorExit:
        return
    except Exception as e:
        print("Stream error:", e)
        return


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    print(f"Open: http://127.0.0.1:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, threaded=True)