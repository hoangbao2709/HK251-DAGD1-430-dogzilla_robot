from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from django.http import StreamingHttpResponse, HttpResponse
import json
import cv2
import base64
import logging
from .models import Robot
from .serializers import RobotSerializer
from .services.ros import ROSClient
from .line_tracking_backend import LineTrackingServer
from .services.mcp_voice import process_text_command
from .services.qr_detect import detect_qr_state_once, generate_qr_video_frames
logger = logging.getLogger(__name__)
line_tracker = LineTrackingServer()


def build_log(robot_id: str, action: str, payload, ok: bool, error: str | None = None):
    ts = now().strftime("%H:%M:%S")
    try:
        payload_str = json.dumps(payload, ensure_ascii=False)
    except Exception:
        payload_str = str(payload)

    if ok:
        return f"[{ts}] {robot_id} {action} {payload_str} → OK"
    return f"[{ts}] {robot_id} {action} {payload_str} → ERROR: {error}"


class CameraProcessView(APIView):
    """
    Lấy frame từ robot hoặc webcam, xử lý line tracking, trả JSON:
    frame base64 + mask base64 + tracking info
    """

    def get(self, request, robot_id):
        client = ROSClient(robot_id)

        try:
            frame = client.get_frame()
        except Exception:
            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return Response({"ok": False, "error": "No frame"}, status=500)

        frame_out, mask, tracking = line_tracker.process_frame(frame)

        _, fjpg = cv2.imencode(".jpg", frame_out)
        _, mjpg = cv2.imencode(".jpg", mask)

        frame_b64 = base64.b64encode(fjpg.tobytes()).decode("utf-8")
        mask_b64 = base64.b64encode(mjpg.tobytes()).decode("utf-8")

        return Response(
            {
                "ok": True,
                "frame": frame_b64,
                "mask": mask_b64,
                "tracking": tracking,
            }
        )


class RobotListView(APIView):
    def get(self, request):
        data = RobotSerializer(Robot.objects.all(), many=True).data
        return Response(data)


class ConnectView(APIView):
    def post(self, request, robot_id):
        robot = get_object_or_404(Robot, pk=robot_id)
        addr = request.data.get("addr", "")
        client = ROSClient(robot_id)
        result = client.connect(addr)

        robot.addr = addr
        robot.save(update_fields=["addr"])

        return Response({"ok": True, **result}, status=200)


class RobotStatusView(APIView):
    def get(self, request, robot_id):
        robot = get_object_or_404(Robot, pk=robot_id)
        client = ROSClient(robot_id)

        try:
            s = client.get_status() or {}
        except Exception as e:
            print("[RobotStatusView] get_status error:", e)
            s = {}

        changed_fields = []

        battery = s.get("battery")
        if battery is not None and hasattr(robot, "battery"):
            robot.battery = battery
            changed_fields.append("battery")

        fps = s.get("fps")
        if fps is not None and hasattr(robot, "fps"):
            robot.fps = fps
            changed_fields.append("fps")

        robot_connected = s.get("robot_connected")
        if robot_connected is not None and hasattr(robot, "status_text"):
            robot.status_text = "online" if robot_connected else "offline"
            changed_fields.append("status_text")

        if changed_fields:
            robot.save(update_fields=changed_fields)

        data = RobotSerializer(robot).data
        data["telemetry"] = {
            "robot_connected": s.get("robot_connected", False),
            "turn_speed_range": s.get("turn_speed_range"),
            "step_default": s.get("step_default"),
            "z_range": s.get("z_range"),
            "z_current": s.get("z_current"),
            "pitch_range": s.get("pitch_range"),
            "pitch_current": s.get("pitch_current"),
            "battery": s.get("battery"),
            "fw": s.get("fw"),
            "fps": s.get("fps"),
            "system": s.get("system"),
        }

        return Response(data, status=200)


class FPVView(APIView):
    def get(self, request, robot_id):
        client = ROSClient(robot_id)
        return Response({"stream_url": client.get_fpv_url()})


class SpeedModeView(APIView):
    def post(self, request, robot_id):
        mode = request.data.get("mode")
        try:
            ROSClient(robot_id).set_speed_mode(mode)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "SPEED_MODE", {"mode": mode}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)


class MoveCommandView(APIView):
    def post(self, request, robot_id):
        payload = request.data
        try:
            ROSClient(robot_id).move(payload)
            ok = True
            err = None
        except Exception as e:
            ok = False
            err = str(e)

        log_line = build_log(robot_id, "MOVE", payload, ok, err)
        status_code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR

        return Response(
            {
                "ok": ok,
                "log": log_line,
            },
            status=status_code,
        )


class PostureView(APIView):
    def post(self, request, robot_id):
        name = request.data.get("name")
        try:
            ROSClient(robot_id).posture(name)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "POSTURE", {"name": name}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)


class BehaviorView(APIView):
    def post(self, request, robot_id):
        name = request.data.get("name")
        try:
            ROSClient(robot_id).behavior(name)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "BEHAVIOR", {"name": name}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)


class LidarView(APIView):
    def post(self, request, robot_id):
        action = request.data.get("action")
        try:
            ROSClient(robot_id).lidar(action)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "LIDAR", {"action": action}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)


class BodyAdjustView(APIView):
    def post(self, request, robot_id):
        payload = request.data
        try:
            ROSClient(robot_id).body_adjust(payload)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "BODY_ADJUST", payload, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)


