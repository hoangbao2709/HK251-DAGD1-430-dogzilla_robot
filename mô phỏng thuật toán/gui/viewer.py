# gui/viewer.py

import math
import cv2
import numpy as np
from time import perf_counter
from PyQt5 import QtCore, QtWidgets, QtGui

# --- planners & path tools ---
from planner.a_star import a_star
from planner.dijkstra import dijkstra
from ros_utils.path_tools import build_path_msg, cell_to_world
from ros_utils.map_subscriber import GOAL_TOL  # dùng cùng ngưỡng goal với follower

PATH_THICK = 1
REPLAN_PERIOD_SEC = 0.30   # tối đa ~3Hz
CELL_MOVE_TRIGGER = 1      # robot đổi >= 1 cell thì replan
PAD_LEFT  = 40             # chỗ trục Y + số
PAD_BOTTOM = 25            # chỗ trục X + số
SAFE_CLEARANCE_M = 0.20 
# ====================== Metrics helpers ======================
def _edge_cost(a, b):
    """Chi phí cạnh theo 8-neighborhood: thẳng=1, chéo=sqrt(2). a,b: (r,c)"""
    dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
    return math.sqrt(2.0) if dr == 1 and dc == 1 else 1.0

def _path_length_cells(path):
    if not path or len(path) < 2:
        return 0.0
    return sum(_edge_cost(path[i - 1], path[i]) for i in range(1, len(path)))

def _angles(path):
    """Hướng của từng đoạn (rad) với quy ước ảnh: y=r, x=c."""
    ang = []
    for i in range(1, len(path)):
        r0, c0 = path[i - 1]; r1, c1 = path[i]
        ang.append(math.atan2(r1 - r0, c1 - c0))
    return ang

def _turn_stats(path, turn_deg_threshold=30.0):
    """(turn_count, smoothness) — smoothness = tổng bình phương delta góc."""
    ang = _angles(path)
    if len(ang) < 2:
        return 0, 0.0
    turns = 0
    smooth = 0.0
    th = math.radians(turn_deg_threshold)
    for i in range(1, len(ang)):
        da = math.atan2(
            math.sin(ang[i] - ang[i - 1]),
            math.cos(ang[i] - ang[i - 1])
        )  # wrap [-pi,pi]
        if abs(da) >= th:
            turns += 1
        smooth += da * da
    return turns, smooth

def _clearance_stats(grid, path, resolution_m=0.05):
    """
    Clearance tới obstacle gần nhất theo L2.
    grid: 0 free, 1 obstacle. Trả về (min_m, mean_m).
    """
    if not path:
        return 0.0, 0.0
    free_u8 = ((grid == 0).astype(np.uint8)) * 255  # distanceTransform: 0=obs, >0=free
    dist = cv2.distanceTransform(free_u8, cv2.DIST_L2, 3)
    H, W = dist.shape[:2]
    vals = []
    for (r, c) in path:
        if 0 <= r < H and 0 <= c < W:
            vals.append(dist[r, c] * resolution_m)
    if not vals:
        return 0.0, 0.0
    return float(min(vals)), float(sum(vals) / len(vals))

def _call_planner(algo_name, grid, start, goal):
    """
    Gọi planner theo tên.
    Trả về: (path, stats_dict, time_ms)
    """
    t0 = perf_counter()
    if algo_name == "a_star":
        out = a_star(grid, start, goal)
    else:
        out = dijkstra(grid, start, goal)
    dt_ms = round((perf_counter() - t0) * 1000.0, 2)

    if isinstance(out, tuple):
        path, stats = out
        stats = stats or {}
    else:
        path, stats = out, {}
    return path or [], stats, dt_ms

def _now_s():
    return QtCore.QTime.currentTime().msecsSinceStartOfDay() / 1000.0

