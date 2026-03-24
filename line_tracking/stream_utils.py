import time
import cv2
from config import JPEG_QUALITY


def get_jpeg(image):
    if image is None:
        return None

    ok, buffer = cv2.imencode(
        ".jpg",
        image,
        [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    )

    if not ok:
        return None

    return buffer.tobytes()


def mjpeg_generator(get_image_func):
    while True:
        image = get_image_func()
        if image is None:
            time.sleep(0.05)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + image + b"\r\n"
        )
        time.sleep(0.03)