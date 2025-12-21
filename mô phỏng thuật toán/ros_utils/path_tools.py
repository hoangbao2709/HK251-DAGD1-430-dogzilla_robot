import math
from nav_msgs.msg import Path
from geometry_msgs.msg import PoseStamped

def yaw_to_quat(yaw):
    qz = math.sin(yaw*0.5)
    qw = math.cos(yaw*0.5)
    return qz, qw

def build_path_msg(node, map_info, cell_path, stride=3):
    if map_info is None or not cell_path: return None
    msg = Path()
    msg.header.stamp = node.get_clock().now().to_msg()
    msg.header.frame_id = 'map'
    pts = cell_path[::max(1, stride)]
    if pts[-1] != cell_path[-1]: pts.append(cell_path[-1])

    for i, rc in enumerate(pts):
        x, y = cell_to_world(map_info, rc)
        if i < len(pts)-1:
            x2, y2 = cell_to_world(map_info, pts[i+1])
            yaw = math.atan2(y2 - y, x2 - x)
        else: yaw = 0.0
        qz, qw = yaw_to_quat(yaw)
        p = PoseStamped()
        p.header = msg.header
        p.pose.position.x = x
        p.pose.position.y = y
        p.pose.orientation.z = qz
        p.pose.orientation.w = qw
        msg.poses.append(p)
    return msg

def cell_to_world(info, rc):
    r, c = rc
    res = info.resolution
    x0, y0 = info.origin.position.x, info.origin.position.y
    h = info.height
    cy = (h - 1) - r
    x = x0 + c * res
    y = y0 + cy * res
    return x, y
