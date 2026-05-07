import math
import asyncio
from typing import Any, ClassVar

from django.conf import settings  # type: ignore[import-untyped]
from rest_framework.views import APIView  # type: ignore[import-untyped]
from rest_framework.response import Response  # type: ignore[import-untyped]
from rest_framework import status  # type: ignore[import-untyped]
from django.utils.timezone import now, localtime  # type: ignore[import-untyped]
from django.http import StreamingHttpResponse, HttpResponse  # type: ignore[import-untyped]
import json
import cv2
import base64
import logging
from .models import Robot, ActionEvent, MetricSystem
from .serializers import RobotSerializer
from .services.ros import ROSClient
from .line_tracking_backend import LineTrackingServer
from .services.mcp_voice import AmbiguousCommandError, map_text_to_tool, process_text_command
from .services.qr_detect import detect_qr_state_once, generate_qr_video_frames, get_current_qr_state, save_qr_metric_event
from .services.patrol_manager import patrol_manager
from .services.patrol_store import get_current_mission, get_history
from .services.xiaozhi_bridge import build_bridge_response_text
from .services.llm_voice import map_text_with_openrouter
from .services.tts_voice import DEFAULT_VOICE, VOICE_GENDER, synthesize_vietnamese_speech
logger = logging.getLogger(__name__)
line_tracker = LineTrackingServer()


def get_or_create_robot(robot_id: str) -> Robot:
    robot, _ = Robot.objects.get_or_create(
        pk=robot_id,
        defaults={
            "name": robot_id.replace("-", " ").title(),
        },
    )
    return robot


def build_log(
    robot_id: str,
    action: str,
    payload: Any,
    ok: bool,
    error: str | None = None,
) -> str:
    ts = now().strftime("%H:%M:%S")
    try:
        payload_str = json.dumps(payload, ensure_ascii=False)
    except Exception:
        payload_str = str(payload)

    if ok:
        return f"[{ts}] {robot_id} {action} {payload_str} → OK"
    return f"[{ts}] {robot_id} {action} {payload_str} → ERROR: {error}"

def _extract_bearer_token(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def _get_xiaozhi_bridge_token(request) -> str:
    return (
        _extract_bearer_token(request.headers.get("Authorization", ""))
        or _extract_bearer_token(request.headers.get("X-Xiaozhi-Token", ""))
        or str(request.data.get("token") or "").strip()
    )


def _build_xiaozhi_bridge_result(
    *,
    robot_id: str,
    robot_addr: str,
    text: str,
    dry_run: bool,
) -> dict[str, Any]:
    robot = get_or_create_robot(robot_id)
    if robot.addr != robot_addr:
        robot.addr = robot_addr
        robot.save(update_fields=["addr"])

    tool_name, arguments, mapping = map_text_to_tool(text)

    if dry_run:
        result = {
            "ok": True,
            "robot_addr": robot_addr,
            "tool": tool_name,
            "arguments": arguments,
            "mapping": mapping,
            "content": {
                "success": True,
                "message": "Mapped command only",
            },
        }
    elif tool_name in {"go_to_point", "goto_waypoints"}:
        result = _build_voice_navigation_result(
            robot_id=robot_id,
            robot_addr=robot_addr,
            tool_name=tool_name,
            arguments=arguments,
            mapping=mapping,
        )
    else:
        result = process_text_command(robot_addr=robot_addr, text=text)

    result["bridge_reply_text"] = build_bridge_response_text(result)
    return result


def _resolve_robot_addr_for_bridge(request, robot_id: str) -> str:
    direct_addr = str(
        request.data.get("robot_addr")
        or request.data.get("addr")
        or request.data.get("robot_ip")
        or ""
    ).strip()
    if direct_addr:
        return direct_addr

    robot = get_or_create_robot(robot_id)
    stored_addr = str(robot.addr or "").strip()
    if stored_addr:
        return stored_addr

    return str(settings.XIAOZHI_DEFAULT_ROBOT_ADDR or "").strip()


def _build_voice_navigation_result(
    *,
    robot_id: str,
    robot_addr: str,
    tool_name: str,
    arguments: dict[str, Any],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    if tool_name == "go_to_point":
        points = [str(arguments.get("name") or "").strip().upper()]
        route_name = f"voice_point_{points[0]}" if points and points[0] else "voice_point"
    else:
        points = [str(point).strip().upper() for point in (arguments.get("points") or []) if str(point).strip()]
        route_name = "voice_route"

    if not points:
        raise ValueError("No valid patrol points derived from voice command")

    mission = patrol_manager.start(
        robot_id=robot_id,
        route_name=route_name,
        points=points,
        wait_sec_per_point=0 if len(points) == 1 else 3,
    )
    return {
        "ok": True,
        "robot_addr": robot_addr,
        "tool": tool_name,
        "arguments": arguments,
        "mapping": mapping,
        "content": {
            "success": True,
            "message": "Started patrol mission",
            "mission": mission_to_dict(mission),
        },
    }


def mission_to_dict(mission: Any) -> dict[str, Any]:
    _STATUS_MAP = {
        "DONE":    "completed",
        "FAILED":  "failed",
        "STOPPED": "stopped",
        "RUNNING": "running",
        "PAUSED":  "paused",
    }
    normalized_status = _STATUS_MAP.get(
        str(mission.status or "").upper(),
        str(mission.status or "").lower(),
    )
    return {
        "mission_id": mission.mission_id,
        "robot_id": mission.robot_id,
        "route_name": mission.route_name,
        "points": mission.points,
        "wait_sec_per_point": mission.wait_sec_per_point,
        "max_retry_per_point": mission.max_retry_per_point,
        "skip_on_fail": mission.skip_on_fail,
        "status": normalized_status,       # ← "DONE" → "completed"
        "current_index": mission.current_index,
        "started_at": mission.started_at,
        "finished_at": mission.finished_at,
        "total_distance_m": getattr(mission, "total_distance_m", None),
        "cpu_samples": getattr(mission, "cpu_samples", []),
        "battery_samples": getattr(mission, "battery_samples", []),
        "temperature_samples": getattr(mission, "temperature_samples", []),
        "ram_samples": getattr(mission, "ram_samples", []),
        "results": [
            {
                "point": r.point,
                "status": r.status,
                "attempts": r.attempts,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "reach_time_sec": r.reach_time_sec,
                "distance_on_finish": r.distance_on_finish,
                "message": r.message,
            }
            for r in mission.results
        ],
    }

class QRMetricView(APIView):
    def get(self, request, robot_id):
        try:
            robot = get_or_create_robot(robot_id)
            today = now().date()

            attempts = ActionEvent.objects.filter(
                robot=robot,
                event="qr_scan_metric",
                status="Attempt",
                timestamp__date=today,
            ).count()

            successes = ActionEvent.objects.filter(
                robot=robot,
                event="qr_scan_metric",
                status="Success",
                timestamp__date=today,
            ).count()

            success_rate = round((successes / attempts * 100), 1) if attempts > 0 else 0.0

            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "qr_scan": {
                        "attempts": attempts,
                        "successes": successes,
                        "success_rate_pct": success_rate,
                        "total_today": attempts,
                    },
                    "timestamp": now().isoformat(),
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("QRMetricView error")
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request, robot_id):
        """Frontend gọi để log Attempt/Success"""
        body = request.data or {}
        success = bool(body.get("success", False))
        name = str(body.get("name", "UNKNOWN"))
        reason = str(body.get("reason", ""))

        save_qr_metric_event(
            robot_id,
            "Attempt",
            detail=f"Save Point '{name}' | {reason}",
            payload={"point_name": name, "success": success, "reason": reason},
        )
        if success:
            save_qr_metric_event(
                robot_id,
                "Success",
                detail=f"Lưu thành công Point '{name}'",
                payload={"point_name": name},
            )
        return Response({"ok": True}, status=200)


class VoiceTTSView(APIView):
    authentication_classes: ClassVar[list[type[Any]]] = []
    permission_classes: ClassVar[list[type[Any]]] = []

    def post(self, request):
        text = str(request.data.get("text") or "").strip()
        if not text:
            return Response(
                {"success": False, "error": "text is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        text = text[:600]
        try:
            audio = asyncio.run(synthesize_vietnamese_speech(text))
            response = HttpResponse(audio, content_type="audio/mpeg")
            response["Cache-Control"] = "no-store"
            response["X-TTS-Voice"] = DEFAULT_VOICE
            response["X-TTS-Gender"] = VOICE_GENDER
            return response
        except Exception as e:
            logger.exception("VoiceTTSView error")
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

class CameraProcessView(APIView):
    def get(self, request, robot_id):
        client = ROSClient(robot_id)

        try:
            frame = client.get_frame()
            if frame is None:
                return Response({"ok": False, "error": "Robot camera frame unavailable"}, status=502)
        except Exception as e:
            return Response({"ok": False, "error": str(e)}, status=502)

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


class ActionEventListView(APIView):
    def get(self, request, robot_id):
        limit = request.query_params.get("limit", 20)
        offset = request.query_params.get("offset", 0)

        try:
            limit = max(1, min(int(limit), 50))
        except Exception:
            limit = 20

        try:
            offset = max(0, int(offset))
        except Exception:
            offset = 0

        robot = get_or_create_robot(robot_id)
        qs = (
            ActionEvent.objects.filter(robot=robot)
            .order_by("-timestamp", "-id")[offset : offset + limit]
        )

        items = [
            {
                "id": event.id,
                "timestamp": localtime(event.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                "robot": event.robot_id,
                "event": event.event,
                "severity": event.severity,
                "duration": f"{event.duration_seconds:.1f}s"
                if event.duration_seconds is not None
                else None,
                "status": event.status,
                "action": event.action,
                "detail": event.detail or None,
                "payload": event.payload,
            }
            for event in qs
        ]

        return Response(
            {
                "ok": True,
                "robot_id": robot_id,
                "count": ActionEvent.objects.filter(robot=robot).count(),
                "limit": limit,
                "offset": offset,
                "items": items,
            },
            status=status.HTTP_200_OK,
        )


class SessionSummaryView(APIView):
    def get(self, request, robot_id):
        robot = get_or_create_robot(robot_id)
        today = now().date()

        obstacle_count = ActionEvent.objects.filter(
            robot=robot,
            event="obstacle_detected",
            timestamp__date=today,
        ).count()

        return Response(
            {
                "ok": True,
                "robot_id": robot_id,
                "obstacle_events_today": obstacle_count,
            },
            status=status.HTTP_200_OK,
        )


class ConnectView(APIView):
    def post(self, request, robot_id):
        robot = get_or_create_robot(robot_id)
        addr = request.data.get("addr", "")
        client = ROSClient(robot_id)
        result = client.connect(addr)

        robot.addr = addr
        robot.save(update_fields=["addr"])

        return Response({"ok": True, **result}, status=200)


class RobotRootInfoView(APIView):
    def get(self, request, robot_id):
        try:
            data = ROSClient(robot_id).get_root_info()
            return Response({"success": True, "robot_id": robot_id, "data": data}, status=200)
        except Exception as e:
            return Response({"success": False, "robot_id": robot_id, "error": str(e)}, status=500)


class RobotHealthView(APIView):
    def get(self, request, robot_id):
        try:
            data = ROSClient(robot_id).get_health()
            return Response({"success": True, "robot_id": robot_id, "data": data}, status=200)
        except Exception as e:
            return Response({"success": False, "robot_id": robot_id, "error": str(e)}, status=500)


class NetworkMetricsView(APIView):
    def get(self, request, robot_id):
        try:
            data = ROSClient(robot_id).get_network_metrics()
            return Response({"ok": True, "data": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {
                    "ok": False,
                    "error": str(e),
                    "data": {
                        "uplink_kbps": None,
                        "downlink_kbps": None,
                        "latency_ms": None,
                        "jitter_ms": None,
                        "packet_loss_pct": None,
                        "signal_quality": 0,
                        "network_name": "Unknown network",
                        "network_type": "unknown",
                        "network_status": "offline",
                        "network_status_label": "Mat ket noi",
                        "network_summary": "Mat ket noi",
                        "connection": {},
                    },
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


class SystemMetricHistoryView(APIView):
    def get(self, request, robot_id):
        try:
            limit = max(1, min(int(request.query_params.get("limit", 120)), 500))
        except (TypeError, ValueError):
            limit = 120

        rows = list(
            MetricSystem.objects.filter(robot_id=robot_id)
            .order_by("-created_at")[:limit]
        )
        rows.reverse()

        return Response(
            {
                "success": True,
                "robot_id": robot_id,
                "items": [
                    {
                        "created_at": localtime(row.created_at).isoformat()
                        if row.created_at
                        else None,
                        "cpu": row.cpu,
                        "battery": row.battery,
                        "temperature": row.temperature,
                        "ram": row.ram,
                    }
                    for row in rows
                ],
            },
            status=status.HTTP_200_OK,
        )


class NavigationAnalyticsView(APIView):
    def get(self, request, robot_id):
        try:
            data = ROSClient(robot_id).get_navigation_summary_metrics()
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
                    "data": {
                        "path_length_m": None,
                        "path_efficiency_pct": None,
                        "distance": {},
                    },
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


class RobotFrameView(APIView):
    authentication_classes: ClassVar[list[type[Any]]] = []
    permission_classes: ClassVar[list[type[Any]]] = []

    def get(self, request, robot_id):
        try:
            upstream = ROSClient(robot_id).get_frame_response()
            content_type = upstream.headers.get("Content-Type", "image/jpeg")
            response = HttpResponse(upstream.content, content_type=content_type)
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            upstream.close()
            return response
        except Exception as e:
            return Response({"success": False, "robot_id": robot_id, "error": str(e)}, status=500)


class RobotTestPageView(APIView):
    authentication_classes: ClassVar[list[type[Any]]] = []
    permission_classes: ClassVar[list[type[Any]]] = []

    def get(self, request, robot_id):
        try:
            upstream = ROSClient(robot_id).get_test_page()
            content_type = upstream.headers.get("Content-Type", "text/html; charset=utf-8")
            response = HttpResponse(upstream.text, content_type=content_type)
            upstream.close()
            return response
        except Exception as e:
            return Response({"success": False, "robot_id": robot_id, "error": str(e)}, status=500)


class RobotStatusView(APIView):
    def get(self, request, robot_id):
        robot = get_or_create_robot(robot_id)
        client = ROSClient(robot_id)

        try:
            s = client.get_status() or {}
        except Exception as e:
            print("[RobotStatusView] get_status error:", e)
            s = {}

        changed_fields = []

        def _int_or_none(value):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None

        battery = _int_or_none(s.get("battery"))
        if battery is not None and hasattr(robot, "battery"):
            robot.battery = battery
            changed_fields.append("battery")

        fps = _int_or_none(s.get("fps"))
        if fps is not None and hasattr(robot, "fps"):
            robot.fps = fps
            changed_fields.append("fps")

        server_connected = bool(s)
        robot_serial_connected = s.get("robot_serial_connected")
        robot_connected = s.get("server_connected")
        if robot_connected is None:
            robot_connected = s.get("robot_connected")
        if robot_connected is None and server_connected:
            robot_connected = True
        if server_connected and s.get("lidar_running"):
            robot_connected = True
        if robot_connected is not None and hasattr(robot, "status_text"):
            robot.status_text = "online" if robot_connected else "offline"
            changed_fields.append("status_text")

        if changed_fields:
            robot.save(update_fields=changed_fields)

        data = RobotSerializer(robot).data
        data["server_connected"] = server_connected
        data["robot_connected"] = bool(robot_connected)
        data["telemetry"] = {
            "robot_connected": bool(robot_connected),
            "server_connected": server_connected,
            "robot_serial_connected": robot_serial_connected,
            "speed_mode": s.get("speed_mode"),
            "gait_type": s.get("gait_type"),
            "perform_enabled": s.get("perform_enabled"),
            "stabilizing_enabled": s.get("stabilizing_enabled"),
            "turn_speed_range": s.get("turn_speed_range"),
            "step_default": s.get("step_default"),
            "z_range": s.get("z_range"),
            "z_current": s.get("z_current"),
            "roll_current": s.get("roll_current"),
            "pitch_range": s.get("pitch_range"),
            "pitch_current": s.get("pitch_current"),
            "yaw_current": s.get("yaw_current"),
            "battery": s.get("battery"),
            "voltage": s.get("voltage"),
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
        return Response({"ok": ok, "mode": mode, "log": log_line}, status=code)


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
        action = (request.data.get("action") or "").strip().lower()
        mode = str(request.data.get("mode") or "").strip() or None
        map_name = str(request.data.get("map_name") or "").strip() or None
        map_arg = str(request.data.get("map_arg") or "").strip() or None
        client = ROSClient(robot_id)
        log_payload: dict[str, Any] = {"action": action}

        if action == "start" and mode:
            log_payload["mode"] = mode
        if action == "start" and map_name:
            log_payload["map_name"] = map_name
        if action == "start" and map_arg:
            log_payload["map_arg"] = map_arg

        try:
            if action == "start":
                try:
                    slam_status = client.get_slam_status() or {}
                except Exception as e:
                    slam_status = {}
                    logger.info("Lidar preflight status unavailable for %s: %s", robot_id, e)

                should_restart_for_static_map = mode == "navigation"
                if slam_status.get("running") is True and not should_restart_for_static_map:
                    log_line = build_log(robot_id, "LIDAR", log_payload, True, None)
                    return Response(
                        {
                            "ok": True,
                            "already_running": True,
                            "log": log_line,
                        },
                        status=status.HTTP_200_OK,
                    )

            client.lidar(action, mode=mode, map_name=map_name, map_arg=map_arg)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "LIDAR", log_payload, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)

class ResetLidarView(APIView):
    def post(self, request, robot_id):
        wait_seconds = request.data.get("wait_seconds")
        mode = str(request.data.get("mode") or "").strip() or None
        map_name = str(request.data.get("map_name") or "").strip() or None
        map_arg = str(request.data.get("map_arg") or "").strip() or None
        try:
            applied_wait = ROSClient(robot_id).reset_lidar(
                wait_seconds=wait_seconds,
                mode=mode,
                map_name=map_name,
                map_arg=map_arg,
            )
            ok, err = True, None
        except Exception as e:
            applied_wait = None
            ok, err = False, str(e)

        log_payload: dict[str, Any] = {
            "wait_seconds": applied_wait if ok else wait_seconds,
        }
        if mode:
            log_payload["mode"] = mode
        if map_name:
            log_payload["map_name"] = map_name
        if map_arg:
            log_payload["map_arg"] = map_arg

        log_line = build_log(
            robot_id,
            "RESET_LIDAR",
            log_payload,
            ok,
            err,
        )
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response(
            {
                "ok": ok,
                "wait_seconds": applied_wait,
                "log": log_line,
            },
            status=code,
        )


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


class PaceModeView(APIView):
    def post(self, request, robot_id):
        mode = request.data.get("mode")
        try:
            ROSClient(robot_id).set_pace_mode(mode)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "PACE_MODE", {"mode": mode}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "mode": mode, "log": log_line}, status=code)


class ZControlView(APIView):
    def post(self, request, robot_id):
        payload = request.data
        try:
            ROSClient(robot_id).z_control(payload)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "Z_CONTROL", payload, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)


class AttitudeControlView(APIView):
    def post(self, request, robot_id):
        payload = request.data
        try:
            ROSClient(robot_id).attitude_control(payload)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "ATTITUDE_CONTROL", payload, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)


class GaitTypeView(APIView):
    def post(self, request, robot_id):
        mode = request.data.get("mode")
        try:
            ROSClient(robot_id).gait_type(mode)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "GAIT_TYPE", {"mode": mode}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "mode": mode, "log": log_line}, status=code)


class PerformModeView(APIView):
    def post(self, request, robot_id):
        action = request.data.get("action")
        try:
            ROSClient(robot_id).perform(action)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "PERFORM", {"action": action}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "action": action, "log": log_line}, status=code)


