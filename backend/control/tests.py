import json
import math
from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import ActionEvent, MetricSystem, QRLocalizationMetric, Robot, VoiceConversationMetric
from .services.patrol_manager import PatrolManager
from .services.patrol_store import append_history, get_history
from .services.patrol_types import PatrolMission, PatrolPointResult
from .services.ros import ROSClient
from .services.qr_detect import enrich_detection_result_with_lidar
from .services.models import QRItem, DetectionResult
from .services.qr_localization_metrics import create_qr_localization_metric
from .services.slam_payload import build_slam_ui_state, find_nearest_obstacle_at_bearing


class SlamPayloadTests(SimpleTestCase):
    def test_builds_ui_state_from_raw_scan_on_backend(self):
        payload = build_slam_ui_state(
            {
                "map_version": 7,
                "render_info": {"resolution": 0.05},
                "pose": {"ok": True, "x": 0.0, "y": 0.0, "theta": 0.0},
                "goal": {"x": 2.0, "y": 0.0, "yaw": 0.0},
                "paths": {
                    "received_plan": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 1.0, "y": 0.0},
                    ],
                },
                "scan": {
                    "ok": True,
                    "raw": {
                        "range_min": 0.05,
                        "range_max": 5.0,
                        "samples": [
                            {"angle": 0.0, "range": 1.0},
                            {"angle": 1.57, "range": 0.5},
                        ],
                    },
                    "transform": {"x": 0.0, "y": 0.0, "yaw": 0.0},
                    "stamp": 123.0,
                    "frame_id": "laser",
                },
                "status": {"slam_ok": True},
            }
        )

        self.assertEqual(payload["map_version"], 7)
        self.assertEqual(len(payload["scan"]["points"]), 2)
        self.assertEqual(payload["paths"]["a_star"][1]["x"], 1.0)
        self.assertAlmostEqual(payload["nearest_obstacle_ahead"]["x"], 1.0)
        self.assertAlmostEqual(payload["nearest_obstacle_ahead"]["dist"], 1.0)

    def test_finds_lidar_point_near_qr_bearing(self):
        point = find_nearest_obstacle_at_bearing(
            {"ok": True, "x": 0.0, "y": 0.0, "theta": 0.0},
            [
                {"x": 1.0, "y": 0.5},
                {"x": 1.2, "y": -0.1},
                {"x": 0.3, "y": 1.0},
            ],
            bearing_rad=0.0,
            half_fov_rad=0.12,
        )

        self.assertIsNotNone(point)
        assert point is not None
        self.assertAlmostEqual(point["x"], 1.2)
        self.assertAlmostEqual(point["dist"], math.hypot(1.2, -0.1))

    @patch("control.services.qr_detect.ROSClient")
    def test_enrich_detection_result_with_lidar_replaces_range_values(self, ros_client_cls):
        ros_client = ros_client_cls.return_value
        ros_client.get_slam_state_for_ui.return_value = {
            "pose": {"ok": True, "x": 0.0, "y": 0.0, "theta": 0.0},
            "scan": {
                "ok": True,
                "points": [
                    {"x": 0.4, "y": 0.1},
                    {"x": 1.2, "y": 0.0},
                ],
            },
        }

        result = DetectionResult(
            ok=True,
            items=[
                QRItem(
                    text="QR-A",
                    qr_type="QRCODE",
                    angle_deg=0.0,
                    angle_rad=0.0,
                    distance_m=0.45,
                    lateral_x_m=0.0,
                    forward_z_m=0.45,
                    target_x_m=0.0,
                    target_z_m=0.8,
                    target_distance_m=0.8,
                    direction="center",
                    center_px=(100, 100),
                    corners=[[0, 0], [1, 0], [1, 1], [0, 1]],
                ),
            ],
        )

        enriched = enrich_detection_result_with_lidar("robot-qr", result)
        item = enriched.items[0]

        self.assertAlmostEqual(item.camera_distance_m, 0.45)
        self.assertAlmostEqual(item.lidar_distance_m, 1.2)
        self.assertAlmostEqual(item.distance_m, 1.2)
        self.assertAlmostEqual(item.forward_z_m, 1.2)
        self.assertAlmostEqual(item.lateral_x_m, 0.0)
        self.assertAlmostEqual(item.target_distance_m, 1.55)


