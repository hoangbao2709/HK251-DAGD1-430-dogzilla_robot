from flask import Flask
from tracker import LineTrackingServer
from web_routes import register_routes
from mission_manager import MissionManager

app = Flask(__name__)
tracker = LineTrackingServer()

mission_manager = MissionManager(tracker)
mission_manager.start()

register_routes(app, tracker, mission_manager)

if __name__ == "__main__":
    tracker.start_camera()
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True, use_reloader=False)