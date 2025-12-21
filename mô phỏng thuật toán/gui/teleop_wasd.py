#!/usr/bin/env python3
import sys
from dataclasses import dataclass

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from PyQt5 import QtCore, QtWidgets, QtGui


# ====================== Cấu hình ======================
CMD_TOPIC = "/cmd_vel"     # đổi nếu robot bạn dùng topic khác
PUBLISH_HZ = 15            # tần số gửi lệnh (Hz)

LIN_VEL = 0.25             # m/s (tốc độ cơ bản)
ANG_VEL = 1.0              # rad/s
FAST_SCALE = 2.0           # giữ Shift để nhân đôi tốc độ


@dataclass
class VelCmd:
    lin_x: float = 0.0
    ang_z: float = 0.0


# ====================== ROS Node ======================
class TeleopNode(Node):
    def __init__(self):
        super().__init__("gui_teleop_wasd")
        self.pub = self.create_publisher(Twist, CMD_TOPIC, 10)
        self.cmd = VelCmd()

        self.timer = self.create_timer(1.0 / PUBLISH_HZ, self._on_timer)
        self.get_logger().info(f"Teleop WASD started, publishing to {CMD_TOPIC}")

    def _on_timer(self):
        msg = Twist()
        msg.linear.x = float(self.cmd.lin_x)
        msg.angular.z = float(self.cmd.ang_z)
        self.pub.publish(msg)


# ====================== Qt Window ======================
class TeleopWindow(QtWidgets.QWidget):
    """
    Điều khiển:
      - W: tiến
      - S: lùi
      - A: quay trái
      - D: quay phải
      - Space: dừng
      - Shift: tăng tốc (nhân FAST_SCALE)
      - Esc / Q: thoát
    """
    def __init__(self, node: TeleopNode):
        super().__init__()
        self.node = node

        # để giữ trạng thái phím đang nhấn
        self.keys_down = set()
        self.fast_mode = False

        self._build_ui()

        # timer để cập nhật velocity từ trạng thái phím
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._update_cmd_from_keys)
        self.timer.start(30)   # ~33Hz đủ mượt

        # Quan trọng: cho phép nhận focus để bắt phím
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def _build_ui(self):
        self.setWindowTitle("🐶 Dogzilla Teleop – WASD")
        self.setMinimumSize(400, 250)

        title = QtWidgets.QLabel("Keyboard Teleop (WASD)")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")

        guide = QtWidgets.QLabel(
            "Controls:\n"
            "  W: Forward   |  S: Backward\n"
            "  A: Turn Left |  D: Turn Right\n"
            "  Shift: Fast mode  |  Space: Stop\n"
            "  Q / Esc: Exit"
        )
        guide.setAlignment(QtCore.Qt.AlignCenter)

        self.speed_label = QtWidgets.QLabel("")
        self.speed_label.setAlignment(QtCore.Qt.AlignCenter)
        self.speed_label.setStyleSheet("font-family: Consolas;")

        # slider chỉnh base speed
        self.speed_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.speed_slider.setRange(5, 100)   # 0.05 -> 1.00 m/s
        self.speed_slider.setValue(int(LIN_VEL * 100))
        self.speed_slider.valueChanged.connect(self._on_speed_change)

        self.base_speed_label = QtWidgets.QLabel("")
        self.base_speed_label.setAlignment(QtCore.Qt.AlignCenter)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(title)
        lay.addSpacing(8)
        lay.addWidget(guide)
        lay.addSpacing(10)
        lay.addWidget(QtWidgets.QLabel("Base linear speed (m/s):"))
        lay.addWidget(self.speed_slider)
        lay.addWidget(self.base_speed_label)
        lay.addSpacing(10)
        lay.addWidget(self.speed_label)
        lay.addStretch(1)

        self._on_speed_change()
        self._update_speed_label()

    # ------------ UI helpers ------------
    def _on_speed_change(self):
        base_lin = self.speed_slider.value() / 100.0
        self.base_lin_vel = base_lin
        self.base_speed_label.setText(f"{base_lin:.2f} m/s (normal) | "
                                      f"{base_lin * FAST_SCALE:.2f} m/s (fast)")
        self._update_speed_label()

    def _update_speed_label(self):
        lin = self.node.cmd.lin_x
        ang = self.node.cmd.ang_z
        mode = "FAST" if self.fast_mode else "NORMAL"
        self.speed_label.setText(
            f"Mode: {mode} | lin_x = {lin:+.2f} m/s   ang_z = {ang:+.2f} rad/s"
        )

    # ------------ Keyboard ------------
    def keyPressEvent(self, event: QtGui.QKeyEvent):
        key = event.key()

        # thoát nhanh
        if key in (QtCore.Qt.Key_Q, QtCore.Qt.Key_Escape):
            self.close()
            return

        # stop
        if key == QtCore.Qt.Key_Space:
            self.keys_down.clear()
            self.node.cmd.lin_x = 0.0
            self.node.cmd.ang_z = 0.0
            self._update_speed_label()
            return

        if key in (QtCore.Qt.Key_Shift, QtCore.Qt.Key_Shift | QtCore.Qt.Key_Shift):
            self.fast_mode = True

        # lưu key đang nhấn
        self.keys_down.add(key)
        self._update_cmd_from_keys()

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        key = event.key()

        if key in (QtCore.Qt.Key_Shift, QtCore.Qt.Key_Shift | QtCore.Qt.Key_Shift):
            self.fast_mode = False

        if key in self.keys_down:
            self.keys_down.discard(key)

        self._update_cmd_from_keys()

    def _update_cmd_from_keys(self):
        # chuyển set phím -> vận tốc
        forward = 0
        turn = 0

        if QtCore.Qt.Key_W in self.keys_down:
            forward += 1
        if QtCore.Qt.Key_S in self.keys_down:
            forward -= 1
        if QtCore.Qt.Key_A in self.keys_down:
            turn += 1     # quay trái (ang_z > 0)
        if QtCore.Qt.Key_D in self.keys_down:
            turn -= 1     # quay phải (ang_z < 0)

        scale = FAST_SCALE if self.fast_mode else 1.0
        lin = forward * self.base_lin_vel * scale
        ang = turn * ANG_VEL * scale

        self.node.cmd.lin_x = lin
        self.node.cmd.ang_z = ang

        self._update_speed_label()

    # Khi đóng cửa sổ thì dừng robot
    def closeEvent(self, event: QtGui.QCloseEvent):
        self.node.cmd.lin_x = 0.0
        self.node.cmd.ang_z = 0.0
        self._update_speed_label()
        super().closeEvent(event)


# ====================== Main ======================
def main():
    rclpy.init()

    app = QtWidgets.QApplication(sys.argv)
    node = TeleopNode()
    win = TeleopWindow(node)
    win.show()
    win.activateWindow()
    win.setFocus()

    # timer để spin ROS2 trong event loop của Qt
    ros_timer = QtCore.QTimer()
    ros_timer.timeout.connect(lambda: rclpy.spin_once(node, timeout_sec=0.0))
    ros_timer.start(10)

    ret = app.exec_()

    node.destroy_node()
    rclpy.shutdown()
    sys.exit(ret)


if __name__ == "__main__":
    main()
