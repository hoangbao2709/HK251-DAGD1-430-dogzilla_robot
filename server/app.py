#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import threading
from typing import Optional

import cv2 as cv
import numpy as np
import requests
from flask import Flask, Response, jsonify, render_template, request

from line_common import color_follow, read_HSV, write_HSV, simplePID

# =========================
# Cấu hình robot
# =========================
ROBOT_BASE_URL = "http://10.122.52.41:9000"
CAMERA_SOURCE = f"{ROBOT_BASE_URL}/camera"
USE_REMOTE_CAMERA = True
CAMERA_INDEX = 0

FRAME_W = 640
FRAME_H = 480


# =========================
# HTTP client điều khiển robot
# =========================
class RobotHTTPClient:
    def __init__(self, base_url: str, timeout: float = 1.5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self._last_cmd = None

    def _send(self, payload: dict, force: bool = False) -> bool:
        cmd = payload.get("command")
        if not force and cmd == self._last_cmd:
            return True

        try:
            resp = self.session.post(
                f"{self.base_url}/control",
                json=payload,
                timeout=self.timeout,
            )
            ok = resp.ok
        except requests.RequestException as e:
            print(f"[RobotHTTP] control error: {e}")
            return False

        if ok:
            self._last_cmd = cmd
        return ok

    def stop(self, force=False):
        return self._send({"command": "stop"}, force=force)

    def forward(self):
        return self._send({"command": "forward"})

    def back(self):
        return self._send({"command": "back"})

    def left(self):
        return self._send({"command": "left"})

    def right(self):
        return self._send({"command": "right"})

    def turnleft(self):
        return self._send({"command": "turnleft"})

    def turnright(self):
        return self._send({"command": "turnright"})

    def pace(self, mode: str):
        return self._send({"command": f"pace_{mode}"}, force=True)

    def init_posture(self):
        return self._send({"command": "init_posture"}, force=True)

    def turn(self, z_pid: int):
        threshold = 15
        if z_pid > threshold:
            return self.turnright()
        elif z_pid < -threshold:
            return self.turnleft()
        return self.forward()

    def reset(self):
        self.stop(force=True)
        self._last_cmd = None


# =========================
# Logic line tracking
# =========================
class WebLineTracker:
    def __init__(self):
        self.color = color_follow()
        self.scale = 1000
        self.FollowLinePID = (10, 0, 20)
        self.PID_init()

        self.hsv_file = os.path.join(os.path.dirname(__file__), "LineFollowHSV.text")
        self.hsv_range = ()
        if os.path.exists(self.hsv_file):
            self.hsv_range = read_HSV(self.hsv_file)

        self.robot = RobotHTTPClient(ROBOT_BASE_URL)
        self.robot.stop(force=True)
        time.sleep(0.02)
        self.robot.pace("slow")
        time.sleep(0.02)
        self.robot.init_posture()

        self.track_enabled = False
        self.identify_mode = True
        self.cmd_interval = 0.6
        self._last_execute_time = 0.0

        self.capture = None
        self.capture_lock = threading.Lock()

        self.frame_raw = None
        self.frame_processed = None
        self.frame_mask = None
        self.last_circle = (0, 0, 0)
        self.last_z_pid = 0
        self.last_fps = 0
        self.status_text = "idle"

        self.running = True
        self.open_capture()

        self.worker = threading.Thread(target=self.update_loop, daemon=True)
        self.worker.start()

    def PID_init(self):
        self.PID_controller = simplePID(
            [0, 0],
            [self.FollowLinePID[0] / self.scale, 0],
            [self.FollowLinePID[1] / self.scale, 0],
            [self.FollowLinePID[2] / self.scale, 0],
        )

    def open_capture(self):
        if self.capture is not None:
            try:
                self.capture.release()
            except Exception:
                pass

        if USE_REMOTE_CAMERA:
            self.capture = cv.VideoCapture(CAMERA_SOURCE)
        else:
            self.capture = cv.VideoCapture(CAMERA_INDEX)
            self.capture.set(cv.CAP_PROP_FRAME_WIDTH, FRAME_W)
            self.capture.set(cv.CAP_PROP_FRAME_HEIGHT, FRAME_H)

        print("Camera opened:", CAMERA_SOURCE if USE_REMOTE_CAMERA else CAMERA_INDEX)

    def reset(self):
        self.PID_init()
        self.track_enabled = False
        self.identify_mode = True
        self.last_circle = (0, 0, 0)
        self.last_z_pid = 0
        self.status_text = "reset"
        self.robot.reset()
        time.sleep(0.02)
        self.robot.pace("slow")
        time.sleep(0.02)
        self.robot.init_posture()

    def set_hsv(self, h_min, s_min, v_min, h_max, s_max, v_max):
        self.hsv_range = (
            (int(h_min), int(s_min), int(v_min)),
            (int(h_max), int(s_max), int(v_max)),
        )
        write_HSV(self.hsv_file, self.hsv_range)

    def process_frame(self, frame):
        frame = cv.convertScaleAbs(frame, alpha=1.4, beta=40)
        frame = cv.resize(frame, (FRAME_W, FRAME_H))

        processed = frame.copy()
        mask_bgr = np.zeros_like(processed)

        if self.identify_mode and os.path.exists(self.hsv_file):
            self.hsv_range = read_HSV(self.hsv_file)

        if len(self.hsv_range) != 0:
            processed, binary, circle = self.color.line_follow(processed, self.hsv_range)
            self.last_circle = circle
            if binary is not None and len(binary) != 0:
                mask_bgr = cv.cvtColor(binary, cv.COLOR_GRAY2BGR)
            else:
                mask_bgr = np.zeros_like(processed)
        else:
            self.last_circle = (0, 0, 0)
            mask_bgr = np.zeros_like(processed)

        cx, cy, cr = self.last_circle
        cv.line(processed, (FRAME_W // 2, 0), (FRAME_W // 2, FRAME_H), (0, 255, 255), 1)
        cv.putText(processed, f"state: {'tracking' if self.track_enabled else 'idle'}",
                   (20, 30), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv.putText(processed, f"circle: x={cx} y={cy} r={cr}",
                   (20, 60), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv.putText(processed, f"z_pid: {int(self.last_z_pid)}",
                   (20, 90), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv.putText(processed, f"fps: {int(self.last_fps)}",
                   (20, 120), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        if self.track_enabled and cr > 0:
            now = time.time()
            if now - self._last_execute_time >= self.cmd_interval:
                self._last_execute_time = now
                z_pid, _ = self.PID_controller.update([(cx - FRAME_W // 2), 0])
                self.last_z_pid = z_pid
                print(f"point_x:{cx} point_y:{cy} radius:{cr} z_pid:{int(z_pid)}")
                self.robot.turn(int(z_pid))

        return frame, processed, mask_bgr

    def update_loop(self):
        fail_count = 0

        while self.running:
            start = time.time()

            with self.capture_lock:
                if self.capture is None or not self.capture.isOpened():
                    self.open_capture()

                ret, frame = self.capture.read()

            if not ret or frame is None:
                fail_count += 1
                self.status_text = f"camera_fail_{fail_count}"
                if fail_count >= 20:
                    print("[INFO] reconnect camera...")
                    self.open_capture()
                    fail_count = 0
                time.sleep(0.05)
                continue

            fail_count = 0

            raw, processed, mask_bgr = self.process_frame(frame)

            self.frame_raw = raw
            self.frame_processed = processed
            self.frame_mask = mask_bgr

            end = time.time()
            self.last_fps = 1.0 / max(end - start, 1e-6)
            self.status_text = "tracking" if self.track_enabled else "ready"

    def encode_frame(self, frame):
        if frame is None:
            empty = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
            cv.putText(empty, "No frame", (220, 240),
                       cv.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            frame = empty

        ok, buffer = cv.imencode(".jpg", frame)
        if not ok:
            return None
        return buffer.tobytes()

    def mjpeg_generator(self, mode="processed"):
        while True:
            if mode == "raw":
                frame = self.frame_raw
            elif mode == "mask":
                frame = self.frame_mask
            else:
                frame = self.frame_processed

            jpg = self.encode_frame(frame)
            if jpg is None:
                time.sleep(0.03)
                continue

            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
            time.sleep(0.03)


# =========================
# Flask app
# =========================
app = Flask(__name__)
tracker = WebLineTracker()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/stream/<mode>")
def stream(mode):
    if mode not in ("raw", "processed", "mask"):
        return "invalid mode", 400
    return Response(
        tracker.mjpeg_generator(mode),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/state", methods=["GET"])
def api_state():
    hsv = tracker.hsv_range if len(tracker.hsv_range) != 0 else ((0, 0, 0), (0, 0, 0))
    return jsonify({
        "track_enabled": tracker.track_enabled,
        "identify_mode": tracker.identify_mode,
        "status": tracker.status_text,
        "fps": tracker.last_fps,
        "circle": {
            "x": tracker.last_circle[0],
            "y": tracker.last_circle[1],
            "r": tracker.last_circle[2],
        },
        "z_pid": tracker.last_z_pid,
        "hsv": {
            "h_min": hsv[0][0],
            "s_min": hsv[0][1],
            "v_min": hsv[0][2],
            "h_max": hsv[1][0],
            "s_max": hsv[1][1],
            "v_max": hsv[1][2],
        }
    })


@app.route("/api/action", methods=["POST"])
def api_action():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "")

    if action == "start":
        tracker.track_enabled = True
        tracker.identify_mode = True
        tracker.robot.pace("slow")
        time.sleep(0.05)
        tracker.robot.forward()
        tracker.status_text = "tracking"

    elif action == "stop":
        tracker.track_enabled = False
        tracker.robot.stop(force=True)
        tracker.status_text = "stopped"

    elif action == "reset":
        tracker.reset()

    elif action == "identify":
        tracker.identify_mode = True
        tracker.status_text = "identify"

    elif action == "forward":
        tracker.robot.forward()

    elif action == "back":
        tracker.robot.back()

    elif action == "left":
        tracker.robot.left()

    elif action == "right":
        tracker.robot.right()

    elif action == "turnleft":
        tracker.robot.turnleft()

    elif action == "turnright":
        tracker.robot.turnright()

    elif action == "pace_slow":
        tracker.robot.pace("slow")

    else:
        return jsonify({"ok": False, "error": "unknown action"}), 400

    return jsonify({"ok": True, "status": tracker.status_text})


@app.route("/api/hsv", methods=["POST"])
def api_hsv():
    data = request.get_json(silent=True) or {}
    try:
        tracker.set_hsv(
            data["h_min"], data["s_min"], data["v_min"],
            data["h_max"], data["s_max"], data["v_max"],
        )
    except KeyError:
        return jsonify({"ok": False, "error": "missing hsv values"}), 400

    return jsonify({"ok": True})


@app.route("/api/config", methods=["POST"])
def api_config():
    data = request.get_json(silent=True) or {}
    robot_base = data.get("robot_base_url")

    global ROBOT_BASE_URL, CAMERA_SOURCE
    if robot_base:
        ROBOT_BASE_URL = robot_base.rstrip("/")
        CAMERA_SOURCE = f"{ROBOT_BASE_URL}/camera"
        tracker.robot = RobotHTTPClient(ROBOT_BASE_URL)
        tracker.open_capture()

    return jsonify({"ok": True, "robot_base_url": ROBOT_BASE_URL})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False, threaded=True)