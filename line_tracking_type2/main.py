import cv2

from image_processing import process_line_frame
from line_points import extract_line_points, draw_line_points
from line_error import compute_line_errors


def main():
    cap = cv2.VideoCapture("http://192.168.1.6:9000/camera")

    if not cap.isOpened():
        print("Khong mo duoc camera")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    cv2.namedWindow("1 - Original", cv2.WINDOW_NORMAL)
    cv2.namedWindow("2 - ROI", cv2.WINDOW_NORMAL)
    cv2.namedWindow("3 - Gray", cv2.WINDOW_NORMAL)
    cv2.namedWindow("4 - Binary", cv2.WINDOW_NORMAL)
    cv2.namedWindow("5 - Morphology", cv2.WINDOW_NORMAL)
    cv2.namedWindow("6 - Step3 Error View", cv2.WINDOW_NORMAL)

    cv2.resizeWindow("1 - Original", 800, 600)
    cv2.resizeWindow("2 - ROI", 800, 600)
    cv2.resizeWindow("3 - Gray", 800, 600)
    cv2.resizeWindow("4 - Binary", 800, 600)
    cv2.resizeWindow("5 - Morphology", 800, 600)
    cv2.resizeWindow("6 - Step3 Error View", 800, 600)

    print("Nhan Q de thoat")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Khong doc duoc frame")
            break

        processed = process_line_frame(frame)

        roi_top = processed["roi_top"]
        roi = processed["roi"]
        gray = processed["gray"]
        binary = processed["binary"]
        morph = processed["morph"]

        points = extract_line_points(morph)

        errors = compute_line_errors(
            x_bottom=points["x_bottom"],
            x_mid=points["x_mid"],
            x_top=points["x_top"],
            image_center_x=points["image_center_x"],
        )

        error_view = draw_line_points(morph, points, errors)

        display = frame.copy()
        h, w = frame.shape[:2]
        cv2.rectangle(display, (0, roi_top), (w, h), (0, 255, 255), 2)
        cv2.putText(display, f"Frame: {w}x{h}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        cv2.imshow("1 - Original", display)
        cv2.imshow("2 - ROI", roi)
        cv2.imshow("3 - Gray", gray)
        cv2.imshow("4 - Binary", binary)
        cv2.imshow("5 - Morphology", morph)
        cv2.imshow("6 - Step3 Error View", error_view)

        print(
            f"x_bottom={points['x_bottom']}, "
            f"x_mid={points['x_mid']}, "
            f"x_top={points['x_top']}, "
            f"e_lat={errors['e_lat']}, "
            f"e_heading={errors['e_heading']}, "
            f"e_mix={errors['e_mix']}, "
            f"status={errors['status']}"
        )

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()