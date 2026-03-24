import cv2
import numpy as np
import threading
import time
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# =========================
# CAMERA CONFIG
# =========================
CAMERA_INDEX = 1
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

# =========================
# IMAGE PROCESSING CONFIG
# =========================
ROI_TOP_RATIO = 0.0
THRESHOLD_BINARY = 60

# =========================
# TARGET / SEARCH WINDOW
# =========================
SEARCH_WINDOW_HALF_WIDTH = 80
JUNCTION_WINDOW_HALF_WIDTH = 150

BOTTOM_SCAN_RATIO = 0.78
TOP_SCAN_RATIO = 0.40

MIN_SEGMENT_WIDTH = 8

# =========================
# CONTROL CONFIG
# =========================
KP = 0.35
KD = 0.08
LINEAR_SPEED = 0.08
MAX_ANGULAR = 0.8

# target movement smoothing
SMOOTHING_ALPHA_NORMAL = 0.82      # càng lớn càng chậm
SMOOTHING_ALPHA_JUNCTION = 0.92    # ngã rẽ thì chấm tròn đi chậm hơn nữa

# speed scaling
JUNCTION_SPEED_SCALE = 0.60

# stream quality
JPEG_QUALITY = 75


class LineTrackingServer:
    def __init__(self):
        self.lock = threading.Lock()

        self.cap = None
        self.running = False

        self.frame = None
        self.annotated_frame = None

        # lựa chọn hướng từ web
        self.turn_choice = "straight"  # left | straight | right

        # PID history
        self.prev_error = 0.0

        # target history
        self.prev_target_x = None
        self.prev_target_y = None

        # state
        self.waiting_at_junction = False
        self.junction_hold_frames = 0

        self.result = {
            "found": False,
            "junction": False,
            "waiting_at_junction": False,
            "turn_choice": self.turn_choice,
            "target_x": None,
            "target_y": None,
            "error": 0.0,
            "linear_x": 0.0,
            "angular_z": 0.0,
            "base_center": None,
            "mode": "idle",
        }

    # =========================
    # PUBLIC STATE
    # =========================
    def set_turn_choice(self, choice):
        if choice in ["left", "straight", "right"]:
            with self.lock:
                self.turn_choice = choice

    # =========================
    # CAMERA
    # =========================
    def start_camera(self):
        self.cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

        if not self.cap.isOpened():
            raise RuntimeError(f"Không mở được camera với index {CAMERA_INDEX}")

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        time.sleep(1.0)

        ret, test_frame = self.cap.read()
        if not ret or test_frame is None:
            self.cap.release()
            raise RuntimeError(f"Mở được camera nhưng không đọc được frame với index {CAMERA_INDEX}")

        print("Camera opened successfully")
        print("Test frame shape:", test_frame.shape)

        self.frame = test_frame.copy()
        self.annotated_frame = test_frame.copy()

        self.running = True
        threading.Thread(target=self.update_loop, daemon=True).start()

    # =========================
    # IMAGE HELPERS
    # =========================
    def build_mask(self, roi):
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        # line đen trên nền sáng
        _, mask = cv2.threshold(gray, THRESHOLD_BINARY, 255, cv2.THRESH_BINARY_INV)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    def get_segments_on_row(self, mask, y, min_width=MIN_SEGMENT_WIDTH):
        h, _ = mask.shape[:2]
        y = max(0, min(h - 1, y))

        row = mask[y, :]
        xs = np.where(row > 0)[0]

        if len(xs) == 0:
            return []

        segments = []
        start = xs[0]
        prev = xs[0]

        for x in xs[1:]:
            if x - prev > 1:
                if prev - start + 1 >= min_width:
                    cx = (start + prev) // 2
                    segments.append((int(start), int(prev), int(cx)))
                start = x
            prev = x

        if prev - start + 1 >= min_width:
            cx = (start + prev) // 2
            segments.append((int(start), int(prev), int(cx)))

        return segments

    def filter_segments_in_window(self, segments, x_center, half_width):
        x_min = int(x_center - half_width)
        x_max = int(x_center + half_width)

        filtered = []
        for x1, x2, cx in segments:
            if x_min <= cx <= x_max:
                filtered.append((x1, x2, cx))
        return filtered

    def smooth_target(self, raw_x, raw_y, junction_detected):
        if raw_x is None or raw_y is None:
            self.prev_target_x = None
            self.prev_target_y = None
            return None, None

        alpha = SMOOTHING_ALPHA_JUNCTION if junction_detected else SMOOTHING_ALPHA_NORMAL

        if self.prev_target_x is None:
            smooth_x = raw_x
        else:
            smooth_x = int(alpha * self.prev_target_x + (1.0 - alpha) * raw_x)

        if self.prev_target_y is None:
            smooth_y = raw_y
        else:
            smooth_y = int(alpha * self.prev_target_y + (1.0 - alpha) * raw_y)

        self.prev_target_x = smooth_x
        self.prev_target_y = smooth_y

        return smooth_x, smooth_y

    # =========================
    # TARGET SELECTION
    # =========================
    def choose_target_point(self, mask, turn_choice):
        h, w = mask.shape[:2]
        image_center = w // 2

        y_bottom = int(h * BOTTOM_SCAN_RATIO)
        y_top = int(h * TOP_SCAN_RATIO)

        seg_bottom_all = self.get_segments_on_row(mask, y_bottom)
        seg_top_all = self.get_segments_on_row(mask, y_top)

        if self.prev_target_x is not None:
            base_center = int(self.prev_target_x)
        else:
            base_center = image_center

        seg_bottom = self.filter_segments_in_window(
            seg_bottom_all, base_center, SEARCH_WINDOW_HALF_WIDTH
        )
        if not seg_bottom and seg_bottom_all:
            seg_bottom = seg_bottom_all

        seg_top = self.filter_segments_in_window(
            seg_top_all, base_center, JUNCTION_WINDOW_HALF_WIDTH
        )
        if not seg_top and seg_top_all:
            seg_top = seg_top_all

        bottom_choice = None
        top_choice = None
        junction_detected = False

        if len(seg_bottom) >= 1:
            bottom_choice = min(seg_bottom, key=lambda s: abs(s[2] - base_center))

        if len(seg_top) >= 2:
            junction_detected = True
            seg_top_sorted = sorted(seg_top, key=lambda s: s[2])

            if turn_choice == "left":
                top_choice = seg_top_sorted[0]
            elif turn_choice == "right":
                top_choice = seg_top_sorted[-1]
            else:
                top_choice = min(seg_top_sorted, key=lambda s: abs(s[2] - image_center))
        elif len(seg_top) == 1:
            top_choice = seg_top[0]

        target_x = None
        target_y = None

        if top_choice is not None and bottom_choice is not None:
            if junction_detected and turn_choice in ["left", "right"]:
                alpha = 0.78
            elif junction_detected and turn_choice == "straight":
                alpha = 0.58
            else:
                alpha = 0.45

            target_x = int(alpha * top_choice[2] + (1.0 - alpha) * bottom_choice[2])
            target_y = int(alpha * y_top + (1.0 - alpha) * y_bottom)

        elif bottom_choice is not None:
            target_x = int(bottom_choice[2])
            target_y = int(y_bottom)

        elif top_choice is not None:
            target_x = int(top_choice[2])
            target_y = int(y_top)

        if target_x is not None and not junction_detected:
            x_min = max(0, base_center - SEARCH_WINDOW_HALF_WIDTH)
            x_max = min(w - 1, base_center + SEARCH_WINDOW_HALF_WIDTH)
            target_x = int(np.clip(target_x, x_min, x_max))

        return {
            "target_x": target_x,
            "target_y": target_y,
            "junction": junction_detected,
            "seg_top": seg_top,
            "seg_bottom": seg_bottom,
            "base_center": base_center,
            "y_top": y_top,
            "y_bottom": y_bottom,
            "image_center": image_center,
        }

    # =========================
    # CONTROL
    # =========================
    def compute_control(self, roi_width, target_x, junction_detected):
        center_x = roi_width / 2.0
        error = (target_x - center_x) / center_x
        d_error = error - self.prev_error
        self.prev_error = error

        angular_z = float(np.clip(-(KP * error + KD * d_error), -MAX_ANGULAR, MAX_ANGULAR))

        if junction_detected:
            angular_z = float(np.clip(angular_z * 1.10, -MAX_ANGULAR, MAX_ANGULAR))
            base_speed = LINEAR_SPEED * JUNCTION_SPEED_SCALE
            mode = "junction"
        else:
            base_speed = LINEAR_SPEED
            mode = "follow"

        linear_x = float(base_speed * max(0.40, 1.0 - abs(error) * 0.6))

        return {
            "error": float(error),
            "linear_x": linear_x,
            "angular_z": angular_z,
            "mode": mode,
        }

    # =========================
    # DRAW
    # =========================
    def draw_segments(self, roi, segs, y, color_line, color_dot):
        for x1, x2, cx in segs:
            cv2.line(roi, (x1, y), (x2, y), color_line, 3)
            cv2.circle(roi, (cx, y), 4, color_dot, -1)

    def draw_windows(self, roi, base_center):
        h, w = roi.shape[:2]

        normal_left = max(0, base_center - SEARCH_WINDOW_HALF_WIDTH)
        normal_right = min(w - 1, base_center + SEARCH_WINDOW_HALF_WIDTH)

        junction_left = max(0, base_center - JUNCTION_WINDOW_HALF_WIDTH)
        junction_right = min(w - 1, base_center + JUNCTION_WINDOW_HALF_WIDTH)

        cv2.line(roi, (normal_left, 0), (normal_left, h), (180, 180, 180), 1)
        cv2.line(roi, (normal_right, 0), (normal_right, h), (180, 180, 180), 1)

        cv2.line(roi, (junction_left, 0), (junction_left, h), (80, 200, 255), 1)
        cv2.line(roi, (junction_right, 0), (junction_right, h), (80, 200, 255), 1)

    # =========================
    # MAIN FRAME PROCESS
    # =========================
    def process_frame(self, frame):
        original = frame.copy()
        annotated = frame.copy()

        h, w = annotated.shape[:2]
        roi_start = int(h * ROI_TOP_RATIO)
        roi = annotated[roi_start:h, :]

        mask = self.build_mask(roi)

        choice_info = self.choose_target_point(mask, self.turn_choice)

        raw_target_x = choice_info["target_x"]
        raw_target_y = choice_info["target_y"]
        junction_detected = choice_info["junction"]
        seg_top = choice_info["seg_top"]
        seg_bottom = choice_info["seg_bottom"]
        base_center = choice_info["base_center"]
        y_top = choice_info["y_top"]
        y_bottom = choice_info["y_bottom"]
        image_center = choice_info["image_center"]

        # junction hold: giữ trạng thái ngã rẽ thêm vài frame cho robot rẽ mượt hơn
        if junction_detected:
            self.junction_hold_frames = 10
        else:
            self.junction_hold_frames = max(0, self.junction_hold_frames - 1)

        effective_junction = junction_detected or (self.junction_hold_frames > 0)
        self.waiting_at_junction = effective_junction

        smooth_target_x, smooth_target_y = self.smooth_target(
            raw_target_x, raw_target_y, effective_junction
        )

        result = {
            "found": False,
            "junction": effective_junction,
            "waiting_at_junction": effective_junction,
            "turn_choice": self.turn_choice,
            "target_x": None,
            "target_y": None,
            "error": 0.0,
            "linear_x": 0.0,
            "angular_z": 0.0,
            "base_center": int(base_center),
            "mode": "search",
        }

        # draw helpers
        cv2.rectangle(annotated, (0, roi_start), (w, h), (255, 255, 0), 2)
        cv2.line(annotated, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)

        cv2.line(roi, (0, y_bottom), (roi.shape[1], y_bottom), (255, 0, 255), 1)
        cv2.line(roi, (0, y_top), (roi.shape[1], y_top), (0, 165, 255), 1)
        self.draw_windows(roi, base_center)
        self.draw_segments(roi, seg_bottom, y_bottom, (255, 0, 255), (255, 0, 255))
        self.draw_segments(roi, seg_top, y_top, (0, 165, 255), (0, 165, 255))
        cv2.line(roi, (image_center, 0), (image_center, roi.shape[0]), (255, 0, 0), 2)

        if smooth_target_x is not None and smooth_target_y is not None:
            control = self.compute_control(roi.shape[1], smooth_target_x, effective_junction)

            result = {
                "found": True,
                "junction": effective_junction,
                "waiting_at_junction": effective_junction,
                "turn_choice": self.turn_choice,
                "target_x": int(smooth_target_x),
                "target_y": int(smooth_target_y + roi_start),
                "error": control["error"],
                "linear_x": control["linear_x"],
                "angular_z": control["angular_z"],
                "base_center": int(base_center),
                "mode": control["mode"],
            }

            # target thô
            if raw_target_x is not None and raw_target_y is not None:
                cv2.circle(roi, (raw_target_x, raw_target_y), 5, (0, 0, 255), -1)

            # target smooth
            cv2.circle(roi, (smooth_target_x, smooth_target_y), 10, (255, 255, 255), 2)
            cv2.circle(roi, (smooth_target_x, smooth_target_y), 3, (0, 255, 0), -1)

            cv2.putText(
                annotated,
                f"FOUND | err={control['error']:.3f} lin={control['linear_x']:.3f} ang={control['angular_z']:.3f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2,
            )
            cv2.putText(
                annotated,
                f"target=({smooth_target_x},{smooth_target_y}) junction={effective_junction}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 255),
                2,
            )
        else:
            self.prev_error = 0.0
            cv2.putText(
                annotated,
                "LINE NOT FOUND",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )

        cv2.putText(
            annotated,
            f"TURN: {self.turn_choice.upper()}",
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

        return original, annotated, result

    # =========================
    # UPDATE LOOP
    # =========================
    def update_loop(self):
        fail_count = 0

        while self.running:
            ret, frame = self.cap.read()

            if not ret or frame is None:
                fail_count += 1
                if fail_count % 10 == 1:
                    print(f"[WARN] Không đọc được frame. fail_count={fail_count}")
                time.sleep(0.1)
                continue

            if fail_count > 0:
                print("[INFO] Camera đọc frame lại bình thường")

            fail_count = 0

            raw_frame, annotated, result = self.process_frame(frame)

            with self.lock:
                self.frame = raw_frame
                self.annotated_frame = annotated
                self.result = result

            time.sleep(0.02)

    # =========================
    # MJPEG
    # =========================
    def get_jpeg(self, image):
        if image is None:
            return None

        ok, buffer = cv2.imencode(
            ".jpg",
            image,
            [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        )

        if not ok:
            return None

        return buffer.tobytes()


tracker = LineTrackingServer()


def mjpeg_generator(get_image_func):
    while True:
        image = get_image_func()
        if image is None:
            time.sleep(0.05)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + image + b"\r\n"
        )
        time.sleep(0.03)


@app.route("/")
def index():
    return """
    <html>
    <head>
        <title>Line Tracking Monitor</title>
        <style>
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: #0f0f10;
                color: white;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 24px;
            }
            h1 {
                text-align: center;
                margin-bottom: 28px;
                font-size: 42px;
            }
            .video-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 24px;
            }
            .card {
                background: #1b1b1d;
                border-radius: 18px;
                padding: 18px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.25);
            }
            .card h3 {
                margin: 0 0 14px 0;
                text-align: center;
                font-size: 24px;
            }
            img {
                width: 100%;
                border-radius: 14px;
                border: 2px solid #333;
                background: #000;
            }
            .status-card {
                margin-top: 28px;
            }
            pre {
                background: #000;
                color: #fff;
                padding: 18px;
                border-radius: 12px;
                font-size: 18px;
                overflow: auto;
            }
            .control-panel {
                margin-top: 28px;
                display: flex;
                justify-content: center;
                gap: 16px;
                flex-wrap: wrap;
            }
            .turn-btn {
                border: none;
                border-radius: 14px;
                padding: 14px 22px;
                font-size: 18px;
                font-weight: 700;
                cursor: pointer;
                transition: 0.2s ease;
                color: white;
                min-width: 160px;
            }
            .turn-btn:hover {
                transform: translateY(-2px);
                opacity: 0.92;
            }
            .turn-btn.left { background: #2563eb; }
            .turn-btn.straight { background: #16a34a; }
            .turn-btn.right { background: #ea580c; }
            .turn-btn.active {
                outline: 3px solid white;
                box-shadow: 0 0 0 4px rgba(255,255,255,0.15);
            }
            @media (max-width: 900px) {
                .video-grid {
                    grid-template-columns: 1fr;
                }
                h1 {
                    font-size: 32px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Line Tracking Monitor</h1>

            <div class="video-grid">
                <div class="card">
                    <h3>Camera gốc</h3>
                    <img src="/raw_feed" alt="Raw Camera Feed">
                </div>

                <div class="card">
                    <h3>Camera sau khi xử lý dò line</h3>
                    <img src="/processed_feed" alt="Processed Camera Feed">
                </div>
            </div>

            <div class="card">
                <h3>Chọn hướng khi gặp ngã ba</h3>
                <div class="control-panel">
                    <button class="turn-btn left" onclick="setTurnChoice('left')" id="btn-left">⬅ Rẽ trái</button>
                    <button class="turn-btn straight active" onclick="setTurnChoice('straight')" id="btn-straight">⬆ Đi thẳng</button>
                    <button class="turn-btn right" onclick="setTurnChoice('right')" id="btn-right">➡ Rẽ phải</button>
                </div>
            </div>

            <div class="card status-card">
                <h3>Thông số điều khiển</h3>
                <pre id="control-box">Loading...</pre>
            </div>
        </div>

        <script>
            async function setTurnChoice(choice) {
                try {
                    const res = await fetch('/set_turn_choice', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ choice })
                    });

                    const data = await res.json();

                    if (!res.ok) {
                        alert(data.error || 'Không cập nhật được hướng đi');
                        return;
                    }

                    updateActiveButton(data.turn_choice);
                } catch (e) {
                    alert('Lỗi kết nối tới server');
                }
            }

            function updateActiveButton(choice) {
                document.getElementById('btn-left').classList.remove('active');
                document.getElementById('btn-straight').classList.remove('active');
                document.getElementById('btn-right').classList.remove('active');

                const btn = document.getElementById('btn-' + choice);
                if (btn) btn.classList.add('active');
            }

            async function updateControl() {
                try {
                    const res = await fetch('/control');
                    const data = await res.json();
                    document.getElementById('control-box').textContent =
                        JSON.stringify(data, null, 2);

                    if (data.turn_choice) {
                        updateActiveButton(data.turn_choice);
                    }
                } catch (e) {
                    document.getElementById('control-box').textContent =
                        'Không lấy được dữ liệu /control';
                }
            }

            setInterval(updateControl, 200);
            updateControl();
        </script>
    </body>
    </html>
    """


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/control")
def control():
    with tracker.lock:
        return jsonify(tracker.result)


@app.route("/set_turn_choice", methods=["POST"])
def set_turn_choice():
    data = request.get_json(silent=True) or {}
    choice = data.get("choice")

    if choice not in ["left", "straight", "right"]:
        return jsonify({"ok": False, "error": "choice must be left/straight/right"}), 400

    tracker.set_turn_choice(choice)

    return jsonify({
        "ok": True,
        "turn_choice": tracker.turn_choice
    })


@app.route("/raw_feed")
def raw_feed():
    return Response(
        mjpeg_generator(lambda: tracker.get_jpeg(tracker.frame)),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/processed_feed")
def processed_feed():
    return Response(
        mjpeg_generator(lambda: tracker.get_jpeg(tracker.annotated_frame)),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    tracker.start_camera()
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True, use_reloader=False)