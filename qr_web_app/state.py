import time


latest_state = {
    "ok": False,
    "text": "",
    "angle_deg": 0.0,
    "angle_rad": 0.0,
    "distance_m": 0.0,
    "lateral_x_m": 0.0,
    "forward_z_m": 0.0,
    "target_x_m": 0.0,
    "target_z_m": 0.0,
    "target_distance_m": 0.0,
    "direction": "none",
    "timestamp": time.time(),
    "items": [],
    "position_json": {
        "detected": False,
        "qr": None,
        "position": None,
        "target": None,
        "image": None,
        "timestamp": time.time(),
    },
}
