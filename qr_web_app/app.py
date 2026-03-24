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
)
from state import latest_state
from camera import create_camera, read_frame
from qr_detector import detect_qr_items
from overlay import draw_overlay


app = Flask(__name__, template_folder="templates")
cap = create_camera(CAMERA_SOURCE)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/qr_state")
def qr_state():
    return jsonify(latest_state)


def generate_frames():
    if not cap.isOpened():
        raise RuntimeError("Cannot open camera")

    while True:
        ok, frame = read_frame(cap, flip_frame=FLIP_FRAME)
        if not ok:
            continue

        result = detect_qr_items(
            frame=frame,
            camera_matrix=CAMERA_MATRIX,
            dist_coeffs=DIST_COEFFS,
            qr_size_m=QR_SIZE_M,
            deadband_deg=DEADBAND_DEG,
        )

        latest_state["ok"] = result.ok
        latest_state["items"] = [
            {
                "text": item.text,
                "qr_type": item.qr_type,
                "angle_deg": item.angle_deg,
                "angle_rad": item.angle_rad,
                "distance_m": item.distance_m,
                "lateral_x_m": item.lateral_x_m,
                "forward_z_m": item.forward_z_m,
                "direction": item.direction,
                "center_px": item.center_px,
                "corners": item.corners,
            }
            for item in result.items
        ]
        latest_state["timestamp"] = time.time()

        vis = draw_overlay(frame, result)

        ret, buffer = cv2.imencode(".jpg", vis)
        if not ret:
            continue

        frame_bytes = buffer.tobytes()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    print(f"Open: http://127.0.0.1:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, threaded=True)