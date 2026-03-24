import numpy as np

CAMERA_SOURCE = 0
QR_SIZE_M = 0.12
DEADBAND_DEG = 5.0
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 8000
FLIP_FRAME = False

CAMERA_MATRIX = np.array([
    [920.0,   0.0, 640.0],
    [  0.0, 920.0, 360.0],
    [  0.0,   0.0,   1.0],
], dtype=np.float32)

DIST_COEFFS = np.array([0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)