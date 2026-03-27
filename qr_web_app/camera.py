import cv2


def create_camera(source):
    cap = cv2.VideoCapture(source)

    # Giảm độ trễ buffer nếu backend/camera hỗ trợ
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    return cap


def read_frame(cap, flip_frame=False):
    ok, frame = cap.read()
    if not ok or frame is None:
        return False, None

    if flip_frame:
        frame = cv2.flip(frame, 1)

    return True, frame