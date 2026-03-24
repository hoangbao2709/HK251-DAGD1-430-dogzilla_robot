from flask import Response, jsonify, request
from stream_utils import mjpeg_generator, get_jpeg


def register_routes(app, tracker, mission_manager=None):
    @app.route("/")
    def index():
        return """
        <html>
        <head>
            <title>Warehouse Line Tracking Monitor</title>
            <style>
                * { box-sizing: border-box; }

                body {
                    margin: 0;
                    font-family: Arial, sans-serif;
                    background: linear-gradient(180deg, #0b1220 0%, #111827 100%);
                    color: white;
                }

                .container {
                    max-width: 1440px;
                    margin: 0 auto;
                    padding: 24px;
                }

                h1 {
                    text-align: center;
                    margin: 0 0 28px 0;
                    font-size: 38px;
                    font-weight: 800;
                }

                .subtitle {
                    text-align: center;
                    color: #cbd5e1;
                    margin-bottom: 28px;
                    font-size: 16px;
                }

                .video-grid {
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 24px;
                }

                .card {
                    background: rgba(17, 24, 39, 0.88);
                    border: 1px solid rgba(148, 163, 184, 0.14);
                    border-radius: 20px;
                    padding: 18px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.28);
                    backdrop-filter: blur(6px);
                }

                .card h3 {
                    margin: 0 0 14px 0;
                    text-align: center;
                    font-size: 22px;
                    font-weight: 700;
                }

                img {
                    width: 100%;
                    border-radius: 16px;
                    border: 2px solid #243045;
                    background: #000;
                }

                .grid-2 {
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 24px;
                    margin-top: 24px;
                }

                .status-card {
                    margin-top: 24px;
                }

                pre {
                    background: #020617;
                    color: #e2e8f0;
                    padding: 18px;
                    border-radius: 14px;
                    font-size: 15px;
                    overflow: auto;
                    border: 1px solid rgba(148, 163, 184, 0.12);
                    min-height: 220px;
                }

                .control-panel {
                    display: flex;
                    justify-content: center;
                    gap: 12px;
                    flex-wrap: wrap;
                }

                .turn-btn,
                .target-btn,
                .action-btn {
                    border: none;
                    border-radius: 14px;
                    padding: 13px 18px;
                    font-size: 16px;
                    font-weight: 700;
                    cursor: pointer;
                    transition: 0.2s ease;
                    color: white;
                    min-width: 132px;
                }

                .turn-btn:hover,
                .target-btn:hover,
                .action-btn:hover {
                    transform: translateY(-2px);
                    opacity: 0.95;
                }

                .turn-btn.left { background: #2563eb; }
                .turn-btn.straight { background: #16a34a; }
                .turn-btn.right { background: #ea580c; }

                .turn-btn.active,
                .target-btn.active {
                    outline: 3px solid white;
                    box-shadow: 0 0 0 4px rgba(255,255,255,0.12);
                }

                .target-grid {
                    display: grid;
                    grid-template-columns: repeat(6, minmax(0, 1fr));
                    gap: 12px;
                }

                .target-btn {
                    background: #7c3aed;
                    min-width: unset;
                    width: 100%;
                    padding: 15px 0;
                    font-size: 20px;
                }

                .target-btn:nth-child(1) { background: #1d4ed8; }
                .target-btn:nth-child(2) { background: #0f766e; }
                .target-btn:nth-child(3) { background: #7c3aed; }
                .target-btn:nth-child(4) { background: #c2410c; }
                .target-btn:nth-child(5) { background: #be123c; }
                .target-btn:nth-child(6) { background: #475569; }

                .action-btn.cancel {
                    background: #dc2626;
                }

                .mission-box {
                    display: grid;
                    grid-template-columns: repeat(4, 1fr);
                    gap: 14px;
                    margin-top: 14px;
                }

                .mission-item {
                    background: #0f172a;
                    border: 1px solid rgba(148, 163, 184, 0.12);
                    border-radius: 16px;
                    padding: 14px;
                }

                .mission-label {
                    font-size: 13px;
                    color: #94a3b8;
                    margin-bottom: 8px;
                    text-transform: uppercase;
                    letter-spacing: 0.04em;
                }

                .mission-value {
                    font-size: 22px;
                    font-weight: 800;
                    word-break: break-word;
                }

                .mission-value.small {
                    font-size: 16px;
                    font-weight: 700;
                }

                .hint {
                    margin-top: 12px;
                    color: #cbd5e1;
                    font-size: 14px;
                    line-height: 1.6;
                }

                @media (max-width: 1100px) {
                    .video-grid,
                    .grid-2 {
                        grid-template-columns: 1fr;
                    }

                    .target-grid {
                        grid-template-columns: repeat(3, minmax(0, 1fr));
                    }

                    .mission-box {
                        grid-template-columns: repeat(2, 1fr);
                    }
                }

                @media (max-width: 700px) {
                    h1 {
                        font-size: 30px;
                    }

                    .target-grid {
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                    }

                    .mission-box {
                        grid-template-columns: 1fr;
                    }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Warehouse Line Tracking Monitor</h1>
                <div class="subtitle">
                    Chọn điểm đến A-F để hệ thống tự chỉ hướng tại các ngã rẽ.
                </div>

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

                <div class="grid-2">
                    <div class="card">
                        <h3>Chọn điểm đến</h3>
                        <div class="target-grid">
                            <button class="target-btn" id="btn-target-A" onclick="setTarget('A')">A</button>
                            <button class="target-btn" id="btn-target-B" onclick="setTarget('B')">B</button>
                            <button class="target-btn" id="btn-target-C" onclick="setTarget('C')">C</button>
                            <button class="target-btn" id="btn-target-D" onclick="setTarget('D')">D</button>
                            <button class="target-btn" id="btn-target-E" onclick="setTarget('E')">E</button>
                            <button class="target-btn" id="btn-target-F" onclick="setTarget('F')">F</button>
                        </div>

                        <div style="margin-top: 16px; display:flex; justify-content:center;">
                            <button class="action-btn cancel" onclick="cancelMission()">Hủy mission</button>
                        </div>

                        <div class="hint">
                            Sau khi chọn đích, web sẽ tự đặt hướng đi tại từng junction.
                            Bạn chỉ cần di chuyển camera theo chấm target và hướng hiển thị trên video xử lý.
                        </div>
                    </div>

                    <div class="card">
                        <h3>Điều khiển tay khi test</h3>
                        <div class="control-panel">
                            <button class="turn-btn left" onclick="setTurnChoice('left')" id="btn-left">⬅ Rẽ trái</button>
                            <button class="turn-btn straight active" onclick="setTurnChoice('straight')" id="btn-straight">⬆ Đi thẳng</button>
                            <button class="turn-btn right" onclick="setTurnChoice('right')" id="btn-right">➡ Rẽ phải</button>
                        </div>

                        <div class="hint">
                            Phần này chỉ để test tay. Khi mission đang chạy, hệ thống có thể tự đổi hướng.
                        </div>
                    </div>
                </div>

                <div class="card status-card">
                    <h3>Trạng thái mission</h3>
                    <div class="mission-box">
                        <div class="mission-item">
                            <div class="mission-label">Điểm đến</div>
                            <div class="mission-value" id="mission-target">-</div>
                        </div>
                        <div class="mission-item">
                            <div class="mission-label">Hướng hiện tại</div>
                            <div class="mission-value" id="mission-turn">straight</div>
                        </div>
                        <div class="mission-item">
                            <div class="mission-label">Junction hiện tại</div>
                            <div class="mission-value" id="mission-junction">-</div>
                        </div>
                        <div class="mission-item">
                            <div class="mission-label">Trạng thái</div>
                            <div class="mission-value small" id="mission-status">idle</div>
                        </div>
                    </div>
                </div>

                <div class="card status-card">
                    <h3>Thông số tracker</h3>
                    <pre id="control-box">Loading...</pre>
                </div>

                <div class="card status-card">
                    <h3>Thông tin mission JSON</h3>
                    <pre id="mission-box">Loading...</pre>
                </div>
            </div>

            <script>
                const TARGETS = ['A', 'B', 'C', 'D', 'E', 'F'];

                async function setTurnChoice(choice) {
                    try {
                        const res = await fetch('/set_turn_choice', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ choice })
                        });

                        const data = await res.json();
                        if (!res.ok) {
                            alert(data.error || 'Không cập nhật được hướng đi');
                            return;
                        }

                        updateActiveTurnButton(data.turn_choice);
                    } catch (e) {
                        alert('Lỗi kết nối tới server');
                    }
                }

                async function setTarget(target) {
                    try {
                        const res = await fetch('/mission/target', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ target })
                        });

                        const data = await res.json();

                        if (!res.ok) {
                            alert(data.error || 'Không đặt được điểm đến');
                            return;
                        }

                        updateActiveTargetButton(target);
                        await updateMission();
                    } catch (e) {
                        alert('Lỗi kết nối tới server');
                    }
                }

                async function cancelMission() {
                    try {
                        const res = await fetch('/mission/cancel', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' }
                        });

                        const data = await res.json();
                        if (!res.ok) {
                            alert(data.error || 'Không hủy được mission');
                            return;
                        }

                        updateActiveTargetButton(null);
                        await updateMission();
                    } catch (e) {
                        alert('Lỗi kết nối tới server');
                    }
                }

                function updateActiveTurnButton(choice) {
                    ['left', 'straight', 'right'].forEach(name => {
                        const el = document.getElementById('btn-' + name);
                        if (el) el.classList.remove('active');
                    });

                    const btn = document.getElementById('btn-' + choice);
                    if (btn) btn.classList.add('active');
                }

                function updateActiveTargetButton(target) {
                    TARGETS.forEach(name => {
                        const el = document.getElementById('btn-target-' + name);
                        if (el) el.classList.remove('active');
                    });

                    if (target) {
                        const btn = document.getElementById('btn-target-' + target);
                        if (btn) btn.classList.add('active');
                    }
                }

                async function updateControl() {
                    try {
                        const res = await fetch('/control');
                        const data = await res.json();

                        document.getElementById('control-box').textContent =
                            JSON.stringify(data, null, 2);

                        if (data.turn_choice) {
                            updateActiveTurnButton(data.turn_choice);
                            document.getElementById('mission-turn').textContent = data.turn_choice;
                        }

                        if (data.junction !== undefined) {
                            document.getElementById('mission-junction').textContent =
                                String(data.junction);
                        }
                    } catch (e) {
                        document.getElementById('control-box').textContent =
                            'Không lấy được dữ liệu /control';
                    }
                }

                async function updateMission() {
                    try {
                        const res = await fetch('/mission');
                        const data = await res.json();

                        document.getElementById('mission-box').textContent =
                            JSON.stringify(data, null, 2);

                        document.getElementById('mission-target').textContent =
                            data.target || '-';

                        document.getElementById('mission-status').textContent =
                            data.status || 'idle';

                        if (data.current_junction) {
                            document.getElementById('mission-junction').textContent =
                                data.current_junction;
                        }

                        if (data.target) {
                            updateActiveTargetButton(data.target);
                        } else {
                            updateActiveTargetButton(null);
                        }

                    } catch (e) {
                        document.getElementById('mission-box').textContent =
                            'Không lấy được dữ liệu /mission';
                    }
                }

                setInterval(updateControl, 200);
                setInterval(updateMission, 300);

                updateControl();
                updateMission();
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
        return jsonify({"ok": True, "turn_choice": tracker.turn_choice})

    @app.route("/mission", methods=["GET"])
    def mission_state():
        if mission_manager is None:
            return jsonify({
                "ok": False,
                "error": "mission_manager is not configured"
            }), 500

        return jsonify(mission_manager.get_state())

    @app.route("/mission/target", methods=["POST"])
    def mission_target():
        if mission_manager is None:
            return jsonify({
                "ok": False,
                "error": "mission_manager is not configured"
            }), 500

        data = request.get_json(silent=True) or {}
        target = data.get("target")

        if target is None:
            return jsonify({
                "ok": False,
                "error": "target is required"
            }), 400

        try:
            state = mission_manager.set_target(target)
            return jsonify({
                "ok": True,
                "message": f"Mission started to {state.get('target')}",
                "mission": state
            })
        except Exception as e:
            return jsonify({
                "ok": False,
                "error": str(e)
            }), 400

    @app.route("/mission/cancel", methods=["POST"])
    def mission_cancel():
        if mission_manager is None:
            return jsonify({
                "ok": False,
                "error": "mission_manager is not configured"
            }), 500

        state = mission_manager.cancel()
        return jsonify({
            "ok": True,
            "message": "Mission cancelled",
            "mission": state
        })

    @app.route("/raw_feed")
    def raw_feed():
        return Response(
            mjpeg_generator(lambda: get_jpeg(tracker.frame)),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )

    @app.route("/processed_feed")
    def processed_feed():
        return Response(
            mjpeg_generator(lambda: get_jpeg(tracker.annotated_frame)),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )