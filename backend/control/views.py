import math
import asyncio
import time
import uuid
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
from .models import Robot, ActionEvent, MetricSystem, QRLocalizationMetric
from .serializers import RobotSerializer
from .services.ros import ROSClient
from .line_tracking_backend import LineTrackingServer
from .services.mcp_voice import AmbiguousCommandError, execute_mcp_tool, map_text_to_tool
from .services.qr_detect import (
    MIN_TARGET_DISTANCE_M,
    TARGET_PUSH_M,
    detect_qr_state_once,
    generate_qr_video_frames,
    get_current_qr_state,
    save_qr_metric_event,
)
from .services.patrol_manager import patrol_manager
from .services.patrol_store import append_history, get_current_mission, get_history
from .services.patrol_types import PatrolMission, PatrolPointResult
from .services.voice_response import build_voice_response_text
from .services.llm_voice import map_text_with_openrouter
from .services.tts_voice import DEFAULT_VOICE, VOICE_GENDER, synthesize_vietnamese_speech
from .services.qr_localization_metrics import (
    create_qr_localization_metric,
    metric_to_dict,
    summarize_qr_localization_metrics,
)
from .services.voice_conversation_metrics import record_voice_conversation_metric
from .services.slam_payload import find_nearest_obstacle_at_bearing
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


def log_qr_point_save_failure(robot_id: str, reason: str, detail: str, payload: dict[str, Any] | None = None) -> None:
    robot = get_or_create_robot(robot_id)
    ActionEvent.objects.create(
        robot=robot,
        event="qr_point_save",
        severity=ActionEvent.Severity.WARNING,
        status=ActionEvent.Status.FAILED,
        action="create_point_from_obstacle",
        detail=detail,
        payload={
            "reason": reason,
            **(payload or {}),
        },
    )


def _record_voice_command_metric(
    *,
    robot_id: str,
    robot_addr: str,
    input_text: str,
    planner_source: str,
    success: bool,
    dry_run: bool,
    response_time_ms: float | None,
    reply_text: str = "",
    llm_error: str = "",
    error_code: str = "",
    plan: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    results: list[Any] | None = None,
    response_payload: dict[str, Any] | None = None,
) -> None:
    try:
        record_voice_conversation_metric(
            robot_id,
            input_text=input_text,
            robot_addr=robot_addr,
            planner_source=planner_source,
            success=success,
            dry_run=dry_run,
            response_time_ms=response_time_ms,
            reply_text=reply_text,
            llm_error=llm_error,
            error_code=error_code,
            plan_json=plan or {},
            result_json=result,
            results_json=results or [],
            response_json=response_payload or {},
            payload=response_payload or {},
        )
    except Exception as exc:
        logger.warning("Failed to record voice conversation metric for %s: %s", robot_id, exc)


def get_latest_metric_value(robot_id: str, field: str) -> float | None:
    if field not in {"cpu", "battery", "temperature", "ram"}:
        return None

    row = (
        MetricSystem.objects.filter(robot_id=robot_id)
        .exclude(**{f"{field}__isnull": True})
        .order_by("-created_at")
        .first()
    )
    if not row:
        return None
    return getattr(row, field, None)


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
            for r in (getattr(mission, "results", None) or [])
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