# ====================== View (zoom/pan) ======================
class GraphicsView(QtWidgets.QGraphicsView):
    zoomChanged = QtCore.pyqtSignal(float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setRenderHints(
            QtGui.QPainter.Antialiasing |
            QtGui.QPainter.SmoothPixmapTransform
        )
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self._zoom = 1.0
        self._min_zoom, self._max_zoom = 0.1, 20.0

    def wheelEvent(self, e: QtGui.QWheelEvent):
        factor = 1.0015 ** e.angleDelta().y()
        self.zoomBy(factor, anchor=e.position())
        e.accept()

    def zoomBy(self, factor: float, anchor=None):
        newz = max(self._min_zoom, min(self._max_zoom, self._zoom * factor))
        factor = newz / self._zoom
        if abs(factor - 1.0) < 1e-6:
            return
        if anchor is not None:
            self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.scale(factor, factor)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
        self._zoom = newz
        self.zoomChanged.emit(self._zoom)

    def setZoom(self, z: float):
        z = max(self._min_zoom, min(self._max_zoom, z))
        self.resetTransform()
        self.scale(z, z)
        self._zoom = z
        self.zoomChanged.emit(self._zoom)

    def fitToScene(self, margin=20):
        self.fitInView(
            self.sceneRect().adjusted(-margin, -margin, margin, margin),
            QtCore.Qt.KeepAspectRatio
        )
        self._zoom = self.transform().m11()
        self.zoomChanged.emit(self._zoom)

# ====================== Main viewer ======================
class MapViewer(QtWidgets.QWidget):
    """
    node cần có:
      - map_img: H×W uint8 (0..255)
      - map_info.resolution: mét/cell (float)
      - robot_cell: (r, c)
      - robot_yaw: rad
      - path_pub: publisher nav_msgs/Path
      - _get_pose(): trả về (x,y,yaw) trong frame map
      - _world_to_cell(x,y): convert goal X,Y (m) -> cell
    """
    def __init__(self, node, algorithm='a_star'):
        super().__init__()
        self.node = node
        self.algorithm = algorithm  # 'a_star' | 'dijkstra'

        self.setWindowTitle(f"🗺 Live Map Viewer ({self.algorithm.upper()})")
        self.setMinimumSize(900, 700)

        # --- scene / view ---
        self.scene = QtWidgets.QGraphicsScene(self)
        self.view = GraphicsView(self.scene, self)
        self.view.setBackgroundBrush(QtGui.QColor("#333"))
        self.pix_item = QtWidgets.QGraphicsPixmapItem()
        self.scene.addItem(self.pix_item)

        # --- toolbar (bottom) ---
        self.combo = QtWidgets.QComboBox()
        self.combo.addItems(["A*", "Dijkstra"])
        self.combo.setCurrentIndex(0 if self.algorithm == 'a_star' else 1)
        self.combo.currentIndexChanged.connect(self._on_algo_change)

        # Hiển thị toạ độ robot (map frame, mét)
        self.robot_label = QtWidgets.QLabel("Robot: x=--, y=--")

        # Input X,Y (m) để đi tới
        self.x_edit = QtWidgets.QLineEdit()
        self.y_edit = QtWidgets.QLineEdit()
        for e in (self.x_edit, self.y_edit):
            e.setFixedWidth(80)
        self.x_edit.setPlaceholderText("x [m]")
        self.y_edit.setPlaceholderText("y [m]")

        self.btn_go_xy = QtWidgets.QPushButton("Go to (x,y)")
        self.btn_go_xy.clicked.connect(self._on_go_to_xy)

        self.zoom_label = QtWidgets.QLabel("100%")
        self.view.zoomChanged.connect(
            lambda z: self.zoom_label.setText(f"{int(z * 100)}%")
        )
        btn_in = QtWidgets.QToolButton(text="+")
        btn_in.clicked.connect(lambda: self.view.zoomBy(1.25))
        btn_out = QtWidgets.QToolButton(text="–")
        btn_out.clicked.connect(lambda: self.view.zoomBy(0.8))
        btn_fit = QtWidgets.QToolButton(text="Fit")
        btn_fit.clicked.connect(self._fit)
        btn_1x = QtWidgets.QToolButton(text="1:1")
        btn_1x.clicked.connect(lambda: self.view.setZoom(1.0))

        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("Planner:"))
        bar.addWidget(self.combo)
        bar.addSpacing(15)
        bar.addWidget(self.robot_label)
        bar.addSpacing(15)
        bar.addWidget(QtWidgets.QLabel("Goal X:"))
        bar.addWidget(self.x_edit)
        bar.addWidget(QtWidgets.QLabel("Y:"))
        bar.addWidget(self.y_edit)
        bar.addWidget(self.btn_go_xy)
        bar.addStretch(1)
        bar.addWidget(self.zoom_label)
        bar.addWidget(btn_out)
        bar.addWidget(btn_in)
        bar.addWidget(btn_fit)
        bar.addWidget(btn_1x)

        # --- metrics panel ---
        self.metrics_view = QtWidgets.QTextBrowser()
        self.metrics_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px;"
        )
        self.metrics_view.setMinimumWidth(320)
        self.metrics_view.setText(
            "No data yet — click on the map or enter (x,y) to set a goal."
        )

        # --- layout ---
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.view)
        lay.addLayout(bar)
        lay.addWidget(self.metrics_view)

        # --- state ---
        self.goal_cell = None
        self.path_cells = None
        self._last_start = None
        self._last_plan_time = 0.0
        self.metrics = None  # chỉ cho thuật toán đang chọn

        # eval tổng thời gian đi tới goal
        self.eval_running = False
        self.eval_start_time_s = 0.0
        self.run_total_time = None
        self.run_goal_world = None  # (x,y) m

        # --- mouse goal picking ---
        self.view.viewport().installEventFilter(self)

        # --- timer (update & replan) ---
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)  # 20 Hz

        # --- shortcuts ---
        QtWidgets.QShortcut(
            QtGui.QKeySequence.ZoomIn,
            self,
            activated=lambda: self.view.zoomBy(1.25),
        )
        QtWidgets.QShortcut(
            QtGui.QKeySequence.ZoomOut,
            self,
            activated=lambda: self.view.zoomBy(0.8),
        )
        QtWidgets.QShortcut(
            QtGui.QKeySequence("0"),
            self,
            activated=lambda: self.view.setZoom(1.0),
        )
        QtWidgets.QShortcut(
            QtGui.QKeySequence("F"),
            self,
            activated=self._fit,
        )
        self._render_metrics()

    # ------------- events -------------
    def eventFilter(self, obj, event):
        if (
            obj is self.view.viewport()
            and event.type() == QtCore.QEvent.MouseButtonPress
        ):
            if event.button() == QtCore.Qt.LeftButton:
                self._on_click(event)
                return True
        return super().eventFilter(obj, event)

    def _on_click(self, e: QtGui.QMouseEvent):
        if self.node.map_img is None:
            print("[viewer] Chưa có map")
            return

        pos_scene = self.view.mapToScene(e.pos())
        xs, ys = int(pos_scene.x()), int(pos_scene.y())

        H, W = self.node.map_img.shape[:2]

        # chuyển từ toạ độ trên canvas (có padding) -> toạ độ trong map
        x_map = xs - PAD_LEFT   # map bắt đầu từ cột PAD_LEFT
        y_map = ys              # map bắt đầu từ hàng 0

        if 0 <= x_map < W and 0 <= y_map < H:
            self.goal_cell = (y_map, x_map)
            print(f"[viewer] Goal cell={self.goal_cell} (click at scene=({xs},{ys}))")
            self._start_eval_for_new_goal()
            self._plan(force=True)
        else:
            print("[viewer] click ngoài vùng map, bỏ qua")

    def _on_algo_change(self):
        self.algorithm = 'a_star' if self.combo.currentText() == "A*" else 'dijkstra'
        self.setWindowTitle(f"🗺 Live Map Viewer ({self.algorithm.upper()})")
        if self.goal_cell is not None:
            self._plan(force=True)

    # ------------- goal từ input (x,y) -------------
    def _on_go_to_xy(self):
        if self.node.map_info is None:
            QtWidgets.QMessageBox.warning(
                self, "Map not ready", "No map info yet."
            )
            return
        try:
            x = float(self.x_edit.text())
            y = float(self.y_edit.text())
        except ValueError:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid input",
                "Please enter numeric X and Y (meters).",
            )
            return

        if not hasattr(self.node, "_world_to_cell"):
            QtWidgets.QMessageBox.warning(
                self,
                "Not supported",
                "Node does not provide _world_to_cell(x,y).",
            )
            return

        cell = self.node._world_to_cell(x, y)
        if cell is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Out of map",
                "Target is outside the map bounds.",
            )
            return

        self.goal_cell = cell
        print(
            f"[viewer] Goal from XY=({x:.3f},{y:.3f}) → cell={self.goal_cell}"
        )
        self._start_eval_for_new_goal()
        self._plan(force=True)

    # ------------- eval run tổng thời gian -------------
    def _start_eval_for_new_goal(self):
        """Gọi mỗi khi đặt goal mới (click hoặc nhập X,Y)."""
        if self.node.map_info is not None and self.goal_cell is not None:
            gx, gy = cell_to_world(self.node.map_info, self.goal_cell)
            self.run_goal_world = (gx, gy)
        else:
            self.run_goal_world = None
        self.eval_running = True
        self.run_total_time = None
        self.eval_start_time_s = _now_s()

    def _check_goal_reached(self):
        """Khi robot vào vùng goal (GOAL_TOL), chốt tổng thời gian."""
        if not self.eval_running or self.run_goal_world is None:
            return
        if not hasattr(self.node, "_get_pose"):
            return
        pose = self.node._get_pose()
        if pose is None:
            return
        x, y, _ = pose
        gx, gy = self.run_goal_world
        dist = math.hypot(gx - x, gy - y)

        # hơi nới lỏng chút để dễ hoàn thành:
        run_tol = max(GOAL_TOL, 1.5 * GOAL_TOL)

        if dist <= run_tol:
            self.eval_running = False
            self.run_total_time = round(_now_s() - self.eval_start_time_s, 3)
            print(
                f"[viewer] Run completed: total_time={self.run_total_time}s, dist={dist}"
            )
            self._render_metrics()

    # ------------- loop -------------
    def _tick(self):
        self._maybe_replan()
        self._update_image()
        self._update_robot_label()
        self._check_goal_reached()

    def _maybe_replan(self):
        if (
            self.goal_cell is None
            or self.node.map_img is None
            or self.node.robot_cell is None
        ):
            return
        now = _now_s()
        start = self.node.robot_cell
        moved = self._last_start is None
        if moved:
            self._plan()

    # ------------- plan -------------
    def _plan(self, force=False):
        if (
            self.goal_cell is None
            or self.node.map_img is None
            or self.node.robot_cell is None
        ):
            return
        base = self.node.map_img

    # 1) base_obs: 0 = free, 1 = obstacle (từ map gốc)
        base_obs = np.zeros_like(base, dtype=np.uint8)
        base_obs[base < 100] = 1   # như cũ: <100 xem là tường

    # 2) lấy resolution của map
        res_m = float(getattr(self.node.map_info, "resolution", 0.05) or 0.05)

    # 3) số cell cần inflate theo SAFE_CLEARANCE_M
        if SAFE_CLEARANCE_M > 0.0 and res_m > 0.0:
            inflate_cells = int(math.ceil(SAFE_CLEARANCE_M / res_m))
        else:
            inflate_cells = 0

    # 4) dùng cv2.dilate để "nở" obstacle ra
        if inflate_cells > 0:
            k = 2 * inflate_cells + 1
            kernel = np.ones((k, k), np.uint8)
            inflated_obs = cv2.dilate(base_obs, kernel)
        else:
            inflated_obs = base_obs

    # 5) grid đưa vào planner: 0 free, 1 obstacle (đã inflate)
        grid = inflated_obs
        start = self.node.robot_cell
        goal = self.goal_cell
        res_m = float(getattr(self.node.map_info, "resolution", 0.05) or 0.05)

        algo_name = self.algorithm
        path, extra, t_ms = _call_planner(algo_name, grid, start, goal)

        if path:
            Lc = _path_length_cells(path)
            Lm = Lc * res_m
            turns, smooth = _turn_stats(path)
            cmin, cmean = _clearance_stats(grid, path, res_m)

            expanded = int(extra.get("expanded", 0)) if isinstance(extra, dict) else None
            visited = int(extra.get("visited", 0)) if isinstance(extra, dict) and "visited" in extra else None
            max_open = int(extra.get("max_open", 0)) if isinstance(extra, dict) and "max_open" in extra else None

            mem_kb = None
            if visited is not None:
                # ước lượng rất thô: ~32 bytes / node
                mem_kb = round(visited * 32 / 1024.0, 1)

            self.metrics = {
                "ok": True,
                "algo": algo_name,
                "time_ms": t_ms,
                "len_cells": round(Lc, 3),
                "len_m": round(Lm, 3),
                "waypoints": len(path),
                "turns": turns,
                "smoothness": round(smooth, 4),
                "clear_min_m": round(cmin, 3),
                "clear_mean_m": round(cmean, 3),
                "expanded": expanded,
                "visited": visited,
                "max_open": max_open,
                "mem_kb": mem_kb,
                "path": path,
            }
        else:
            self.metrics = {
                "ok": False,
                "algo": algo_name,
                "time_ms": t_ms,
            }

        print("[planner] result:", self.metrics)
        self._render_metrics()

        # Publish path của thuật toán đang ACTIVE
        if self.metrics.get("ok"):
            self.path_cells = self.metrics["path"]
            msg = build_path_msg(self.node, self.node.map_info, self.path_cells, stride=3)
            if msg:
                self.node.path_pub.publish(msg)
            self._last_start = start
            self._last_plan_time = _now_s()
        else:
            self.path_cells = None

    def _render_metrics(self):
        def fmt_planner(m):
            """Benchmark của planner (chỉ thuật toán, không tính thời gian robot chạy)."""
            if not m or not m.get("ok"):
                t = m.get("time_ms") if m else "–"
                return f"  ❌ no path ({t} ms)"
            body = (
                f"  time: {m['time_ms']} ms\n"
                f"  len : {m['len_cells']} cells  (~{m['len_m']} m)\n"
                f"  pts : {m['waypoints']}  | turns: {m['turns']}  | smooth: {m['smoothness']}\n"
                f"  clr : min {m['clear_min_m']} m  | mean {m['clear_mean_m']} m"
            )
            if m.get("expanded") is not None:
                body += f"\n  expanded: {m['expanded']}"
            if m.get("visited") is not None:
                body += f"  | visited: {m['visited']}"
            if m.get("max_open") is not None:
                body += f"\n  max_open: {m['max_open']}  (~search width)"
            if m.get("mem_kb") is not None:
                body += f"\n  est. memory: {m['mem_kb']} KB"
            return body

        def fmt_run_summary(m, goal_xy, total_time):
            """Run summary: goal + toàn bộ benchmark + total_time."""
            if not m or not m.get("ok") or goal_xy is None or total_time is None:
                return "  (no run data)"
            gx, gy = goal_xy
            body = (
                f"  algo: {'A*' if m.get('algo') == 'a_star' else 'Dijkstra'}\n"
                f"  goal (x,y): ({gx:.3f}, {gy:.3f}) m\n"
                f"  plan time : {m['time_ms']} ms\n"
                f"  total time: {total_time:.3f} s\n"
                f"  len : {m['len_cells']} cells  (~{m['len_m']} m)\n"
                f"  pts : {m['waypoints']}  | turns: {m['turns']}  | smooth: {m['smoothness']}\n"
                f"  clr : min {m['clear_min_m']} m  | mean {m['clear_mean_m']} m"
            )
            if m.get("expanded") is not None:
                body += f"\n  expanded: {m['expanded']}"
            if m.get("visited") is not None:
                body += f"  | visited: {m['visited']}"
            if m.get("max_open") is not None:
                body += f"\n  max_open: {m['max_open']}  (~search width)"
            if m.get("mem_kb") is not None:
                body += f"\n  est. memory: {m['mem_kb']} KB"
            return body

        algo_label = "A*" if self.algorithm == "a_star" else "Dijkstra"

        # Phần benchmark (planner-only)
        text = (
            f"[{algo_label} @ {QtCore.QTime.currentTime().toString('HH:mm:ss.zzz')}] (ACTIVE)\n"
            + (fmt_planner(self.metrics) if self.metrics else "  (no data)")
            + "\n"
        )

        # Phần run summary: đầy đủ benchmark + total_time (khi đã tới goal)
        if self.run_total_time is not None and self.run_goal_world is not None:
            text += (
                "\n[Run summary]\n"
                + fmt_run_summary(self.metrics, self.run_goal_world, self.run_total_time)
                + "\n"
            )

        self.metrics_view.setText(text)
        print("[benchmark] render ok")

    # ------------- draw -------------
    def _update_image(self):
        if self.node.map_img is None:
            return

        base = self.node.map_img  # ảnh map gốc H×W
        H, W = base.shape[:2]

        # ----- padding để vẽ trục & số ở ngoài map -----
        newH = H + PAD_BOTTOM
        newW = W + PAD_LEFT

        # nền tối
        img = np.zeros((newH, newW), np.uint8)
        img[:] = 40

        # đặt map gốc vào canvas mới (lệch sang phải)
        img[0:H, PAD_LEFT:PAD_LEFT + W] = base

        # ================== VẼ TRỤC & TỌA ĐỘ ==================
        if self.node.map_info is not None:
            steps = 4  # số đoạn chia trên mỗi trục (=> 5 tick)

            # ---- trục Y: theo mép trái của map (x = PAD_LEFT) ----
            x_axis_y = PAD_LEFT
            cv2.line(img, (x_axis_y, 0), (x_axis_y, H - 1), 200, 1)

            # ---- trục X: theo đáy map (y = H-1) ----
            y_axis_y = H - 1
            cv2.line(img, (PAD_LEFT, y_axis_y),
                     (PAD_LEFT + W - 1, y_axis_y), 200, 1)

            # ---- tick + label trên trục X (ngoài map, bên dưới) ----
            for i in range(steps + 1):
                c = int(i * (W - 1) / steps)       # cột trong map
                r = H - 1                          # hàng đáy trong map

                x_world, _ = cell_to_world(self.node.map_info, (r, c))

                sx = PAD_LEFT + c                  # x trên canvas
                sy = y_axis_y

                # tick trên trục
                cv2.line(img, (sx, sy), (sx, sy - 5), 200, 1)

                # label x nằm dưới map
                txt = f"{x_world:.1f}"
                tx = max(0, sx - 12)
                ty = H - 1 + 13                    # dưới đáy map
                cv2.putText(
                    img, txt, (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, 200, 1, cv2.LINE_AA
                )

            # ---- tick + label trên trục Y (ngoài map, bên trái) ----
            for i in range(steps + 1):
                r = int(i * (H - 1) / steps)       # hàng trong map
                c = 0                              # cột trái trong map

                _, y_world = cell_to_world(self.node.map_info, (r, c))

                sx = PAD_LEFT                      # x của trục Y
                sy = r                             # y trên canvas

                # tick trên trục
                cv2.line(img, (sx, sy), (sx + 5, sy), 200, 1)

                # label y nằm bên trái map
                txt = f"{y_world:.1f}"
                tx = 3                             # sát mép trái canvas
                ty = max(10, sy + 3)
                cv2.putText(
                    img, txt, (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, 200, 1, cv2.LINE_AA
                )

            # nhãn X,Y
            cv2.putText(
                img, "X",
                (PAD_LEFT + W - 12, H - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, 200, 1, cv2.LINE_AA
            )
            cv2.putText(
                img, "Y",
                (PAD_LEFT + 3, 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, 200, 1, cv2.LINE_AA
            )

        # ================== VẼ PATH / ROBOT / GOAL ==================

        # path (dịch sang phải PAD_LEFT)
        if self.path_cells and len(self.path_cells) > 1:
            pts = np.array(
                [(PAD_LEFT + c, r) for (r, c) in self.path_cells],
                np.int32
            )
            cv2.polylines(
                img, [pts], False, 100,
                thickness=PATH_THICK, lineType=cv2.LINE_AA
            )

        # robot
        if self.node.robot_cell is not None:
            rr, cc = self.node.robot_cell
            yaw = -float(self.node.robot_yaw)
            cx = PAD_LEFT + cc
            cy = rr
            cv2.circle(img, (cx, cy), 4, 0, -1)
            cv2.circle(img, (cx, cy), 3, 180, -1)
            dx = int(12 * math.cos(yaw))
            dy = int(12 * math.sin(yaw))
            cv2.arrowedLine(
                img, (cx, cy), (cx + dx, cy + dy),
                50, 1, tipLength=0.35
            )

        # goal
        if self.goal_cell:
            rg, cg = self.goal_cell
            gx = PAD_LEFT + cg
            gy = rg
            cv2.circle(img, (gx, gy), 3, 230, -1)

        # ================== CHUYỂN THÀNH PIXMAP ==================
        qimg = QtGui.QImage(
            img.data, img.shape[1], img.shape[0],
            img.strides[0], QtGui.QImage.Format_Grayscale8
        )
        pix = QtGui.QPixmap.fromImage(qimg)
        self.pix_item.setPixmap(pix)
        self.scene.setSceneRect(0, 0, pix.width(), pix.height())
        if not hasattr(self, "_fitted_once"):
            self._fitted_once = True
            self._fit()

    def _update_robot_label(self):
        """Hiển thị toạ độ hiện tại của robot theo map frame (m)."""
        x = y = None
        if hasattr(self.node, "_get_pose"):
            pose = self.node._get_pose()
            if pose is not None:
                x, y, _ = pose
        elif (
            getattr(self.node, "robot_cell", None) is not None
            and getattr(self.node, "map_info", None) is not None
        ):
            x, y = cell_to_world(self.node.map_info, self.node.robot_cell)

        if x is not None and y is not None:
            self.robot_label.setText(f"Robot: x={x:.3f}, y={y:.3f}")
        else:
            self.robot_label.setText("Robot: x=--, y=--")

    def _fit(self):
        self.view.fitToScene(margin=20)

