import cv2
import numpy as np


def find_line_center_on_row(binary_img, y, min_pixels=5):
    row = binary_img[y, :]
    xs = np.where(row > 0)[0]

    if len(xs) < min_pixels:
        return None

    return int(np.mean(xs))


def process_line_frame(frame):
    h, w = frame.shape[:2]

    # ROI rộng hơn để đỡ cảm giác zoom
    roi_top = int(h * 0.35)
    roi = frame[roi_top:h, 0:w]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # line đen trên nền sáng
    _, binary = cv2.threshold(blur, 100, 255, cv2.THRESH_BINARY_INV)

    kernel = np.ones((5, 5), np.uint8)
    morph = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    morph = cv2.morphologyEx(morph, cv2.MORPH_CLOSE, kernel)

    rh, rw = morph.shape[:2]

    # 3 hàng quét
    y_bottom = int(rh * 0.85)
    y_mid = int(rh * 0.55)
    y_top = int(rh * 0.25)

    x_bottom = find_line_center_on_row(morph, y_bottom)
    x_mid = find_line_center_on_row(morph, y_mid)
    x_top = find_line_center_on_row(morph, y_top)

    point_view = cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR)

    # vẽ tâm ảnh
    cv2.line(point_view, (rw // 2, 0), (rw // 2, rh), (255, 0, 0), 2)

    # vẽ các hàng quét
    cv2.line(point_view, (0, y_bottom), (rw, y_bottom), (0, 255, 255), 1)
    cv2.line(point_view, (0, y_mid), (rw, y_mid), (0, 255, 255), 1)
    cv2.line(point_view, (0, y_top), (rw, y_top), (0, 255, 255), 1)

    # vẽ điểm
    pts = []

    if x_bottom is not None:
        cv2.circle(point_view, (x_bottom, y_bottom), 6, (0, 0, 255), -1)
        pts.append((x_bottom, y_bottom))

    if x_mid is not None:
        cv2.circle(point_view, (x_mid, y_mid), 6, (0, 255, 0), -1)
        pts.append((x_mid, y_mid))

    if x_top is not None:
        cv2.circle(point_view, (x_top, y_top), 6, (255, 0, 255), -1)
        pts.append((x_top, y_top))

    for i in range(len(pts) - 1):
        cv2.line(point_view, pts[i], pts[i + 1], (255, 255, 0), 2)

    e_lat = None
    e_heading = None

    if x_bottom is not None:
        e_lat = x_bottom - (rw // 2)

    if x_bottom is not None and x_top is not None:
        e_heading = x_top - x_bottom

    cv2.putText(point_view, f"x_bottom={x_bottom}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(point_view, f"x_mid={x_mid}", (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(point_view, f"x_top={x_top}", (10, 75),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(point_view, f"e_lat={e_lat}", (10, 105),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(point_view, f"e_heading={e_heading}", (10, 130),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    data = {
        "roi_top": roi_top,
        "x_bottom": x_bottom,
        "x_mid": x_mid,
        "x_top": x_top,
        "y_bottom": y_bottom,
        "y_mid": y_mid,
        "y_top": y_top,
        "e_lat": e_lat,
        "e_heading": e_heading,
    }

    return roi, gray, binary, morph, point_view, data


def main():
    cap = cv2.VideoCapture(1)  # không ép CAP_DSHOW để giảm khả năng crop lạ

    if not cap.isOpened():
        print("Khong mo duoc camera")
        return

    # chỉ set nhẹ, không resize lại frame sau khi đọc
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    cv2.namedWindow("1 - Original", cv2.WINDOW_NORMAL)
    cv2.namedWindow("2 - ROI", cv2.WINDOW_NORMAL)
    cv2.namedWindow("3 - Gray", cv2.WINDOW_NORMAL)
    cv2.namedWindow("4 - Binary", cv2.WINDOW_NORMAL)
    cv2.namedWindow("5 - Morphology", cv2.WINDOW_NORMAL)
    cv2.namedWindow("6 - Multi-Point Tracking", cv2.WINDOW_NORMAL)

    cv2.resizeWindow("1 - Original", 800, 600)
    cv2.resizeWindow("2 - ROI", 800, 260)
    cv2.resizeWindow("3 - Gray", 800, 260)
    cv2.resizeWindow("4 - Binary", 800, 260)
    cv2.resizeWindow("5 - Morphology", 800, 260)
    cv2.resizeWindow("6 - Multi-Point Tracking", 800, 260)

    print("Nhan Q de thoat")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Khong doc duoc frame")
            break

        h, w = frame.shape[:2]

        roi, gray, binary, morph, point_view, data = process_line_frame(frame)

        display = frame.copy()
        roi_top = data["roi_top"]

        cv2.rectangle(display, (0, roi_top), (w, h), (0, 255, 255), 2)
        cv2.putText(display, f"Frame: {w}x{h}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        cv2.imshow("1 - Original", display)
        cv2.imshow("2 - ROI", roi)
        cv2.imshow("3 - Gray", gray)
        cv2.imshow("4 - Binary", binary)
        cv2.imshow("5 - Morphology", morph)
        cv2.imshow("6 - Multi-Point Tracking", point_view)

        print(
            f'x_bottom={data["x_bottom"]}, '
            f'x_mid={data["x_mid"]}, '
            f'x_top={data["x_top"]}, '
            f'e_lat={data["e_lat"]}, '
            f'e_heading={data["e_heading"]}'
        )

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()