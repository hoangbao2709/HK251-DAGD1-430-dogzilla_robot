#!/usr/bin/env python3
import sys, rclpy, argparse
from ros_utils.map_subscriber import MapSubscriber
from gui.viewer import MapViewer
from PyQt5 import QtWidgets

def ros_spin_in_background(node):
    import threading
    threading.Thread(target=lambda: rclpy.spin(node), daemon=True).start()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--algo', choices=['a_star', 'dijkstra'], default='a_star',
                        help='Chọn thuật toán tìm đường')
    args = parser.parse_args()

    rclpy.init()
    node = MapSubscriber('/map', base_frame='base_link', map_frame='map')
    ros_spin_in_background(node)

    app = QtWidgets.QApplication(sys.argv)
    win = MapViewer(node, algorithm=args.algo)
    win.show()
    print(f"✅ Running with {args.algo.upper()} — click 1 điểm để chọn đích.")
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
