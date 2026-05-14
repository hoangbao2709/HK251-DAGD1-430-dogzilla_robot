from dataclasses import dataclass
from typing import List


@dataclass
class QRItem:
    text: str
    qr_type: str
    angle_deg: float
    angle_rad: float
    distance_m: float
    lateral_x_m: float
    forward_z_m: float
    target_x_m: float
    target_z_m: float
    target_distance_m: float
    direction: str
    center_px: tuple[int, int]
    corners: list[list[int]]
    camera_distance_m: float | None = None
    lidar_distance_m: float | None = None
    map_x_m: float | None = None
    map_y_m: float | None = None
    ray_distance_m: float | None = None
    ray_angle_rad: float | None = None


@dataclass
class DetectionResult:
    ok: bool
    items: List[QRItem]
