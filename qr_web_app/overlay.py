import cv2


def draw_overlay(frame, detection_result):
    out = frame.copy()
    h, w = out.shape[:2]
    cx = w // 2

    cv2.line(out, (cx, 0), (cx, h), (0, 255, 255), 2)

    if not detection_result.ok:
        cv2.putText(out, "QR not found", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        return out

    for item in detection_result.items:
        corners = item.corners

        for i in range(4):
            p1 = tuple(corners[i])
            p2 = tuple(corners[(i + 1) % 4])
            cv2.line(out, p1, p2, (0, 255, 0), 2)

        cv2.circle(out, item.center_px, 5, (255, 0, 0), -1)

        lines = [
            f"{item.text}",
            f"{item.angle_deg:.1f} deg",
            f"{item.distance_m:.2f} m",
        ]

        x, y = item.center_px
        yy = y - 35
        for line in lines:
            cv2.putText(out, line, (x + 10, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            yy += 20

    return out