class ROSClientStateSelectionTests(SimpleTestCase):
    @patch("control.services.ros.build_slam_ui_state", return_value={"ok": True})
    @patch.object(ROSClient, "get_slam_state")
    @patch.object(ROSClient, "get_slam_state_light")
    def test_uses_full_state_when_scan_points_requested(
        self,
        get_slam_state_light,
        get_slam_state,
        build_state,
    ):
        get_slam_state.return_value = {"scan": {"ok": True, "points": [{"x": 1.0, "y": 0.0}]}}
        client = ROSClient("robot-a")

        payload = client.get_slam_state_for_ui(include_scan_points=True)

        self.assertEqual(payload, {"ok": True})
        get_slam_state.assert_called_once_with()
        get_slam_state_light.assert_not_called()
        build_state.assert_called_once()
        self.assertIs(build_state.call_args.args[0], get_slam_state.return_value)
        self.assertTrue(build_state.call_args.kwargs["include_scan_points"])

    @patch("control.services.ros.build_slam_ui_state", return_value={"ok": True})
    @patch.object(ROSClient, "get_slam_state")
    @patch.object(ROSClient, "get_slam_state_light")
    def test_uses_light_state_when_scan_points_not_requested(
        self,
        get_slam_state_light,
        get_slam_state,
        build_state,
    ):
        get_slam_state_light.return_value = {"status": {"slam_ok": True}}
        client = ROSClient("robot-a")

        payload = client.get_slam_state_for_ui(include_scan_points=False)

        self.assertEqual(payload, {"ok": True})
        get_slam_state_light.assert_called_once_with()
        get_slam_state.assert_not_called()
        build_state.assert_called_once()
        self.assertIs(build_state.call_args.args[0], get_slam_state_light.return_value)
        self.assertFalse(build_state.call_args.kwargs["include_scan_points"])


