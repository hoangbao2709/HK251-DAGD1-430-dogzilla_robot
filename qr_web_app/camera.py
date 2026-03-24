import cv2


def create_camera(source):
    return cv2.VideoCapture(source)


def read_frame(cap, flip_frame=False):
    ok, frame = cap.read()
    if not ok:
        return False, None

    if flip_frame:
        frame = cv2.flip(frame, 1)

    return True, frame