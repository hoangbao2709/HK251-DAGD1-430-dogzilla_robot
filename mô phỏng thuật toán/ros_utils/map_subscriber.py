# ros_utils/map_subscriber.py

import rclpy
import cv2
import math
import numpy as np
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from rclpy.time import Time

from geometry_msgs.msg import Twist
from nav_msgs.msg import OccupancyGrid, Path
from tf2_ros import Buffer, TransformListener, LookupException, ConnectivityException, ExtrapolationException

from .path_tools import build_path_msg, cell_to_world

# --- tham số follower (WAYPOINT) ---

# Ngưỡng coi như đã tới 1 waypoint / goal
GOAL_TOL = 0.15      # m – có thể chỉnh 0.12–0.20 tuỳ map

# Linear speed (gắn với gait Dogzilla, đi vừa nhanh vừa ổn)
V_FAST = 0.6         # m/s khi còn xa waypoint
V_SLOW = 0.35        # m/s khi gần waypoint

# Điều khiển góc
YAW_TOL       = 0.35      # ~20°, lệch hơn sẽ bắt đầu quay
KP_TURN       = 1.5       # gain quay
TURN_W_STRONG = 0.9       # quay tại chỗ (khi lệch lớn)
TURN_W_WEAK   = 0.6       # quay khi đang đi


