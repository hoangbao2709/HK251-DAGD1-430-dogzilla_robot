import cv2
import math
import time
import json
import numpy as np
from dataclasses import dataclass, asdict
from typing import Optional, Tuple

from flask import Flask, Response, jsonify, render_template_string


# =====================================
# Data structures
# =====================================

@dataclass
class CameraPose2D:
    x: float
    y: float
    yaw: float


@dataclass
class QRResult:
    ok: bool
    text: str
    angle_deg: float
    angle_rad: float
    distance_m: float
    lateral_x_m: float
    forward_z_m: float
    direction: str
    qr_map_xy: Optional[Tuple[float, float]] = None


# =====================================
# Geometry / QR pose logic
# =====================================

def order_qr_corners(corners: np.ndarray) -> np.ndarray:
    pts = np.array(corners, dtype=np.float32).reshape(4, 2)

    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)

    top_left = pts[np.argmin(s)]
    bottom_right = pts[np.argmax(s)]
    top_right = pts[np.argmin(diff)]
    bottom_left = pts[np.argmax(diff)]

    return np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)


def get_qr_object_points(qr_size_m: float) -> np.ndarray:
    s = qr_size_m / 2.0
    return np.array([
        [-s, -s, 0.0],
        [ s, -s, 0.0],
        [ s,  s, 0.0],
        [-s,  s, 0.0],
    ], dtype=np.float32)


def estimate_qr_pose(corners_2d, camera_matrix, dist_coeffs, qr_size_m):
    obj_points = get_qr_object_points(qr_size_m)
    img_points = order_qr_corners(corners_2d)

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


def compute_topdown_angle_from_tvec(tvec):
    tx = float(tvec[0][0])
    tz = float(tvec[2][0])
    angle_rad = math.atan2(tx, tz)
    return angle_rad, tx, tz


def compute_distance_xz(tx, tz):
    return math.sqrt(tx * tx + tz * tz)


def classify_direction(angle_deg, deadband_deg=5.0):
    if angle_deg > deadband_deg:
        return "right"
    if angle_deg < -deadband_deg:
        return "left"
    return "center"


def detect_and_estimate_qr(frame, camera_matrix, dist_coeffs, qr_size_m, deadband_deg=5.0):
    detector = cv2.QRCodeDetector()
    text, points, _ = detector.detectAndDecode(frame)

    if points is None or len(points) == 0:
        return QRResult(
            ok=False,
            text="",
            angle_deg=0.0,
            angle_rad=0.0,
            distance_m=0.0,
            lateral_x_m=0.0,
            forward_z_m=0.0,
            direction="none",
        ), None, None, None

    corners = np.array(points[0], dtype=np.float32).reshape(4, 2)
    ok, rvec, tvec = estimate_qr_pose(corners, camera_matrix, dist_coeffs, qr_size_m)

    if not ok:
        return QRResult(
            ok=False,
            text=text,
            angle_deg=0.0,
            angle_rad=0.0,
            distance_m=0.0,
            lateral_x_m=0.0,
            forward_z_m=0.0,
            direction="none",
        ), corners, None, None

    angle_rad, tx, tz = compute_topdown_angle_from_tvec(tvec)
    angle_deg = math.degrees(angle_rad)
    distance_m = compute_distance_xz(tx, tz)
    direction = classify_direction(angle_deg, deadband_deg)

    result = QRResult(
        ok=True,
        text=text,
        angle_deg=angle_deg,
        angle_rad=angle_rad,
        distance_m=distance_m,
        lateral_x_m=tx,
        forward_z_m=tz,
        direction=direction,
    )

    return result, corners, rvec, tvec


