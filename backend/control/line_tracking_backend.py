import cv2
import numpy as np
import base64

ROI_TOP_RATIO = 0.55
LOWER_BLACK = np.array([0,0,0])
UPPER_BLACK = np.array([180,255,80])
KP = 0.35
KD = 0.08
LINEAR_SPEED = 0.08
MAX_ANGULAR = 0.8
MIN_CONTOUR_AREA = 300

class LineTrackingServer:
    def __init__(self):
        self.prev_error = 0.0

    def process_frame(self, frame):
        h, w = frame.shape[:2]
        roi_start = int(h * ROI_TOP_RATIO)
        roi = frame[roi_start:h, :]

        # Chuyển ROI sang HSV
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, LOWER_BLACK, UPPER_BLACK)

        # Morphology
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT,(5,5))
        mask = cv2.erode(mask, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=2)

        # Tìm contour lớn nhất
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid = [c for c in contours if cv2.contourArea(c) >= MIN_CONTOUR_AREA]

        result = {"found": False, "cx": None, "cy": None}
        mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        if valid:
            largest = max(valid, key=cv2.contourArea)

            # Bounding box
            x,y,w_box,h_box = cv2.boundingRect(largest)
            cv2.rectangle(roi, (x,y), (x+w_box, y+h_box), (0,255,0), 2)

            # Centroid chính xác
            M = cv2.moments(largest)
            cx = int(M['m10']/M['m00'])
            cy = int(M['m01']/M['m00'])

            # PD control
            center_x = w/2
            error = (cx - center_x)/center_x
            d_error = error - self.prev_error
            self.prev_error = error
            angular_z = float(np.clip(-(KP*error + KD*d_error), -MAX_ANGULAR, MAX_ANGULAR))
            linear_x  = LINEAR_SPEED * max(0.4, 1.0 - abs(error)*0.6)

            result.update({
                "found": True,
                "cx": cx,
                "cy": cy,
                "error": float(error),
                "linear_x": float(linear_x),
                "angular_z": float(angular_z)
            })

            # Vẽ overlay giống GUI Raspberry Pi
            cv2.drawContours(roi, [largest], -1, (0,255,0), 2)  # contour
            cv2.circle(roi, (cx, cy), 6, (0,0,255), -1)          # centroid đỏ
            cv2.line(roi, (int(center_x),0), (int(center_x), roi.shape[0]), (255,0,0),1)  # trục giữa

        return frame, mask_bgr, result