class QRLocalizationMetricView(APIView):
    def get(self, request, robot_id):
        try:
            limit = max(1, min(int(request.query_params.get("limit", 100)), 500))
        except Exception:
            limit = 100

        qs = QRLocalizationMetric.objects.filter(robot_id=robot_id)
        label = str(request.query_params.get("label") or "").strip()
        trial_name = str(request.query_params.get("trial") or "").strip()
        if label:
            qs = qs.filter(label=label)
        if trial_name:
            qs = qs.filter(trial_name=trial_name)

        rows = list(qs[:limit])
        return Response(
            {
                "success": True,
                "robot_id": robot_id,
                "summary": summarize_qr_localization_metrics(rows),
                "items": [metric_to_dict(row) for row in rows],
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, robot_id):
        try:
            row = create_qr_localization_metric(robot_id, request.data or {})
            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "data": metric_to_dict(row),
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception("QRLocalizationMetricView error")
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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
            total_dist = None
            try:
                history = get_history(robot_id)
                total_dist = sum(
                    (float(m.total_distance_m) if getattr(m, "total_distance_m", None) else 0.0)
                    for m in history
                )
            except Exception:
                pass

            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": str(e),
                    "data": {
                        "path_length_m": round(total_dist, 2) if total_dist and total_dist > 0 else None,
                        "path_efficiency_pct": None,
                        "distance": {},
                    },
                },
                status=status.HTTP_200_OK,
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

        latest_metrics = {
            "cpu": get_latest_metric_value(robot_id, "cpu"),
            "battery": get_latest_metric_value(robot_id, "battery"),
            "temperature": get_latest_metric_value(robot_id, "temperature"),
            "ram": get_latest_metric_value(robot_id, "ram"),
        }
        system_data = s.get("system")
        if not isinstance(system_data, dict):
            system_data = {}
        system_data = {
            **system_data,
            "cpu_percent": system_data.get("cpu_percent")
            if system_data.get("cpu_percent") is not None
            else latest_metrics["cpu"],
            "battery": system_data.get("battery")
            if system_data.get("battery") is not None
            else latest_metrics["battery"],
            "temperature": system_data.get("temperature")
            if system_data.get("temperature") is not None
            else latest_metrics["temperature"],
            "ram": system_data.get("ram")
            if system_data.get("ram") is not None
            else (
                f"{latest_metrics['ram']}%" if latest_metrics["ram"] is not None else None
            ),
        }
        if not any(value is not None for value in system_data.values()):
            system_data = None

        telemetry_battery = s.get("battery")
        if telemetry_battery is None:
            telemetry_battery = latest_metrics["battery"]
        if telemetry_battery is None:
            telemetry_battery = getattr(robot, "battery", None)

        data = RobotSerializer(robot).data
        if latest_metrics["battery"] is not None:
            data["battery"] = latest_metrics["battery"]
        data["metric_system_latest"] = latest_metrics
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
            "battery": telemetry_battery,
            "voltage": s.get("voltage"),
            "fw": s.get("fw"),
            "fps": s.get("fps") if s.get("fps") is not None else getattr(robot, "fps", None),
            "system": system_data,
            "metric_system_latest": latest_metrics,
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
        request_started = time.perf_counter()
        robot_id = kwargs.get("robot_id", "robot-a")
        robot_addr = (
            request.data.get("addr")
            or request.data.get("robot_ip")
            or request.data.get("robot_addr")
            or ""
        ).strip()

        text = (request.data.get("text") or "").strip()
        dry_run = bool(request.data.get("dry_run", False))
        planner_source = ""
        llm_error = ""
        plan: dict[str, Any] = {}
        results: list[dict[str, Any]] = []
        reply_text = ""

        if not robot_addr:
            response_payload = {
                "success": False,
                "error": "robot addr is required",
            }
            _record_voice_command_metric(
                robot_id=robot_id,
                robot_addr=robot_addr,
                input_text=text,
                planner_source=planner_source,
                success=False,
                dry_run=dry_run,
                response_time_ms=(time.perf_counter() - request_started) * 1000.0,
                reply_text=reply_text,
                llm_error=llm_error,
                error_code="robot_addr_required",
                plan=plan,
                results=results,
                response_payload=response_payload,
            )
            return Response(response_payload, status=status.HTTP_400_BAD_REQUEST)

        if not text:
            response_payload = {
                "success": False,
                "error": "text is required",
            }
            _record_voice_command_metric(
                robot_id=robot_id,
                robot_addr=robot_addr,
                input_text=text,
                planner_source=planner_source,
                success=False,
                dry_run=dry_run,
                response_time_ms=(time.perf_counter() - request_started) * 1000.0,
                reply_text=reply_text,
                llm_error=llm_error,
                error_code="text_required",
                plan=plan,
                results=results,
                response_payload=response_payload,
            )
            return Response(response_payload, status=status.HTTP_400_BAD_REQUEST)

        robot = get_or_create_robot(robot_id)
        if robot.addr != robot_addr:
            robot.addr = robot_addr
            robot.save(update_fields=["addr"])

        try:
            planner_source = "openrouter"

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
                reply_text = str(plan.get("reply_text") or "").strip()
                response_payload = {
                    "success": True,
                    "dry_run": True,
                    "robot_id": robot_id,
                    "robot_addr": robot_addr,
                    "input_text": text,
                    "planner_source": planner_source,
                    "llm_error": llm_error or None,
                    "plan": plan,
                }
                _record_voice_command_metric(
                    robot_id=robot_id,
                    robot_addr=robot_addr,
                    input_text=text,
                    planner_source=planner_source,
                    success=True,
                    dry_run=True,
                    response_time_ms=(time.perf_counter() - request_started) * 1000.0,
                    reply_text=reply_text,
                    llm_error=llm_error,
                    error_code="",
                    plan=plan,
                    results=results,
                    response_payload=response_payload,
                )
                return Response(response_payload, status=status.HTTP_200_OK)

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

                result = execute_mcp_tool(
                    robot_addr=robot_addr,
                    text=text,
                    tool_name=tool_name,
                    arguments=arguments,
                    mapping=mapping,
                )

                results.append(result)

            if not results and plan.get("reply_text"):
                reply_text = str(plan.get("reply_text") or "").strip()
                log_line = f'TEXT_COMMAND {json.dumps({"addr": robot_addr, "text": text}, ensure_ascii=False)} -> CHAT'
                response_payload = {
                    "success": True,
                    "robot_id": robot_id,
                    "robot_addr": robot_addr,
                    "input_text": text,
                    "planner_source": planner_source,
                    "llm_error": llm_error or None,
                    "plan": plan,
                    "result": None,
                    "results": [],
                    "reply_text": reply_text,
                    "log": log_line,
                }
                _record_voice_command_metric(
                    robot_id=robot_id,
                    robot_addr=robot_addr,
                    input_text=text,
                    planner_source=planner_source,
                    success=True,
                    dry_run=False,
                    response_time_ms=(time.perf_counter() - request_started) * 1000.0,
                    reply_text=reply_text,
                    llm_error=llm_error,
                    error_code="",
                    plan=plan,
                    results=results,
                    response_payload=response_payload,
                )
                return Response(response_payload, status=status.HTTP_200_OK)

            log_line = f'TEXT_COMMAND {json.dumps({"addr": robot_addr, "text": text}, ensure_ascii=False)} -> OK'
            reply_text = " ".join(
                build_voice_response_text(result)
                for result in results
            ).strip() or str(plan.get("reply_text") or "").strip() or "Em đã nhận lệnh."
            response_payload = {
                "success": True,
                "robot_id": robot_id,
                "robot_addr": robot_addr,
                "input_text": text,
                "planner_source": planner_source,
                "llm_error": llm_error or None,
                "plan": plan,
                "result": results[0] if results else None,
                "results": results,
                "reply_text": reply_text,
                "log": log_line,
            }
            _record_voice_command_metric(
                robot_id=robot_id,
                robot_addr=robot_addr,
                input_text=text,
                planner_source=planner_source,
                success=True,
                dry_run=False,
                response_time_ms=(time.perf_counter() - request_started) * 1000.0,
                reply_text=reply_text,
                llm_error=llm_error,
                error_code="",
                plan=plan,
                result=results[0] if results else None,
                results=results,
                response_payload=response_payload,
            )
            return Response(response_payload, status=status.HTTP_200_OK)

        except AmbiguousCommandError as e:
            response_payload = {
                "success": False,
                "robot_addr": robot_addr,
                "input_text": text,
                "error": str(e),
                "error_code": "ambiguous_command",
                "normalized_text": e.normalized_text,
                "candidate_matches": e.matches,
            }
            _record_voice_command_metric(
                robot_id=robot_id,
                robot_addr=robot_addr,
                input_text=text,
                planner_source=planner_source,
                success=False,
                dry_run=dry_run,
                response_time_ms=(time.perf_counter() - request_started) * 1000.0,
                reply_text=reply_text,
                llm_error=llm_error,
                error_code="ambiguous_command",
                plan=plan,
                results=results,
                response_payload=response_payload,
            )
            return Response(response_payload, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.exception("TextCommandView error")
            log_line = (
                f'TEXT_COMMAND {json.dumps({"addr": robot_addr, "text": text}, ensure_ascii=False)} '
                f"-> ERROR: {str(e)}"
            )
            response_payload = {
                "success": False,
                "robot_addr": robot_addr,
                "input_text": text,
                "error": str(e),
                "log": log_line,
            }
            _record_voice_command_metric(
                robot_id=robot_id,
                robot_addr=robot_addr,
                input_text=text,
                planner_source=planner_source,
                success=False,
                dry_run=dry_run,
                response_time_ms=(time.perf_counter() - request_started) * 1000.0,
                reply_text=reply_text,
                llm_error=llm_error or str(e),
                error_code="unexpected_error",
                plan=plan,
                results=results,
                response_payload=response_payload,
            )
            return Response(response_payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            position_json = data.get("position_json")
            if isinstance(position_json, dict) and position_json.get("detected"):
                position = position_json.get("position") or {}
                angle_rad = position.get("angle_rad")
                try:
                    bearing_rad = float(angle_rad)
                except (TypeError, ValueError):
                    bearing_rad = None

                if bearing_rad is not None and math.isfinite(bearing_rad):
                    try:
                        slam_state = ROSClient(robot_id).get_slam_state_for_ui(
                            include_scan_points=True,
                            max_scan_points=240,
                        )
                        pose = slam_state.get("pose") or {}
                        scan_points = (slam_state.get("scan") or {}).get("points") or []
                        lidar_point = find_nearest_obstacle_at_bearing(
                            pose,
                            scan_points,
                            bearing_rad,
                        )
                        if lidar_point:
                            lidar_distance = float(lidar_point["dist"])
                            position_json["camera_position"] = dict(position)
                            position_json["lidar"] = {
                                "ok": True,
                                "source": "scan_point_at_qr_bearing",
                                "distance_m": lidar_distance,
                                "x": lidar_point.get("x"),
                                "y": lidar_point.get("y"),
                                "bearing_rad": lidar_point.get("bearing_rad"),
                                "bearing_error_rad": lidar_point.get("bearing_error_rad"),
                            }
                            position_json["position"] = {
                                **position,
                                "distance_m": lidar_distance,
                                "forward_z_m": lidar_distance * math.cos(bearing_rad),
                                "lateral_x_m": lidar_distance * math.sin(bearing_rad),
                                "distance_source": "lidar",
                            }
                            target_distance = max(
                                lidar_distance + TARGET_PUSH_M,
                                MIN_TARGET_DISTANCE_M,
                            )
                            position_json["target"] = {
                                **(position_json.get("target") or {}),
                                "x_m": target_distance * math.sin(bearing_rad),
                                "z_m": target_distance * math.cos(bearing_rad),
                                "distance_m": target_distance,
                                "distance_source": "lidar",
                            }
                        else:
                            position_json["lidar"] = {
                                "ok": False,
                                "source": "scan_point_at_qr_bearing",
                                "reason": "no_scan_point_on_qr_bearing",
                            }
                    except Exception as lidar_error:
                        logger.warning("QRPositionView lidar distance fallback failed: %s", lidar_error)
                        position_json["lidar"] = {
                            "ok": False,
                            "source": "scan_point_at_qr_bearing",
                            "reason": str(lidar_error),
                        }

            return Response(
                {
                    "success": True,
                    "robot_id": robot_id,
                    "data": position_json,
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
        qr_detected = bool(body.get("qr_detected", False))

        if not qr_detected:
            log_qr_point_save_failure(
                robot_id,
                "qr_not_detected",
                "QR not detected; point save blocked",
                payload={"name": name},
            )
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": "QR not detected",
                    "reason": "qr_not_detected",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not name:
            log_qr_point_save_failure(
                robot_id,
                "name_required",
                "QR detected but name is empty",
                payload={"name": name},
            )
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": "name is required",
                    "reason": "name_required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            client = ROSClient(robot_id)
            state = client.get_slam_state_for_ui(include_scan_points=True)
            obstacle = state.get("nearest_obstacle_ahead")

            if not obstacle:
                log_qr_point_save_failure(
                    robot_id,
                    "no_obstacle",
                    "No obstacle ahead; point save blocked",
                    payload={"name": name, "qr_detected": qr_detected},
                )
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


class PatrolUIActionHistoryView(APIView):
    def post(self, request, robot_id):
        body = request.data or {}
        action = str(body.get("action") or "").strip().lower()
        if action not in {"goal", "initial_pose"}:
            return Response(
                {
                    "success": False,
                    "robot_id": robot_id,
                    "error": "action must be 'goal' or 'initial_pose'",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        now_ts = time.time()
        point_label = "GOAL" if action == "goal" else "INITPOSE"
        route_name = "docker_ui_goal" if action == "goal" else "docker_ui_initial_pose"
        mission = PatrolMission(
            mission_id=f"docker_ui_{action}_{uuid.uuid4().hex[:8]}",
            robot_id=robot_id,
            route_name=route_name,
            points=[f"{point_label}({x:.3f},{y:.3f})"],
            wait_sec_per_point=0,
            max_retry_per_point=0,
            skip_on_fail=False,
            status="DONE",
            current_index=0,
            started_at=now_ts,
            finished_at=now_ts,
            total_distance_m=0.0,
        )
        mission.results.append(
            PatrolPointResult(
                point=mission.points[0],
                status="SUCCESS",
                attempts=1,
                started_at=now_ts,
                finished_at=now_ts,
                reach_time_sec=0.0,
                distance_on_finish=0.0,
                message=str(body.get("message") or f"recorded {action} from docker ui"),
            )
        )
        append_history(robot_id, mission)

        return Response(
            {
                "success": True,
                "robot_id": robot_id,
                "mission": mission_to_dict(mission),
            },
            status=status.HTTP_201_CREATED,
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


# views.py
class PatrolHistoryView(APIView):
    def get(self, request, robot_id):
        date_filter = request.query_params.get("date")

        if date_filter in (None, "", "all", "alltime", "all_time"):
            date_filter = "all"
        elif date_filter == "today":
            date_filter = localtime(now()).date().isoformat()

        history = get_history(robot_id, date_filter=date_filter)
        return Response({
            "success": True,
            "robot_id": robot_id,
            "history": [mission_to_dict(m) for m in history],
        }, status=status.HTTP_200_OK)