def draw_overlay(frame, result: QRResult, corners, camera_matrix, dist_coeffs, rvec, tvec):
    out = frame.copy()
    h, w = out.shape[:2]
    cx = w // 2

    cv2.line(out, (cx, 0), (cx, h), (0, 255, 255), 2)

    if corners is not None:
        corners_i = corners.astype(int)
        for i in range(4):
            p1 = tuple(corners_i[i])
            p2 = tuple(corners_i[(i + 1) % 4])
            cv2.line(out, p1, p2, (0, 255, 0), 2)

        center = np.mean(corners_i, axis=0).astype(int)
        cv2.circle(out, tuple(center), 5, (255, 0, 0), -1)

    if rvec is not None and tvec is not None:
        cv2.drawFrameAxes(out, camera_matrix, dist_coeffs, rvec, tvec, 0.05)

    info = [
        f"QR: {result.text}",
        f"angle: {result.angle_deg:.2f} deg",
        f"distance: {result.distance_m:.3f} m",
        f"tx: {result.lateral_x_m:.3f} m",
        f"tz: {result.forward_z_m:.3f} m",
        f"dir: {result.direction}",
    ]

    y = 30
    for line in info:
        cv2.putText(out, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        y += 28

    if not result.ok:
        cv2.putText(out, "QR not found", (20, y + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

    return out


# =====================================
# Flask app
# =====================================

app = Flask(__name__)

latest_state = {
    "ok": False,
    "text": "",
    "angle_deg": 0.0,
    "angle_rad": 0.0,
    "distance_m": 0.0,
    "lateral_x_m": 0.0,
    "forward_z_m": 0.0,
    "direction": "none",
    "timestamp": time.time(),
}

# ======= thay bằng calib thật của bạn =======
camera_matrix = np.array([
    [920.0,   0.0, 640.0],
    [  0.0, 920.0, 360.0],
    [  0.0,   0.0,   1.0],
], dtype=np.float32)

dist_coeffs = np.array([0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
qr_size_m = 0.12

# camera sau: đổi index hoặc URL IP cam
cap = cv2.VideoCapture(0)


HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>QR Angle 2D Viewer</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #0b1220;
      color: #e5edf7;
    }

    .wrap {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 16px;
      padding: 16px;
      min-height: 100vh;
    }

    .panel {
      background: #111a2b;
      border: 1px solid #22314d;
      border-radius: 18px;
      padding: 14px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.25);
    }

    .title {
      font-size: 20px;
      font-weight: 700;
      margin-bottom: 12px;
      color: #ffd54a;
    }

    .video-box {
      overflow: hidden;
      border-radius: 14px;
      border: 1px solid #2d4268;
      background: #000;
    }

    .video-box img {
      display: block;
      width: 100%;
      height: auto;
    }

    .stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 14px;
    }

    .card {
      background: #0d1524;
      border: 1px solid #22314d;
      border-radius: 14px;
      padding: 12px;
    }

    .label {
      font-size: 12px;
      color: #8ea3c5;
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .value {
      font-size: 24px;
      font-weight: 700;
      color: #ffffff;
    }

    .sub {
      font-size: 13px;
      color: #a8bbd8;
      margin-top: 4px;
    }

    .canvas-wrap {
      background: linear-gradient(180deg, #0b1322 0%, #0a1020 100%);
      border: 1px solid #22314d;
      border-radius: 14px;
      padding: 8px;
    }

    #topdownCanvas {
      width: 100%;
      height: auto;
      display: block;
      border-radius: 10px;
      background: #0a0f1a;
    }

    .status-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }

    .badge {
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 700;
      border: 1px solid #294066;
      background: #101a2d;
    }

    .ok { color: #65f28d; }
    .left { color: #66b8ff; }
    .right { color: #ff9f66; }
    .center { color: #ffe066; }
    .none { color: #d0d8e4; }

    @media (max-width: 980px) {
      .wrap {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <div class="title">Camera Feed</div>
      <div class="video-box">
        <img src="/video_feed" alt="video feed" />
      </div>

      <div class="stats">
        <div class="card">
          <div class="label">Angle</div>
          <div class="value" id="angleDeg">0.00°</div>
          <div class="sub">Góc từ trục tâm camera đến QR</div>
        </div>

        <div class="card">
          <div class="label">Distance</div>
          <div class="value" id="distanceM">0.000 m</div>
          <div class="sub">Khoảng cách trên mặt phẳng x-z</div>
        </div>

        <div class="card">
          <div class="label">Lateral X</div>
          <div class="value" id="txVal">0.000</div>
          <div class="sub">Lệch ngang, phải là dương</div>
        </div>

        <div class="card">
          <div class="label">Forward Z</div>
          <div class="value" id="tzVal">0.000</div>
          <div class="sub">Khoảng trước camera</div>
        </div>
      </div>

      <div class="status-row">
        <div class="badge" id="qrOk">NO QR</div>
        <div class="badge" id="direction">none</div>
        <div class="badge" id="qrText">text: -</div>
      </div>
    </div>

    <div class="panel">
      <div class="title">Top-Down 2D Plane</div>
      <div class="canvas-wrap">
        <canvas id="topdownCanvas" width="700" height="700"></canvas>
      </div>
    </div>
  </div>

  <script>
    const canvas = document.getElementById("topdownCanvas");
    const ctx = canvas.getContext("2d");

    const angleDegEl = document.getElementById("angleDeg");
    const distanceMEl = document.getElementById("distanceM");
    const txValEl = document.getElementById("txVal");
    const tzValEl = document.getElementById("tzVal");
    const qrOkEl = document.getElementById("qrOk");
    const directionEl = document.getElementById("direction");
    const qrTextEl = document.getElementById("qrText");

    let state = {
      ok: false,
      text: "",
      angle_deg: 0,
      distance_m: 0,
      lateral_x_m: 0,
      forward_z_m: 0,
      direction: "none"
    };

    function drawGrid() {
      const w = canvas.width;
      const h = canvas.height;

      ctx.clearRect(0, 0, w, h);

      ctx.fillStyle = "#0a0f1a";
      ctx.fillRect(0, 0, w, h);

      ctx.strokeStyle = "rgba(80,120,180,0.18)";
      ctx.lineWidth = 1;

      const step = 50;
      for (let x = 0; x <= w; x += step) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }

      for (let y = 0; y <= h; y += step) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
    }

    function drawTopDown(data) {
      drawGrid();

      const w = canvas.width;
      const h = canvas.height;

      const camX = w / 2;
      const camY = h - 90;

      // scale: 1m = 220px
      const scale = 220;

      // forward axis
      ctx.strokeStyle = "#ffd54a";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(camX, camY);
      ctx.lineTo(camX, 80);
      ctx.stroke();

      // direction arrow
      ctx.fillStyle = "#ffd54a";
      ctx.beginPath();
      ctx.moveTo(camX, 55);
      ctx.lineTo(camX - 10, 80);
      ctx.lineTo(camX + 10, 80);
      ctx.closePath();
      ctx.fill();

      // robot/camera body
      ctx.fillStyle = "#3ec5ff";
      ctx.beginPath();
      ctx.arc(camX, camY, 22, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#08111d";
      ctx.beginPath();
      ctx.arc(camX, camY, 9, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#d6f5ff";
      ctx.font = "bold 16px Arial";
      ctx.fillText("CAM", camX - 18, camY + 45);

      // no qr
      if (!data.ok) {
        ctx.fillStyle = "#ff6b6b";
        ctx.font = "bold 26px Arial";
        ctx.fillText("QR NOT FOUND", w / 2 - 95, 60);
        return;
      }

      const tx = data.lateral_x_m;
      const tz = data.forward_z_m;

      // top-down:
      // +x => right
      // +z => forward (up on canvas)
      const qrX = camX + tx * scale;
      const qrY = camY - tz * scale;

      // line camera -> qr
      ctx.strokeStyle = "#66ff9a";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(camX, camY);
      ctx.lineTo(qrX, qrY);
      ctx.stroke();

      // angle arc
      const angleRad = data.angle_rad;
      const arcRadius = 70;

      ctx.strokeStyle = "#ff9f66";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.arc(camX, camY, arcRadius, -Math.PI / 2, -Math.PI / 2 + angleRad, angleRad < 0);
      ctx.stroke();

      // qr point
      ctx.fillStyle = "#ff4d6d";
      ctx.beginPath();
      ctx.arc(qrX, qrY, 14, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 16px Arial";
      ctx.fillText("QR", qrX + 16, qrY - 10);

      // tx guide
      ctx.strokeStyle = "rgba(102,184,255,0.9)";
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 8]);
      ctx.beginPath();
      ctx.moveTo(camX, qrY);
      ctx.lineTo(qrX, qrY);
      ctx.stroke();

      // tz guide
      ctx.strokeStyle = "rgba(255,224,102,0.9)";
      ctx.beginPath();
      ctx.moveTo(camX, camY);
      ctx.lineTo(camX, qrY);
      ctx.stroke();
      ctx.setLineDash([]);

      // labels
      ctx.fillStyle = "#cfe0ff";
      ctx.font = "15px Arial";
      ctx.fillText(`angle = ${data.angle_deg.toFixed(2)}°`, 24, 34);
      ctx.fillText(`distance = ${data.distance_m.toFixed(3)} m`, 24, 60);
      ctx.fillText(`tx = ${data.lateral_x_m.toFixed(3)} m`, 24, 86);
      ctx.fillText(`tz = ${data.forward_z_m.toFixed(3)} m`, 24, 112);
      ctx.fillText(`dir = ${data.direction}`, 24, 138);
    }

    function updateInfo(data) {
      angleDegEl.textContent = `${data.angle_deg.toFixed(2)}°`;
      distanceMEl.textContent = `${data.distance_m.toFixed(3)} m`;
      txValEl.textContent = data.lateral_x_m.toFixed(3);
      tzValEl.textContent = data.forward_z_m.toFixed(3);

      qrOkEl.textContent = data.ok ? "QR FOUND" : "NO QR";
      qrOkEl.className = `badge ${data.ok ? "ok" : "none"}`;

      directionEl.textContent = data.direction;
      directionEl.className = `badge ${data.direction}`;

      qrTextEl.textContent = `text: ${data.text || "-"}`;
    }

    async function fetchState() {
      try {
        const res = await fetch("/qr_state");
        const data = await res.json();
        state = data;
        updateInfo(data);
        drawTopDown(data);
      } catch (err) {
        console.error(err);
      }
    }

    drawTopDown(state);
    fetchState();
    setInterval(fetchState, 120);
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/qr_state")
def qr_state():
    return jsonify(latest_state)


def generate_frames():
    global latest_state

    if not cap.isOpened():
        raise RuntimeError("Cannot open camera")

    while True:
        success, frame = cap.read()
        if not success:
            continue

        # nếu camera sau bị mirror thì mở dòng dưới:
        # frame = cv2.flip(frame, 1)

        result, corners, rvec, tvec = detect_and_estimate_qr(
            frame=frame,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
            qr_size_m=qr_size_m,
            deadband_deg=5.0
        )

        latest_state = {
            "ok": result.ok,
            "text": result.text,
            "angle_deg": result.angle_deg,
            "angle_rad": result.angle_rad,
            "distance_m": result.distance_m,
            "lateral_x_m": result.lateral_x_m,
            "forward_z_m": result.forward_z_m,
            "direction": result.direction,
            "timestamp": time.time(),
        }

        vis = draw_overlay(frame, result, corners, camera_matrix, dist_coeffs, rvec, tvec)

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
    print("Open: http://127.0.0.1:8000")
    app.run(host="0.0.0.0", port=8000, threaded=True)