class MarkTimeView(APIView):
    def post(self, request, robot_id):
        value = request.data.get("value")
        try:
            ROSClient(robot_id).mark_time(value)
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "MARK_TIME", {"value": value}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "value": value, "log": log_line}, status=code)


class ResetRobotView(APIView):
    def post(self, request, robot_id):
        try:
            ROSClient(robot_id).reset()
            ok, err = True, None
        except Exception as e:
            ok, err = False, str(e)

        log_line = build_log(robot_id, "RESET", {}, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "log": log_line}, status=code)


class RawControlView(APIView):
    def post(self, request, robot_id):
        payload = request.data
        try:
            result = ROSClient(robot_id).raw_control(payload)
            ok, err = True, None
        except Exception as e:
            result = None
            ok, err = False, str(e)

        log_line = build_log(robot_id, "RAW_CONTROL", payload, ok, err)
        code = status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"ok": ok, "result": result, "log": log_line}, status=code)


class ControlStatusView(APIView):
    def get(self, request, robot_id):
        try:
            data = ROSClient(robot_id).get_control_status()
            return Response({"success": True, "robot_id": robot_id, "data": data}, status=200)
        except Exception as e:
            return Response({"success": False, "robot_id": robot_id, "error": str(e)}, status=500)


class TextCommandView(APIView):
    def post(self, request, *args, **kwargs):
        robot_id = kwargs.get("robot_id", "robot-a")
        robot_addr = (
            request.data.get("addr")
            or request.data.get("robot_ip")
            or request.data.get("robot_addr")
            or ""
        ).strip()

        text = (request.data.get("text") or "").strip()
        dry_run = bool(request.data.get("dry_run", False))

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

        robot = get_or_create_robot(robot_id)
        if robot.addr != robot_addr:
            robot.addr = robot_addr
            robot.save(update_fields=["addr"])

        try:
            planner_source = "openrouter"
            llm_error = None

            try:
                plan = map_text_with_openrouter(text)
                if not plan.get("actions") and not plan.get("reply_text"):
                    raise ValueError("LLM không chọn action nào")
            except Exception as exc:
                llm_error = str(exc)
                planner_source = "fallback_keyword"

                tool_name, arguments, mapping = map_text_to_tool(text)
                plan = {
                    "actions": [
                        {
                            "tool": tool_name,
                            "arguments": arguments,
                            "mapping": mapping,
                        }
                    ]
                }

            if dry_run:
                return Response(
                    {
                        "success": True,
                        "dry_run": True,
                        "robot_id": robot_id,
                        "robot_addr": robot_addr,
                        "input_text": text,
                        "planner_source": planner_source,
                        "llm_error": llm_error,
                        "plan": plan,
                    },
                    status=status.HTTP_200_OK,
                )

            results = []

            for action in plan.get("actions", []):
                tool_name = action["tool"]
                arguments = action.get("arguments", {})
                mapping = action.get(
                    "mapping",
                    {
                        "source": planner_source,
                        "intent": "llm_robot_command",
                    },
                )

                if tool_name in {"go_to_point", "goto_waypoints"}:
                    result = _build_voice_navigation_result(
                        robot_id=robot_id,
                        robot_addr=robot_addr,
                        tool_name=tool_name,
                        arguments=arguments,
                        mapping=mapping,
                    )

                elif tool_name == "set_posture":
                    ROSClient(robot_id).posture(arguments["name"])
                    result = {
                        "ok": True,
                        "robot_addr": robot_addr,
                        "tool": tool_name,
                        "arguments": arguments,
                        "mapping": mapping,
                        "content": {"success": True},
                    }

                elif tool_name == "play_behavior":
                    ROSClient(robot_id).behavior(arguments["name"])
                    result = {
                        "ok": True,
                        "robot_addr": robot_addr,
                        "tool": tool_name,
                        "arguments": arguments,
                        "mapping": mapping,
                        "content": {"success": True},
                    }

                elif tool_name == "reset_robot":
                    ROSClient(robot_id).reset()
                    result = {
                        "ok": True,
                        "robot_addr": robot_addr,
                        "tool": tool_name,
                        "arguments": arguments,
                        "mapping": mapping,
                        "content": {"success": True},
                    }

                elif tool_name == "rotation":
                    ROSClient(robot_id).raw_control({"command": "rotation"})
                    result = {
                        "ok": True,
                        "robot_addr": robot_addr,
                        "tool": tool_name,
                        "arguments": arguments,
                        "mapping": mapping,
                        "content": {"success": True},
                    }

                elif tool_name == "stop_navigation":
                    patrol_manager.stop(robot_id)
                    result = {
                        "ok": True,
                        "robot_addr": robot_addr,
                        "tool": tool_name,
                        "arguments": arguments,
                        "mapping": mapping,
                        "content": {"success": True},
                    }

                else:
                    raise ValueError(f"Unsupported tool: {tool_name}")

                results.append(result)

            if not results and plan.get("reply_text"):
                reply_text = str(plan.get("reply_text") or "").strip()
                log_line = (
                    f'TEXT_COMMAND {json.dumps({"addr": robot_addr, "text": text}, ensure_ascii=False)} â†’ CHAT'
                )
                return Response(
                    {
                        "success": True,
                        "robot_id": robot_id,
                        "robot_addr": robot_addr,
                        "input_text": text,
                        "planner_source": planner_source,
                        "llm_error": llm_error,
                        "plan": plan,
                        "result": None,
                        "results": [],
                        "reply_text": reply_text,
                        "log": log_line,
                    },
                    status=status.HTTP_200_OK,
                )

            log_line = (
                f'TEXT_COMMAND {json.dumps({"addr": robot_addr, "text": text}, ensure_ascii=False)} → OK'
            )
            reply_text = " ".join(
                build_bridge_response_text(result)
                for result in results
            ).strip() or str(plan.get("reply_text") or "").strip() or "Em \u0111\u00e3 nh\u1eadn l\u1ec7nh."

            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "robot_addr": robot_addr,
                    "input_text": text,
                    "planner_source": planner_source,
                    "llm_error": llm_error,
                    "plan": plan,
                    "result": results[0] if results else None,
                    "results": results,
                    "reply_text": reply_text,
                    "log": log_line,
                },
                status=status.HTTP_200_OK,
            )

        except AmbiguousCommandError as e:
            return Response(
                {
                    "success": False,
                    "robot_addr": robot_addr,
                    "input_text": text,
                    "error": str(e),
                    "error_code": "ambiguous_command",
                    "normalized_text": e.normalized_text,
                    "candidate_matches": e.matches,
                },
                status=status.HTTP_400_BAD_REQUEST,
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


class XiaozhiBridgeHealthView(APIView):
    authentication_classes: ClassVar[list[type[Any]]] = []
    permission_classes: ClassVar[list[type[Any]]] = []

    def get(self, request):
        return Response(
            {
                "success": True,
                "service": "xiaozhi_bridge",
                "default_robot_id": settings.XIAOZHI_DEFAULT_ROBOT_ID,
                "default_robot_addr": settings.XIAOZHI_DEFAULT_ROBOT_ADDR,
                "token_configured": bool(str(settings.XIAOZHI_BRIDGE_TOKEN).strip()),
            },
            status=status.HTTP_200_OK,
        )


class XiaozhiBridgeCommandView(APIView):
    authentication_classes: ClassVar[list[type[Any]]] = []
    permission_classes: ClassVar[list[type[Any]]] = []

    def post(self, request):
        expected_token = str(settings.XIAOZHI_BRIDGE_TOKEN or "").strip()
        provided_token = _get_xiaozhi_bridge_token(request)

        if expected_token and provided_token != expected_token:
            return Response(
                {
                    "success": False,
                    "error": "invalid bridge token",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        robot_id = str(
            request.data.get("robot_id")
            or settings.XIAOZHI_DEFAULT_ROBOT_ID
            or "robot-a"
        ).strip()
        robot_addr = _resolve_robot_addr_for_bridge(request, robot_id)
        text = str(
            request.data.get("text")
            or request.data.get("query")
            or request.data.get("command")
            or ""
        ).strip()
        dry_run = bool(request.data.get("dry_run", False))

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
            result = _build_xiaozhi_bridge_result(
                robot_id=robot_id,
                robot_addr=robot_addr,
                text=text,
                dry_run=dry_run,
            )
            return Response(
                {
                    "success": True,
                    "source": "xiaozhi_bridge",
                    "robot_id": robot_id,
                    "robot_addr": robot_addr,
                    "input_text": text,
                    "dry_run": dry_run,
                    "reply_text": result.get("bridge_reply_text"),
                    "result": result,
                },
                status=status.HTTP_200_OK,
            )
        except AmbiguousCommandError as e:
            return Response(
                {
                    "success": False,
                    "source": "xiaozhi_bridge",
                    "robot_id": robot_id,
                    "robot_addr": robot_addr,
                    "input_text": text,
                    "error": str(e),
                    "error_code": "ambiguous_command",
                    "normalized_text": e.normalized_text,
                    "candidate_matches": e.matches,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("XiaozhiBridgeCommandView error")
            return Response(
                {
                    "success": False,
                    "source": "xiaozhi_bridge",
                    "robot_id": robot_id,
                    "robot_addr": robot_addr,
                    "input_text": text,
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
            include_scan = str(request.query_params.get("scan", "1")).lower() not in {
                "0",
                "false",
                "no",
            }
            data = ROSClient(robot_id).get_slam_state_for_ui(
                include_scan_points=include_scan,
            )
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


class ClearNavigationView(APIView):
    def post(self, request, robot_id):
        try:
            result = ROSClient(robot_id).clear_navigation()
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "result": result,
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


class InitialPoseView(APIView):
    def post(self, request, robot_id):
        body = request.data or {}
        try:
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

        try:
            result = ROSClient(robot_id).set_initial_pose(x=x, y=y, yaw=yaw)
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "result": result,
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
    authentication_classes: ClassVar[list[type[Any]]] = []
    permission_classes: ClassVar[list[type[Any]]] = []

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

    authentication_classes: ClassVar[list[type[Any]]] = []
    permission_classes: ClassVar[list[type[Any]]] = []

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
            return Response({"success": False, "error": f"invalid payload: {e}"}, status=400)

        if not name:
            return Response({"success": False, "error": "name is required"}, status=400)

        try:
            result = ROSClient(robot_id).create_point(name=name, x=x, y=y, yaw=yaw)
            log_line = build_log(robot_id, "CREATE_POINT", {"name": name, "x": x, "y": y, "yaw": yaw}, True, None)
            return Response({"success": True, "robot_id": robot_id, "result": result, "log": log_line}, status=200)
        except Exception as e:
            log_line = build_log(robot_id, "CREATE_POINT", {"name": name, "x": x, "y": y, "yaw": yaw}, False, str(e))
            return Response({"success": False, "robot_id": robot_id, "error": str(e), "log": log_line}, status=500)


class PointFromObstacleView(APIView):
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
            client = ROSClient(robot_id)
            state = client.get_slam_state_for_ui(include_scan_points=True)
            obstacle = state.get("nearest_obstacle_ahead")

            if not obstacle:
                return Response(
                    {
                        "success": False,
                        "robot_id": robot_id,
                        "error": "no obstacle ahead",
                        "reason": "no_obstacle",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            x = float(obstacle["x"])
            y = float(obstacle["y"])
            if body.get("yaw") is not None:
                try:
                    yaw = float(body.get("yaw", 0.0))
                except Exception:
                    yaw = 0.0
            else:
                pose = state.get("pose") or {}
                if pose.get("ok"):
                    robot_x = float(pose.get("x", 0.0))
                    robot_y = float(pose.get("y", 0.0))
                    yaw = math.atan2(y - robot_y, x - robot_x)
                else:
                    yaw = 0.0

            result = client.create_point(name=name, x=x, y=y, yaw=yaw)
            log_line = build_log(
                robot_id,
                "CREATE_POINT_FROM_OBSTACLE",
                {"name": name, "x": x, "y": y, "yaw": yaw},
                True,
                None,
            )
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "point": {"name": name, "x": x, "y": y, "yaw": yaw},
                    "result": result,
                    "log": log_line,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            log_line = build_log(
                robot_id,
                "CREATE_POINT_FROM_OBSTACLE",
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
            client = ROSClient(robot_id)
            points = client.get_points() or {}
            point = points.get(name) or points.get(name.upper())
            if point is None:
                return Response(
                    {
                        "success": False,
                        "robot_id": robot_id,
                        "error": f"point '{name}' not found",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            standoff_m = float(body.get("standoff_m", 0.35))
            point_x = float(point["x"])
            point_y = float(point["y"])
            approach_yaw = float(point.get("yaw", 0.0))
            target_x = point_x - (standoff_m * math.cos(approach_yaw))
            target_y = point_y - (standoff_m * math.sin(approach_yaw))
            target_yaw = math.atan2(point_y - target_y, point_x - target_x)

            result = client.set_goal_pose(target_x, target_y, target_yaw)

            log_line = build_log(
                robot_id,
                "GO_TO_POINT",
                {
                    "name": name,
                    "standoff_m": standoff_m,
                    "source": {"x": point_x, "y": point_y, "yaw": approach_yaw},
                    "goal": {"x": target_x, "y": target_y, "yaw": target_yaw},
                },
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


class ManualGoalView(APIView):
    def post(self, request, robot_id):
        body = request.data or {}

        try:
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

        addr = str(body.get("addr") or "").strip()
        if addr:
            robot = get_or_create_robot(robot_id)
            if robot.addr != addr:
                robot.addr = addr
                robot.save(update_fields=["addr"])

        route_name = str(body.get("route_name") or "manual_goal").strip() or "manual_goal"

        try:
            mission = patrol_manager.start_manual_goal(
                robot_id=robot_id,
                route_name=route_name,
                x=x,
                y=y,
                yaw=yaw,
            )
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "mission": mission_to_dict(mission),
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
                status=status.HTTP_400_BAD_REQUEST,
            )

class PatrolStartView(APIView):
    def post(self, request, robot_id):
        body = request.data or {}
        route_name = str(body.get("route_name", "custom_route")).strip()
        points = body.get("points") or []
        wait_sec = int(body.get("wait_sec_per_point", 3))
        max_retry = int(body.get("max_retry_per_point", 1))
        skip_on_fail = bool(body.get("skip_on_fail", True))

        try:
            mission = patrol_manager.start(
                robot_id=robot_id,
                route_name=route_name,
                points=points,
                wait_sec_per_point=wait_sec,
                max_retry_per_point=max_retry,
                skip_on_fail=skip_on_fail,
            )
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "mission": mission_to_dict(mission),
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
                status=status.HTTP_400_BAD_REQUEST,
            )

class PatrolStopView(APIView):
    def post(self, request, robot_id):
        patrol_manager.stop(robot_id)
        return Response({"success": True, "robot_id": robot_id}, status=status.HTTP_200_OK)


class PatrolPauseView(APIView):
    def post(self, request, robot_id):
        patrol_manager.pause(robot_id)
        return Response({"success": True, "robot_id": robot_id}, status=status.HTTP_200_OK)


class PatrolResumeView(APIView):
    def post(self, request, robot_id):
        patrol_manager.resume(robot_id)
        return Response({"success": True, "robot_id": robot_id}, status=status.HTTP_200_OK)


class PatrolStatusView(APIView):
    def get(self, request, robot_id):
        mission = get_current_mission(robot_id)
        return Response(
            {
                "success": True,
                "robot_id": robot_id,
                "running": mission is not None,
                "mission": mission_to_dict(mission) if mission else None,
            },
            status=status.HTTP_200_OK,
        )


class PatrolHistoryView(APIView):
    def get(self, request, robot_id):
        date_filter = request.query_params.get("date")
        history = get_history(robot_id, date_filter=date_filter)
        return Response(
            {
                "success": True,
                "robot_id": robot_id,
                "history": [mission_to_dict(m) for m in history],
            },
            status=status.HTTP_200_OK,
        )
