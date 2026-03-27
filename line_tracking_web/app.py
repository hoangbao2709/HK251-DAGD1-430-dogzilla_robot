from flask import Flask, Response, jsonify, render_template, request
import cv2
import threading
import time

from vision import LineTracker
from robot_api import RobotAPI

app = Flask(__name__)

cap = cv2.VideoCapture("http://10.28.129.110:9000/camera")
# cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

tracker = LineTracker()
robot_api = RobotAPI(base_url="http://10.28.129.110:8000", timeout=0.35)

latest_original = None
latest_error = None
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

lock = threading.Lock()
running = True
tracking_enabled = True

# ===== Throttle / debounce gửi lệnh =====
SEND_INTERVAL = 0.15          # 150 ms
FORWARD_EPS = 2               # chỉ gửi lại nếu forward đổi từ 2 đơn vị trở lên
TURN_EPS = 6                  # chỉ gửi lại nếu turn đổi từ 6 đơn vị trở lên
FORCE_RESEND_INTERVAL = 0.60  # dù lệnh không đổi, 0.6s gửi lại 1 lần để giữ trạng thái

last_sent_forward = 0
last_sent_turn = 0
last_send_time = 0.0
last_sent_status = "INIT"
last_send_reason = "init"


def draw_error_view(morph, result):
    view = cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR)
    h, w = morph.shape[:2]
    center_x = w // 2

    y_bottom = int(h * 0.85)
    y_mid = int(h * 0.55)
    y_top = int(h * 0.25)

    cv2.line(view, (center_x, 0), (center_x, h), (255, 0, 0), 2)

    for y in [y_bottom, y_mid, y_top]:
        cv2.line(view, (0, y), (w, y), (0, 255, 255), 1)

    pts = []
    if result["x_bottom"] is not None:
        pts.append((result["x_bottom"], y_bottom))
        cv2.circle(view, (result["x_bottom"], y_bottom), 7, (0, 0, 255), -1)
    if result["x_mid"] is not None:
        pts.append((result["x_mid"], y_mid))
        cv2.circle(view, (result["x_mid"], y_mid), 7, (0, 255, 0), -1)
    if result["x_top"] is not None:
        pts.append((result["x_top"], y_top))
        cv2.circle(view, (result["x_top"], y_top), 7, (255, 0, 255), -1)

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

    # STOP hoặc mất line phải ưu tiên gửi ngay
    if status == "NO_LINE":
        if last_sent_status != "NO_LINE" or last_sent_forward != 0 or last_sent_turn != 0:
            last_send_reason = "force_stop_no_line"
            return True
        return False

    # nếu chưa từng gửi thì gửi ngay
    if last_send_time == 0:
        last_send_reason = "first_send"
        return True

    # chưa tới chu kỳ gửi tối thiểu thì không gửi
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


def update_loop():
    global latest_original, latest_error, latest_state, tracking_enabled

    while running:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.02)
            continue

        result = tracker.process(frame)

        display_original = frame.copy()
        h, w = frame.shape[:2]
        roi_top = result["roi_top"]
        cv2.rectangle(display_original, (0, roi_top), (w, h), (0, 255, 255), 2)

        error_view = draw_error_view(result["morph"], result)

        with lock:
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

        ok1, enc1 = cv2.imencode(".jpg", display_original)
        ok2, enc2 = cv2.imencode(".jpg", error_view)

        if ok1 and ok2:
            with lock:
                latest_original = enc1.tobytes()
                latest_error = enc2.tobytes()
                latest_state = {
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
                    "tracking_enabled": tracking_enabled,
                    "last_sent_forward": last_sent_forward,
                    "last_sent_turn": last_sent_turn,
                    "last_send_reason": last_send_reason,
                    "send_interval_ms": int(SEND_INTERVAL * 1000),
                }

        time.sleep(0.01)


def mjpeg_generator(mode):
    while True:
        with lock:
            frame = latest_original if mode == "original" else latest_error

        if frame is None:
            time.sleep(0.03)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )


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
        return jsonify(latest_state)


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
        latest_state["tracking_enabled"] = tracking_enabled
        latest_state["robot_response"] = robot_resp
        latest_state["last_sent_forward"] = last_sent_forward
        latest_state["last_sent_turn"] = last_sent_turn
        latest_state["last_send_reason"] = last_send_reason

    return jsonify({
        "ok": True,
        "tracking_enabled": tracking_enabled,
        "robot_response": robot_resp
    })


@app.route("/tracking/resume", methods=["POST"])
def tracking_resume():
    global tracking_enabled, last_send_time, last_send_reason

    with lock:
        tracking_enabled = True
        latest_state["tracking_enabled"] = tracking_enabled

    # cho phép gửi lại ngay sau khi resume
    last_send_time = 0.0
    last_send_reason = "manual_resume"

    return jsonify({
        "ok": True,
        "tracking_enabled": tracking_enabled,
        "message": "Tracking resumed"
    })


if __name__ == "__main__":
    t = threading.Thread(target=update_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)