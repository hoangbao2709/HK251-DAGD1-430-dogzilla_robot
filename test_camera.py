import cv2

CAMERA_INDEX = 1

cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

if not cap.isOpened():
    print("Không mở được camera")
    exit()

while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        print("Không đọc được frame")
        break

    cv2.imshow("Test Camera", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == 27:
        break

cap.release()
cv2.destroyAllWindows()