class PointFromObstacleViewTests(TestCase):
    @patch("control.views.ROSClient")
    def test_derives_yaw_from_robot_pose_when_not_provided(self, ros_client_cls):
        ros_client = ros_client_cls.return_value
        ros_client.get_slam_state_for_ui.return_value = {
            "pose": {"ok": True, "x": 1.0, "y": 1.0},
            "nearest_obstacle_ahead": {"x": 1.0, "y": 2.0, "dist": 1.0},
        }
        ros_client.create_point.return_value = {"success": True, "message": "OK"}

        response = self.client.post(
            "/control/api/robots/robot-a/points/from-obstacle/",
            data=json.dumps({"name": "QR-A", "qr_detected": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        ros_client.create_point.assert_called_once()
        _, kwargs = ros_client.create_point.call_args
        self.assertEqual(kwargs["name"], "QR-A")
        self.assertAlmostEqual(kwargs["x"], 1.0)
        self.assertAlmostEqual(kwargs["y"], 2.0)
        self.assertAlmostEqual(kwargs["yaw"], math.pi / 2, places=5)

    @patch("control.views.ROSClient")
    def test_rejects_save_when_qr_is_not_detected_and_logs_event(self, ros_client_cls):
        ros_client = ros_client_cls.return_value

        response = self.client.post(
            "/control/api/robots/robot-a/points/from-obstacle/",
            data=json.dumps({"name": "POINT", "qr_detected": False}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["reason"], "qr_not_detected")
        ros_client.create_point.assert_not_called()
        self.assertEqual(
            ActionEvent.objects.filter(robot_id="robot-a", event="qr_point_save", status=ActionEvent.Status.FAILED).count(),
            1,
        )


class TextCommandMetricTests(TestCase):
    @patch("control.views.execute_mcp_tool")
    @patch("control.views.map_text_with_openrouter")
    def test_persists_voice_conversation_metric_on_success(self, map_text_mock, execute_tool_mock):
        map_text_mock.return_value = {
            "actions": [
                {
                    "tool": "play_behavior",
                    "arguments": {"name": "Swing"},
                }
            ],
            "reply_text": "Em đã nhận lệnh.",
        }
        execute_tool_mock.return_value = {
            "tool": "play_behavior",
            "arguments": {"name": "Swing"},
            "status": "ok",
        }

        response = self.client.post(
            "/control/api/robots/robot-voice/command/text/",
            data=json.dumps({"addr": "192.168.1.10", "text": "high Swing"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(VoiceConversationMetric.objects.filter(robot_id="robot-voice").count(), 1)

        row = VoiceConversationMetric.objects.get(robot_id="robot-voice")
        self.assertEqual(row.input_text, "high Swing")
        self.assertEqual(row.robot_addr, "192.168.1.10")
        self.assertEqual(row.planner_source, "openrouter")
        self.assertTrue(row.success)
        self.assertFalse(row.dry_run)
        self.assertGreaterEqual(row.response_time_ms or 0.0, 0.0)
        self.assertIn("Swing", row.reply_text)
        self.assertEqual(row.result_json["tool"], "play_behavior")
        self.assertEqual(row.plan_json["actions"][0]["tool"], "play_behavior")
        self.assertIn("reply_text", row.response_json)


class SessionSummaryTests(TestCase):
    def test_counts_only_today_obstacle_events_for_robot(self):
        robot, _ = Robot.objects.get_or_create(id="robot-a", defaults={"name": "Robot A"})
        other_robot = Robot.objects.create(id="robot-b", name="Robot B")

        today_event = ActionEvent.objects.create(
            robot=robot,
            event="obstacle_detected",
            severity=ActionEvent.Severity.WARNING,
            status=ActionEvent.Status.ACTIVE,
        )
        old_event = ActionEvent.objects.create(
            robot=robot,
            event="obstacle_detected",
            severity=ActionEvent.Severity.WARNING,
            status=ActionEvent.Status.ACTIVE,
        )
        ActionEvent.objects.create(
            robot=robot,
            event="Lidar Start",
            severity=ActionEvent.Severity.INFO,
            status=ActionEvent.Status.SUCCESS,
        )
        ActionEvent.objects.create(
            robot=other_robot,
            event="obstacle_detected",
            severity=ActionEvent.Severity.WARNING,
            status=ActionEvent.Status.ACTIVE,
        )

        ActionEvent.objects.filter(pk=old_event.pk).update(timestamp=timezone.now() - timedelta(days=1))

        response = self.client.get("/control/api/robots/robot-a/session/summary/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["obstacle_events_today"], 1)
        self.assertEqual(response.data["robot_id"], "robot-a")

    def test_action_events_keep_only_latest_twenty_per_robot(self):
        robot = Robot.objects.create(id="robot-events-prune", name="Robot Events")

        for i in range(25):
            ActionEvent.objects.create(
                robot=robot,
                event=f"event-{i:02d}",
                severity=ActionEvent.Severity.INFO,
                status=ActionEvent.Status.SUCCESS,
            )

        events = list(
            ActionEvent.objects.filter(robot=robot).order_by("timestamp", "id")
        )
        self.assertEqual(len(events), 20)
        self.assertEqual(events[0].event, "event-05")
        self.assertEqual(events[-1].event, "event-24")


class MetricFallbackTests(TestCase):
    def test_status_uses_local_metric_system_when_robot_is_not_connected(self):
        robot = Robot.objects.create(id="robot-metric", name="Metric Robot")
        MetricSystem.objects.create(
            robot=robot,
            cpu=42.0,
            battery=77.0,
            temperature=36.5,
            ram=61.0,
        )

        with patch("control.views.ROSClient.get_status", return_value={}):
            response = self.client.get("/control/api/robots/robot-metric/status/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["robot_connected"])
        self.assertEqual(response.data["battery"], 77.0)
        self.assertEqual(response.data["metric_system_latest"]["battery"], 77.0)
        self.assertEqual(response.data["telemetry"]["battery"], 77.0)
        self.assertEqual(response.data["telemetry"]["system"]["cpu_percent"], 42.0)
        self.assertEqual(response.data["telemetry"]["system"]["temperature"], 36.5)
        self.assertEqual(response.data["telemetry"]["system"]["ram"], "61.0%")

    def test_metric_system_keeps_only_latest_fifty_samples(self):
        robot = Robot.objects.create(id="robot-metric-prune", name="Metric Prune")

        for i in range(55):
            MetricSystem.objects.create(
                robot=robot,
                cpu=float(i),
                battery=80.0,
                temperature=30.0,
                ram=40.0,
            )

        rows = list(MetricSystem.objects.order_by("created_at", "id"))
        self.assertEqual(len(rows), 50)
        self.assertEqual(rows[0].cpu, 5.0)
        self.assertEqual(rows[-1].cpu, 54.0)


class QRLocalizationMetricTests(TestCase):
    def test_creates_manual_metric_with_errors(self):
        body = {
            "label": "QR-A",
            "trial": "angle_10",
            "ground_truth": {
                "distance_m": 1.0,
                "angle_deg": 10.0,
                "x": 2.0,
                "y": 3.0,
            },
            "estimate": {
                "detected": True,
                "qr_text": "A",
                "distance_m": 1.08,
                "lidar_distance_m": 1.08,
                "angle_deg": 13.0,
                "x": 2.1,
                "y": 3.2,
            },
            "nav": {
                "goal_x": 2.0,
                "goal_y": 3.0,
                "stop_x": 2.3,
                "stop_y": 3.4,
            },
            "processing_time_ms": 31.5,
            "qr_detect_time_ms": 18.2,
            "docker_save_time_ms": 44.0,
        }

        row = create_qr_localization_metric("robot-qr-metric", body)

        self.assertEqual(row.label, "QR-A")
        self.assertTrue(row.detected)
        self.assertAlmostEqual(row.distance_error_m, 0.08)
        self.assertAlmostEqual(row.angle_error_deg, 3.0)
        self.assertAlmostEqual(row.qr_world_error_m, math.hypot(0.1, 0.2))
        self.assertAlmostEqual(row.nav_error_m, 0.5)
        self.assertAlmostEqual(row.qr_detect_time_ms, 18.2)
        self.assertAlmostEqual(row.docker_save_time_ms, 44.0)

    def test_qr_localization_metric_api_persists_row(self):
        response = self.client.post(
            "/control/api/robots/robot-qr-api/metrics/qr-localization/",
            data=json.dumps(
                {
                    "label": "QR-B",
                    "ground_truth": {"distance_m": 0.8, "angle_deg": 0},
                    "estimate": {
                        "detected": True,
                        "distance_m": 0.7,
                        "lidar_distance_m": 0.7,
                        "angle_deg": -2,
                    },
                    "qr_detect_time_ms": 12.0,
                    "docker_save_time_ms": 30.0,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(QRLocalizationMetric.objects.filter(robot_id="robot-qr-api").count(), 1)
        self.assertAlmostEqual(response.data["data"]["distance"]["error_m"], 0.1)
        self.assertAlmostEqual(response.data["data"]["timing"]["qr_detect_time_ms"], 12.0)
        self.assertAlmostEqual(response.data["data"]["timing"]["docker_save_time_ms"], 30.0)

    def test_qr_localization_metric_api_filters_by_date(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        today_row = create_qr_localization_metric(
            "robot-qr-api",
            {
                "label": "QR-TODAY",
                "estimate": {"detected": True, "distance_m": 0.9, "angle_deg": 1.0},
            },
        )
        yesterday_row = create_qr_localization_metric(
            "robot-qr-api",
            {
                "label": "QR-YESTERDAY",
                "estimate": {"detected": False},
            },
        )

        QRLocalizationMetric.objects.filter(id=today_row.id).update(
            created_at=timezone.make_aware(datetime.combine(today, datetime.min.time()))
        )
        QRLocalizationMetric.objects.filter(id=yesterday_row.id).update(
            created_at=timezone.make_aware(datetime.combine(yesterday, datetime.min.time()))
        )

        today_response = self.client.get(
            "/control/api/robots/robot-qr-api/metrics/qr-localization/?date=today"
        )
        self.assertEqual(today_response.status_code, 200)
        self.assertEqual(today_response.data["summary"]["total"], 1)
        self.assertEqual(today_response.data["summary"]["detected"], 1)
        self.assertAlmostEqual(today_response.data["summary"]["success_rate_pct"], 100.0)
        self.assertEqual(len(today_response.data["items"]), 1)

        all_response = self.client.get(
            "/control/api/robots/robot-qr-api/metrics/qr-localization/?date=all"
        )
        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(all_response.data["summary"]["total"], 2)
        self.assertEqual(all_response.data["summary"]["detected"], 1)
        self.assertAlmostEqual(all_response.data["summary"]["success_rate_pct"], 50.0)
        self.assertEqual(len(all_response.data["items"]), 2)

        custom_response = self.client.get(
            f"/control/api/robots/robot-qr-api/metrics/qr-localization/?date={today.isoformat()}"
        )
        self.assertEqual(custom_response.status_code, 200)
        self.assertEqual(custom_response.data["summary"]["total"], 1)
        self.assertEqual(custom_response.data["summary"]["detected"], 1)
        self.assertAlmostEqual(custom_response.data["summary"]["success_rate_pct"], 100.0)

    @patch("control.services.qr_localization_metrics.ROSClient")
    def test_metric_can_measure_docker_point_save(self, ros_client_cls):
        ros_client = ros_client_cls.return_value
        ros_client.create_point.return_value = {"success": True}

        row = create_qr_localization_metric(
            "robot-qr-save",
            {
                "label": "QR-SAVE",
                "estimate": {"detected": True, "x": 1.0, "y": 2.0},
                "save_point": {
                    "enabled": True,
                    "name": "QR-SAVE",
                    "x": 1.0,
                    "y": 2.0,
                    "yaw": 0.5,
                },
            },
        )

        ros_client.create_point.assert_called_once_with(
            name="QR-SAVE",
            x=1.0,
            y=2.0,
            yaw=0.5,
        )
        self.assertTrue(row.docker_save_success)
        self.assertIsNotNone(row.docker_save_time_ms)
        self.assertGreaterEqual(row.docker_save_time_ms, 0.0)


class PatrolHistoryTests(TestCase):
    def test_persists_patrol_history_to_database(self):
        mission = PatrolMission(
            mission_id="patrol_test123",
            robot_id="robot-history",
            route_name="test_route",
            points=["A", "B"],
            status="DONE",
            current_index=1,
            started_at=100.0,
            finished_at=120.0,
            total_distance_m=12.34,
        )
        mission.results.append(
            PatrolPointResult(
                point="A",
                status="SUCCESS",
                attempts=1,
                started_at=101.0,
                finished_at=110.0,
                reach_time_sec=9.0,
                distance_on_finish=0.2,
                message="reached",
            )
        )

        append_history("robot-history", mission)

        history = get_history("robot-history")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].mission_id, "patrol_test123")
        self.assertEqual(history[0].status, "DONE")
        self.assertEqual(history[0].total_distance_m, 12.34)
        self.assertEqual(history[0].results[0].point, "A")
        self.assertEqual(history[0].results[0].status, "SUCCESS")

        from .models import PatrolHistory

        record = PatrolHistory.objects.get(mission_id="patrol_test123")
        self.assertEqual(record.total_distance_m, 12.34)

    def test_all_history_is_not_limited_to_today(self):
        old_mission = PatrolMission(
            mission_id="patrol_old",
            robot_id="robot-history-all",
            route_name="old_route",
            points=["A"],
            status="DONE",
            started_at=100.0,
            finished_at=120.0,
        )
        today_ts = datetime.combine(datetime.today().date(), datetime.min.time()).timestamp()
        today_mission = PatrolMission(
            mission_id="patrol_today",
            robot_id="robot-history-all",
            route_name="today_route",
            points=["B"],
            status="DONE",
            started_at=today_ts,
            finished_at=today_ts + 10,
        )

        append_history("robot-history-all", old_mission)
        append_history("robot-history-all", today_mission)

        self.assertEqual(len(get_history("robot-history-all", "all")), 2)
        self.assertEqual(len(get_history("robot-history-all", "today")), 1)

        response = self.client.get("/control/api/robots/robot-history-all/patrol/history/?date=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["history"]), 2)

    def test_history_accepts_string_timestamps_and_custom_date_filter(self):
        mission = PatrolMission(
            mission_id="patrol_string_time",
            robot_id="robot-history-string",
            route_name="string_route",
            points=["A"],
            status="DONE",
            started_at=100.0,
            finished_at=120.0,
        )
        append_history("robot-history-string", mission)

        from .models import PatrolHistory
        from django.db import connection

        record = PatrolHistory.objects.get(mission_id="patrol_string_time")
        payload = record.payload
        payload["started_at"] = "2026-05-08 11:06:07"
        payload["finished_at"] = "2026-05-08 11:08:07"
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE control_patrolhistory
                SET started_at = %s, finished_at = %s, payload = %s
                WHERE id = %s
                """,
                [
                    "2026-05-08 11:06:07",
                    "2026-05-08 11:08:07",
                    json.dumps(payload),
                    record.pk,
                ],
            )

        history = get_history("robot-history-string", "2026-05-08")

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].mission_id, "patrol_string_time")
        self.assertIsInstance(history[0].started_at, float)

    def test_records_docker_ui_goal_in_patrol_history(self):
        response = self.client.post(
            "/control/api/robots/robot-docker-ui/patrol/ui-action/",
            data=json.dumps(
                {
                    "action": "goal",
                    "x": 1.25,
                    "y": -0.5,
                    "yaw": 0.75,
                    "u": 120,
                    "v": 80,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["mission"]["status"], "completed")

        history = get_history("robot-docker-ui", "all")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].route_name, "manual_map_goal")
        self.assertEqual(history[0].status, "DONE")
        self.assertEqual(history[0].results[0].status, "SUCCESS")

        from .models import PatrolHistory

        record = PatrolHistory.objects.get(mission_id=history[0].mission_id)
        self.assertEqual(record.route_name, "manual_map_goal")

    def test_records_docker_ui_initial_pose_in_patrol_history(self):
        response = self.client.post(
            "/control/api/robots/robot-docker-ui-init/patrol/ui-action/",
            data=json.dumps(
                {
                    "action": "initial_pose",
                    "x": -1.0,
                    "y": 2.5,
                    "yaw": 1.57,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        history = get_history("robot-docker-ui-init", "all")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].route_name, "docker_ui_initial_pose")
        self.assertEqual(history[0].points[0], "INITPOSE(-1.000,2.500)")


class PatrolManagerStopTests(TestCase):
    def test_saved_point_uses_go_to_point_api(self):
        manager = PatrolManager()
        manager.poll_interval_sec = 0.01
        manager.point_timeout_sec = 0.2

        mission = PatrolMission(
            mission_id="patrol_goal_pose_test",
            robot_id="robot-goal",
            route_name="point_A",
            points=["A"],
            wait_sec_per_point=0,
            max_retry_per_point=0,
            skip_on_fail=False,
            status="RUNNING",
        )

        class FakeROSClient:
            def __init__(self, robot_id: str) -> None:
                self.robot_id = robot_id
                self.go_to_point_calls: list[str] = []

            def get_points(self):
                return {"A": {"x": 2.0, "y": 1.0, "yaw": 0.0}}

            def get_navigation_metrics(self):
                return {"missions": []}

            def go_to_point(self, name: str):
                self.go_to_point_calls.append(name)
                return {"success": True, "message": "OK"}

            def get_slam_state_light(self):
                if self.go_to_point_calls:
                    return {"pose": {"ok": True, "x": 2.0, "y": 1.0, "theta": 0.0}}
                return {"pose": {"ok": True, "x": 0.0, "y": 0.0, "theta": 0.0}}

        fake_client = FakeROSClient(mission.robot_id)

        with patch("control.services.patrol_manager.ROSClient", return_value=fake_client):
            manager._run_patrol(mission)

        self.assertEqual(fake_client.go_to_point_calls, ["A"])
        self.assertEqual(mission.status, "DONE")
        self.assertEqual(mission.results[0].status, "SUCCESS")

    def test_stop_during_single_point_marks_stopped_without_retry(self):
        manager = PatrolManager()
        manager.poll_interval_sec = 0.01
        manager.point_timeout_sec = 1.0

        mission = PatrolMission(
            mission_id="patrol_stop_test",
            robot_id="robot-stop",
            route_name="point_A",
            points=["A"],
            wait_sec_per_point=0,
            max_retry_per_point=1,
            skip_on_fail=True,
            status="RUNNING",
        )
        manager._stop_flags[mission.robot_id] = False

        class FakeROSClient:
            def __init__(self, robot_id: str) -> None:
                self.robot_id = robot_id
                self.go_to_point_calls: list[str] = []

            def get_points(self):
                return {"A": {"x": 1.0, "y": 1.0, "yaw": 0.0}}

            def get_navigation_metrics(self):
                return {"missions": []}

            def go_to_point(self, name: str):
                self.go_to_point_calls.append(name)
                manager._stop_flags[mission.robot_id] = True
                return {"success": True}

            def get_slam_state_light(self):
                return {"pose": {"ok": True, "x": 0.0, "y": 0.0, "theta": 0.0}}

        fake_client = FakeROSClient(mission.robot_id)

        with patch("control.services.patrol_manager.ROSClient", return_value=fake_client):
            manager._run_patrol(mission)

        self.assertEqual(fake_client.go_to_point_calls, ["A"])
        self.assertEqual(mission.status, "STOPPED")
        self.assertEqual(mission.results[0].status, "ABORTED")
        self.assertEqual(mission.results[0].message, "mission stopped")


class PatrolDistancePersistenceTests(TestCase):
    def test_manual_goal_persists_total_distance_to_patrol_history(self):
        manager = PatrolManager()
        manager.poll_interval_sec = 0.01
        manager.point_timeout_sec = 0.2

        mission = PatrolMission(
            mission_id="manual_distance_test",
            robot_id="robot-distance",
            route_name="manual_goal_test",
            points=["GOAL(1.000,2.000)"],
            wait_sec_per_point=0,
            max_retry_per_point=0,
            skip_on_fail=False,
            status="RUNNING",
        )

        class FakeROSClient:
            def __init__(self, robot_id: str) -> None:
                self.robot_id = robot_id
                self.goal_calls: list[tuple[float, float, float]] = []

            def get_navigation_metrics(self):
                return {"missions": []}

            def set_goal_pose(self, x: float, y: float, yaw: float):
                self.goal_calls.append((x, y, yaw))
                return {"success": True, "message": "OK"}

            def get_slam_state_light(self):
                if self.goal_calls:
                    x, y, yaw = self.goal_calls[-1]
                    return {"pose": {"ok": True, "x": x, "y": y, "theta": yaw}}
                return {"pose": {"ok": True, "x": 0.0, "y": 0.0, "theta": 0.0}}

            def get_distance_metrics(self):
                return {"total_m": 7.89, "duration_sec": 12.3}

        fake_client = FakeROSClient(mission.robot_id)

        with patch("control.services.patrol_manager.ROSClient", return_value=fake_client):
            manager._run_manual_goal(mission, 1.0, 2.0, 0.0)

        from .models import PatrolHistory

        record = PatrolHistory.objects.get(mission_id="manual_distance_test")
        self.assertEqual(record.total_distance_m, 7.89)
        self.assertEqual(record.payload.get("total_distance_m"), 7.89)
        self.assertEqual(mission.total_distance_m, 7.89)