class MapSubscriber(Node):
    def __init__(self, map_topic='/map', base_frame='base_link', map_frame='map'):
        super().__init__('map_subscriber')

        # dùng sim time (gazebo / bag)
        self.set_parameters([rclpy.parameter.Parameter(
            'use_sim_time', rclpy.parameter.Parameter.Type.BOOL, True
        )])

        # --- /map subscribe (TRANSIENT_LOCAL để bắt map ngay) ---
        qos_map = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL
        )
        self.create_subscription(OccupancyGrid, map_topic, self._on_map, qos_map)

        # --- TF ---
        self.tf_buffer = Buffer(cache_time=rclpy.duration.Duration(seconds=5.0))
        self.tf_listener = TransformListener(self.tf_buffer, self, spin_thread=False)

        # --- publishers/subscribers khác ---
        self.path_pub = self.create_publisher(Path, '/a_star_path', 10)  # để xem path trên RViz
        self.cmd_pub  = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(Path, '/a_star_path', self._on_path, 10)

        # --- trạng thái map/robot/path ---
        self.map_img   = None
        self.map_info  = None
        self.map_frame = map_frame
        self.base_frame = base_frame

        self.robot_cell = None
        self.robot_yaw  = 0.0

        self.path_world = []  # [(x,y)] đường hiện tại để bám
        self.path_idx   = 0   # index waypoint hiện tại

        # timers
        self.create_timer(0.10, self._update_robot_pose)  # 10 Hz
        self.create_timer(0.05, self._control_step)       # 20 Hz

    # ---------- Map ----------
    def _on_map(self, msg: OccupancyGrid):
        self.map_info = msg.info
        h, w = msg.info.height, msg.info.width
        data = np.asarray(msg.data, dtype=np.int16).reshape((h, w))

        img = np.zeros((h, w), np.uint8)
        img[data == -1] = 128     # unknown
        img[data == 0]  = 255     # free
        img[data >= 65] = 0       # occupied
        # lật trục Y để khớp với viewer
        self.map_img = cv2.flip(img, 0)

    # ---------- TF & robot cell ----------
    def _world_to_cell(self, x, y):
        if self.map_info is None:
            return None
        res = self.map_info.resolution
        x0, y0 = self.map_info.origin.position.x, self.map_info.origin.position.y
        w, h = self.map_info.width, self.map_info.height

        cx = int((x - x0) / res)
        cy = int((y - y0) / res)
        if cx < 0 or cy < 0 or cx >= w or cy >= h:
            return None

        r = (h - 1) - cy
        c = cx
        return (r, c)

    def _update_robot_pose(self):
        if self.map_info is None:
            return
        try:
            tf = self.tf_buffer.lookup_transform(
                self.map_frame, self.base_frame, Time(),
                timeout=rclpy.duration.Duration(seconds=0.05)
            )
            x = tf.transform.translation.x
            y = tf.transform.translation.y
            q = tf.transform.rotation
            siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
            cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
            yaw = math.atan2(siny_cosp, cosy_cosp)

            cell = self._world_to_cell(x, y)
            if cell is not None:
                self.robot_cell = cell
                self.robot_yaw  = yaw
        except (LookupException, ConnectivityException, ExtrapolationException):
            pass

    # ---------- Nhận path từ Viewer ----------
    def _on_path(self, msg: Path):
        self.path_world = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]
        self.path_idx = 0
        self.get_logger().info(f"Receive path: {len(self.path_world)} pts")

    # ---------- Follower kiểu waypoint ----------
    def _control_step(self):
        # Không có path -> dừng
        if not self.path_world:
            return

        pose = self._get_pose()
        if pose is None:
            self.cmd_pub.publish(Twist())
            return

        x, y, yaw = pose

        # Hết path -> dừng hẳn
        if self.path_idx >= len(self.path_world):
            self.cmd_pub.publish(Twist())
            self.path_world = []
            return

        # --- waypoint hiện tại ---
        gx, gy = self.path_world[self.path_idx]
        dx = gx - x
        dy = gy - y
        dist = math.hypot(dx, dy)

        # 1) Nếu đã tới waypoint này -> sang điểm tiếp theo
        if dist < GOAL_TOL:
            self.path_idx += 1
            if self.path_idx >= len(self.path_world):
                # tới goal cuối cùng
                self.cmd_pub.publish(Twist())
                self.path_world = []
                return

            # cập nhật lại waypoint mới
            gx, gy = self.path_world[self.path_idx]
            dx = gx - x
            dy = gy - y
            dist = math.hypot(dx, dy)

        # 2) Tính góc lệch tới waypoint
        target_yaw = math.atan2(dy, dx)
        ang_err = (target_yaw - yaw + math.pi) % (2.0 * math.pi) - math.pi
        
        
        BEHIND_ANGLE = math.radians(150)  # gần như quay lưng hẳn mới skip
        CLOSE_DIST   = 0.10               # chỉ skip nếu đã rất gần
        # 2.a. Nếu waypoint đã gần như nằm phía sau robot (> ~90°)
        #      coi như đã đi qua, SKIP sang waypoint tiếp theo
        if dist < CLOSE_DIST and abs(ang_err) > BEHIND_ANGLE:
            self.path_idx += 1
            if self.path_idx >= len(self.path_world):
                self.cmd_pub.publish(Twist())
                self.path_world = []
                return

            gx, gy = self.path_world[self.path_idx]
            dx = gx - x
            dy = gy - y
            dist = math.hypot(dx, dy)
            target_yaw = math.atan2(dy, dx)
            ang_err = (target_yaw - yaw + math.pi) % (2.0 * math.pi) - math.pi

        cmd = Twist()
        abs_err = abs(ang_err)

        # 3) Điều khiển quay / tiến với 3 vùng

        # 3.a. Lệch hướng lớn -> quay tại chỗ cho thẳng
        if abs_err > 1.5 * YAW_TOL:
            cmd.linear.x = 0.0
            w_cmd = KP_TURN * ang_err
            if w_cmd > 0.0:
                w_cmd = min(w_cmd, TURN_W_STRONG)
            else:
                w_cmd = max(w_cmd, -TURN_W_STRONG)
            cmd.angular.z = w_cmd

        else:
            # 3.b. Lệch vừa phải -> vừa đi vừa chỉnh
            if dist > 0.4:
                v = V_FAST
            else:
                v = V_SLOW

            cmd.linear.x = v

            if abs_err > YAW_TOL:
                w_cmd = KP_TURN * ang_err
                if w_cmd > 0.0:
                    w_cmd = min(w_cmd, TURN_W_WEAK)
                else:
                    w_cmd = max(w_cmd, -TURN_W_WEAK)
                cmd.angular.z = w_cmd
            else:
                # 3.c. Hướng đã khá thẳng -> đi gần như thẳng
                cmd.angular.z = 0.0

        self.cmd_pub.publish(cmd)

    def _get_pose(self):
        try:
            tf = self.tf_buffer.lookup_transform(
                self.map_frame, self.base_frame, Time(),
                timeout=rclpy.duration.Duration(seconds=0.05)
            )
            x = tf.transform.translation.x
            y = tf.transform.translation.y
            q = tf.transform.rotation
            siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
            cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
            yaw = math.atan2(siny_cosp, cosy_cosp)
            return x, y, yaw
        except (LookupException, ConnectivityException, ExtrapolationException):
            return None

