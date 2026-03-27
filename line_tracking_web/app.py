from flask import Flask, Response, jsonify, render_template
import cv2
import threading
import time
import numpy as np

from vision import LineTracker
from robot_api import RobotAPI

app = Flask(__name__)

CAMERA_URL = "http://192.168.1.6:9000/camera"

tracker = LineTracker()
robot_api = RobotAPI(base_url="http://192.168.1.6:8000", timeout=0.35)

lock = threading.Lock()
running = True
tracking_enabled = True

# ===== shared data =====
latest_raw_frame = None
latest_result = None

latest_original_jpeg = None
latest_error_jpeg = None

latest_state = {
    "status": "INIT",
    "forward": 0,
    "turn": 0,
    "robot_response": None,
    "tracking_enabled": True,
    "last_sent_forward": 0,
    "last_sent_turn": 0,
    "last_send_reason": "init",
    "send_interval_ms": 150,
}

# ===== throttle gửi robot =====
SEND_INTERVAL = 0.15
FORWARD_EPS = 2
TURN_EPS = 6
FORCE_RESEND_INTERVAL = 0.60

last_sent_forward = 0
last_sent_turn = 0
last_send_time = 0.0
last_sent_status = "INIT"
last_send_reason = "init"

# ===== web render =====
WEB_FPS = 8
WEB_JPEG_QUALITY = 55
WEB_WIDTH = 640
WEB_HEIGHT = 360


def to_py_num(v):
    if v is None:
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    return v


