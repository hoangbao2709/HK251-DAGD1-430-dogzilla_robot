from dataclasses import dataclass
from typing import List, Optional


@dataclass
class QRItem:
    text: str
    qr_type: str
    angle_deg: float
    angle_rad: float
    distance_m: float
    lateral_x_m: float
    forward_z_m: float
    direction: str
    center_px: tuple[int, int]
    corners: list[list[int]]


@dataclass
class DetectionResult:
    ok: bool
    items: List[QRItem]