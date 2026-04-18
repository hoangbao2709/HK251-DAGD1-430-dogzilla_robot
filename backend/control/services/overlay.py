import cv2


def draw_overlay(frame, detection_result):
    out = frame.copy()

    if not detection_result.ok:
        return out

    for item in detection_result.items:
        corners = item.corners

        for i in range(4):
            p1 = tuple(corners[i])
            p2 = tuple(corners[(i + 1) % 4])
            cv2.line(out, p1, p2, (0, 255, 0), 2)

        cv2.circle(out, item.center_px, 6, (255, 0, 0), -1)

        x, y = item.center_px
        lines = [
            f"QR: {item.text}",
            f"angle: {item.angle_deg:.1f} deg",
            f"dist : {item.distance_m:.2f} m",
            f"tx/tz: ({item.lateral_x_m:.2f}, {item.forward_z_m:.2f})",
            f"target: ({item.target_x_m:.2f}, {item.target_z_m:.2f})",
        ]

        yy = y - 55
        for line in lines:
            cv2.putText(
                out,
                line,
                (x + 10, yy),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2
            )
            yy += 20

    return out