def sanitize_for_json(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = sanitize_for_json(v)
        else:
            out[k] = to_py_num(v)
    return out


def open_camera():
    cap = cv2.VideoCapture(CAMERA_URL)
    if not cap.isOpened():
        print(f"[Camera] Khong mo duoc camera: {CAMERA_URL}")
    else:
        print(f"[Camera] Opened: {CAMERA_URL}")
    return cap


def draw_error_view(morph, result):
    view = cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR)
    h, w = morph.shape[:2]
    center_x = w // 2

    y_bottom = int(h * 0.88)
    y_mid = int(h * 0.60)
    y_top = int(h * 0.30)

    cv2.line(view, (center_x, 0), (center_x, h), (255, 0, 0), 2)

    for y in [y_bottom, y_mid, y_top]:
        cv2.line(view, (0, y), (w, y), (0, 255, 255), 1)

    pts = []
    if result["x_bottom"] is not None:
        pts.append((int(result["x_bottom"]), y_bottom))
        cv2.circle(view, (int(result["x_bottom"]), y_bottom), 7, (0, 0, 255), -1)
    if result["x_mid"] is not None:
        pts.append((int(result["x_mid"]), y_mid))
        cv2.circle(view, (int(result["x_mid"]), y_mid), 7, (0, 255, 0), -1)
    if result["x_top"] is not None:
        pts.append((int(result["x_top"]), y_top))
        cv2.circle(view, (int(result["x_top"]), y_top), 7, (255, 0, 255), -1)

    for i in range(len(pts) - 1):
        cv2.line(view, pts[i], pts[i + 1], (255, 255, 0), 2)

    lines = [
        f"status={result['status']}",
        f"e_lat={result['e_lat']}",
        f"e_heading={result['e_heading']}",
        f"e_mix={result['e_mix']}",
        f"forward={result['forward']}",
        f"turn={result['turn']}",
    ]

    y0 = 30
    for line in lines:
        cv2.putText(view, line, (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
        y0 += 28

    return view


def should_send_command(forward, turn, status, now):
    global last_sent_forward, last_sent_turn, last_send_time, last_sent_status, last_send_reason

    if status == "NO_LINE":
        if last_sent_status != "NO_LINE" or last_sent_forward != 0 or last_sent_turn != 0:
            last_send_reason = "force_stop_no_line"
            return True
        return False

    if last_send_time == 0:
        last_send_reason = "first_send"
        return True

    if now - last_send_time < SEND_INTERVAL:
        return False

    forward_changed = abs(forward - last_sent_forward) >= FORWARD_EPS
    turn_changed = abs(turn - last_sent_turn) >= TURN_EPS
    status_changed = status != last_sent_status
    stale = (now - last_send_time) >= FORCE_RESEND_INTERVAL

    if forward_changed:
        last_send_reason = "forward_changed"
        return True
    if turn_changed:
        last_send_reason = "turn_changed"
        return True
    if status_changed:
        last_send_reason = "status_changed"
        return True
    if stale:
        last_send_reason = "keepalive_resend"
        return True

    return False


def send_robot_command(result):
    global last_sent_forward, last_sent_turn, last_send_time, last_sent_status, last_send_reason

    now = time.time()
    status = result["status"]
    forward = int(result["forward"])
    turn = int(result["turn"])

    if status == "NO_LINE":
        robot_resp = robot_api.stop()
        last_sent_forward = 0
        last_sent_turn = 0
        last_sent_status = "NO_LINE"
        last_send_time = now
        last_send_reason = "force_stop_no_line"
        return robot_resp

    if not should_send_command(forward, turn, status, now):
        return {
            "ok": True,
            "message": "command skipped by throttle",
            "skipped": True,
            "last_sent_forward": last_sent_forward,
            "last_sent_turn": last_sent_turn,
            "reason": "too_soon_or_change_too_small"
        }

    robot_resp = robot_api.send_move(forward=forward, turn=turn)

    last_sent_forward = forward
    last_sent_turn = turn
    last_sent_status = status
    last_send_time = now

    return robot_resp


def process_loop():
    global latest_raw_frame, latest_result, latest_state, tracking_enabled

    cap = open_camera()
    last_reconnect_time = 0

    while running:
        if cap is None or not cap.isOpened():
            if time.time() - last_reconnect_time > 1.0:
                last_reconnect_time = time.time()
                cap = open_camera()
            time.sleep(0.1)
            continue

        ret, frame = cap.read()
        if not ret:
            print("[Camera] Mat frame, reconnect...")
            cap.release()
            cap = None
            time.sleep(0.2)
            continue

        result = tracker.process(frame)

        with lock:
            latest_raw_frame = frame.copy()
            latest_result = result
            current_tracking_enabled = tracking_enabled

        if current_tracking_enabled:
            robot_resp = send_robot_command(result)
        else:
            robot_resp = {
                "ok": True,
                "message": "Tracking paused by user",
                "skipped": True,
                "reason": "paused"
            }

        state_data = sanitize_for_json({
            "status": result["status"],
            "x_bottom": result["x_bottom"],
            "x_mid": result["x_mid"],
            "x_top": result["x_top"],
            "e_lat": result["e_lat"],
            "e_heading": result["e_heading"],
            "e_mix": result["e_mix"],
            "forward": result["forward"],
            "turn": result["turn"],
            "robot_response": robot_resp,
            "tracking_enabled": current_tracking_enabled,
            "last_sent_forward": last_sent_forward,
            "last_sent_turn": last_sent_turn,
            "last_send_reason": last_send_reason,
            "send_interval_ms": int(SEND_INTERVAL * 1000),
        })

        with lock:
            latest_state = state_data

        time.sleep(0.01)


def web_render_loop():
    global latest_original_jpeg, latest_error_jpeg

    interval = 1.0 / WEB_FPS

    while running:
        start = time.time()

        with lock:
            frame = None if latest_raw_frame is None else latest_raw_frame.copy()
            result = None if latest_result is None else dict(latest_result)

        if frame is not None and result is not None:
            display_original = frame.copy()
            h, w = display_original.shape[:2]
            roi_top = int(result["roi_top"])

            cv2.rectangle(display_original, (0, roi_top), (w, h), (0, 255, 255), 2)

            error_view = draw_error_view(result["morph"], result)

            display_original_small = cv2.resize(display_original, (WEB_WIDTH, WEB_HEIGHT))
            error_view_small = cv2.resize(error_view, (WEB_WIDTH, WEB_HEIGHT))

            ok1, enc1 = cv2.imencode(
                ".jpg",
                display_original_small,
                [int(cv2.IMWRITE_JPEG_QUALITY), WEB_JPEG_QUALITY]
            )
            ok2, enc2 = cv2.imencode(
                ".jpg",
                error_view_small,
                [int(cv2.IMWRITE_JPEG_QUALITY), WEB_JPEG_QUALITY]
            )

            if ok1 and ok2:
                with lock:
                    latest_original_jpeg = enc1.tobytes()
                    latest_error_jpeg = enc2.tobytes()

        elapsed = time.time() - start
        sleep_time = max(0, interval - elapsed)
        time.sleep(sleep_time)


def mjpeg_generator(mode):
    while True:
        with lock:
            frame = latest_original_jpeg if mode == "original" else latest_error_jpeg

        if frame is None:
            time.sleep(0.03)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )

        time.sleep(0.01)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video/original")
def video_original():
    return Response(
        mjpeg_generator("original"),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/video/error")
def video_error():
    return Response(
        mjpeg_generator("error"),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/state")
def state():
    with lock:
        return jsonify(sanitize_for_json(latest_state))


@app.route("/tracking/pause", methods=["POST"])
def tracking_pause():
    global tracking_enabled, last_sent_forward, last_sent_turn, last_sent_status, last_send_time, last_send_reason

    with lock:
        tracking_enabled = False

    robot_resp = robot_api.stop()

    last_sent_forward = 0
    last_sent_turn = 0
    last_sent_status = "PAUSED"
    last_send_time = time.time()
    last_send_reason = "manual_pause_stop"

    with lock:
        latest_state["tracking_enabled"] = False
        latest_state["robot_response"] = robot_resp
        latest_state["last_sent_forward"] = 0
        latest_state["last_sent_turn"] = 0
        latest_state["last_send_reason"] = last_send_reason

    return jsonify({
        "ok": True,
        "tracking_enabled": False,
        "robot_response": robot_resp
    })


@app.route("/tracking/resume", methods=["POST"])
def tracking_resume():
    global tracking_enabled, last_send_time, last_send_reason

    with lock:
        tracking_enabled = True
        latest_state["tracking_enabled"] = True

    last_send_time = 0.0
    last_send_reason = "manual_resume"

    return jsonify({
        "ok": True,
        "tracking_enabled": True,
        "message": "Tracking resumed"
    })


if __name__ == "__main__":
    t1 = threading.Thread(target=process_loop, daemon=True)
    t2 = threading.Thread(target=web_render_loop, daemon=True)

    t1.start()
    t2.start()

    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)