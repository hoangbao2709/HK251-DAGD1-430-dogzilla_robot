import cv2
from pyzbar.pyzbar import decode

def read_qr_from_camera(camera_index=0):
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print("Không mở được camera")
        return

    print("Nhấn Q để thoát")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Không đọc được frame từ camera")
            break

        qr_codes = decode(frame)

        for qr in qr_codes:
            x, y, w, h = qr.rect
            qr_data = qr.data.decode("utf-8")
            qr_type = qr.type

            # Vẽ khung quanh mã QR
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Hiển thị nội dung mã QR
            text = f"{qr_type}: {qr_data}"
            cv2.putText(
                frame,
                text,
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

            print("Đã đọc được:", qr_data)

        cv2.imshow("QR Scanner", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    read_qr_from_camera(0)