class StabilizingModeView(APIView):
    def post(self, request, robot_id):
        action = request.data.get("action")
        try:
            ROSClient(robot_id).stabilizing_mode(action)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "STABILIZING", {"action": action}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)


class TextCommandView(APIView):
    def post(self, request, *args, **kwargs):
        robot_addr = (
            request.data.get("addr")
            or request.data.get("robot_ip")
            or request.data.get("robot_addr")
            or ""
        ).strip()

        text = (request.data.get("text") or "").strip()

        if not robot_addr:
            return Response(
                {
                    "success": False,
                    "error": "robot addr is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not text:
            return Response(
                {
                    "success": False,
                    "error": "text is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            print("[TextCommandView] robot_addr =", robot_addr)
            print("[TextCommandView] text =", text)
            result = process_text_command(robot_addr=robot_addr, text=text)
            log_line = (
                f'TEXT_COMMAND {json.dumps({"addr": robot_addr, "text": text}, ensure_ascii=False)} → OK'
            )

            return Response(
                {
                    "success": True,
                    "robot_addr": robot_addr,
                    "input_text": text,
                    "result": result,
                    "log": log_line,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("TextCommandView error")
            log_line = (
                f'TEXT_COMMAND {json.dumps({"addr": robot_addr, "text": text}, ensure_ascii=False)} '
                f"→ ERROR: {str(e)}"
            )

            return Response(
                {
                    "success": False,
                    "robot_addr": robot_addr,
                    "input_text": text,
                    "error": str(e),
                    "log": log_line,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class QRStateView(APIView):
    def get(self, request, robot_id):
        try:
            data = detect_qr_state_once(robot_id)
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "data": data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("QRStateView error")
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class QRPositionView(APIView):
    def get(self, request, robot_id):
        try:
            data = detect_qr_state_once(robot_id)
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "data": data.get("position_json"),
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("QRPositionView error")
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SlamStateView(APIView):
    def get(self, request, robot_id):
        try:
            data = ROSClient(robot_id).get_slam_state()
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "data": data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class QRVideoFeedView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, robot_id):
        try:
            return StreamingHttpResponse(
                generate_qr_video_frames(robot_id),
                content_type="multipart/x-mixed-replace; boundary=frame",
            )
        except Exception as e:
            logger.exception("QRVideoFeedView error")
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class SlamMapView(APIView):
    """
    Proxy file map.png từ robot về frontend qua Django.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request, robot_id):
        try:
            upstream = ROSClient(robot_id).stream_slam_map_png()
            content_type = upstream.headers.get("Content-Type", "image/png")

            response = HttpResponse(
                upstream.content,
                content_type=content_type,
            )
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            upstream.close()
            return response
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PointsView(APIView):
    def get(self, request, robot_id):
        try:
            data = ROSClient(robot_id).get_points()
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "data": data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request, robot_id):
        body = request.data or {}

        try:
            name = str(body.get("name", "")).strip()
            x = float(body.get("x"))
            y = float(body.get("y"))
            yaw = float(body.get("yaw", 0.0))
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": f"invalid payload: {e}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not name:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": "name is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = ROSClient(robot_id).create_point(
                name=name,
                x=x,
                y=y,
                yaw=yaw,
            )

            log_line = build_log(
                robot_id,
                "CREATE_POINT",
                {"name": name, "x": x, "y": y, "yaw": yaw},
                True,
                None,
            )

            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "result": result,
                    "log": log_line,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            log_line = build_log(
                robot_id,
                "CREATE_POINT",
                {"name": name, "x": x, "y": y, "yaw": yaw},
                False,
                str(e),
            )

            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                    "log": log_line,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeletePointView(APIView):
    def post(self, request, robot_id):
        body = request.data or {}
        name = str(body.get("name", "")).strip()

        if not name:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": "name is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = ROSClient(robot_id).delete_point(name=name)

            log_line = build_log(
                robot_id,
                "DELETE_POINT",
                {"name": name},
                True,
                None,
            )

            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "result": result,
                    "log": log_line,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            log_line = build_log(
                robot_id,
                "DELETE_POINT",
                {"name": name},
                False,
                str(e),
            )

            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                    "log": log_line,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GoToPointView(APIView):
    def post(self, request, robot_id):
        body = request.data or {}
        name = str(body.get("name", "")).strip()

        if not name:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": "name is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = ROSClient(robot_id).go_to_point(name=name)

            log_line = build_log(
                robot_id,
                "GO_TO_POINT",
                {"name": name},
                True,
                None,
            )

            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "result": result,
                    "log": log_line,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            log_line = build_log(
                robot_id,
                "GO_TO_POINT",
                {"name": name},
                False,
                str(e),
            )

            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                    "log": log_line,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GoToMarkerView(APIView):
    def post(self, request, robot_id):
        body = request.data or {}

        try:
            label = str(body.get("label", "")).strip()
            x = float(body.get("x"))
            y = float(body.get("y"))
            yaw = float(body.get("yaw", 0.0))
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": f"invalid payload: {e}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not label:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": "label is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = ROSClient(robot_id).go_to_marker(
                label=label,
                x=x,
                y=y,
                yaw=yaw,
            )

            log_line = build_log(
                robot_id,
                "GO_TO_MARKER",
                {"label": label, "x": x, "y": y, "yaw": yaw},
                True,
                None,
            )

            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "result": result,
                    "log": log_line,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            log_line = build_log(
                robot_id,
                "GO_TO_MARKER",
                {"label": label, "x": x, "y": y, "yaw": yaw},
                False,
                str(e),
            )

            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                    "log": log_line,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )