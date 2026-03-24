from flask import Flask
from tracker import LineTrackingServer
from web_routes import register_routes
from mission_manager import MissionManager

app = Flask(__name__)
tracker = LineTrackingServer()

# Base URL của server robot nhận lệnh
ROBOT_BASE_URL = "http://10.122.52.41:9000"

mission_manager = MissionManager(
    tracker=tracker,
    robot_base_url=ROBOT_BASE_URL,
)
mission_manager.start()

register_routes(app, tracker, mission_manager)

if __name__ == "__main__":
    tracker.start_camera()
    app.run(host="0.0.0.0", port=8888, debug=False, threaded=True, use_reloader=False)