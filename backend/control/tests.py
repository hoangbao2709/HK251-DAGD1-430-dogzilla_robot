import json
import math
from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings
from django.utils import timezone

from .models import ActionEvent, Robot
from .services.patrol_manager import PatrolManager
from .services.patrol_store import append_history, get_history
from .services.patrol_types import PatrolMission, PatrolPointResult
from .services.ros import ROSClient
from .services.slam_payload import build_slam_ui_state


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
            data=json.dumps({"name": "QR-A"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        ros_client.create_point.assert_called_once()
        _, kwargs = ros_client.create_point.call_args
        self.assertEqual(kwargs["name"], "QR-A")
        self.assertAlmostEqual(kwargs["x"], 1.0)
        self.assertAlmostEqual(kwargs["y"], 2.0)
        self.assertAlmostEqual(kwargs["yaw"], math.pi / 2, places=5)


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


class XiaozhiBridgeViewTests(TestCase):
    @override_settings(
        XIAOZHI_BRIDGE_TOKEN="bridge-secret",
        XIAOZHI_DEFAULT_ROBOT_ID="robot-default",
        XIAOZHI_DEFAULT_ROBOT_ADDR="http://127.0.0.1:9000",
    )
    def test_requires_bridge_token(self):
        response = self.client.post(
            "/control/api/xiaozhi/command/",
            data=json.dumps({"text": "bat tay"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.data["success"])

    @override_settings(
        XIAOZHI_BRIDGE_TOKEN="bridge-secret",
        XIAOZHI_DEFAULT_ROBOT_ID="robot-default",
        XIAOZHI_DEFAULT_ROBOT_ADDR="http://127.0.0.1:9000",
    )
    @patch("control.views.process_text_command")
    def test_uses_defaults_and_executes_command(self, process_text_command_mock):
        process_text_command_mock.return_value = {
            "ok": True,
            "robot_addr": "http://127.0.0.1:9000",
            "tool": "play_behavior",
            "arguments": {"name": "Handshake"},
            "mapping": {"matched_phrase": "bat tay"},
            "content": {"success": True},
        }

        response = self.client.post(
            "/control/api/xiaozhi/command/",
            data=json.dumps({"text": "bat tay", "robot_addr": "http://127.0.0.1:9000"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer bridge-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["robot_id"], "robot-default")
        self.assertEqual(response.data["robot_addr"], "http://127.0.0.1:9000")
        self.assertEqual(
            response.data["reply_text"],
            "Em đã nhận lệnh. Robot đang thực hiện động tác Handshake.",
        )
        process_text_command_mock.assert_called_once_with(
            robot_addr="http://127.0.0.1:9000",
            text="bat tay",
        )

    @override_settings(
        XIAOZHI_BRIDGE_TOKEN="bridge-secret",
        XIAOZHI_DEFAULT_ROBOT_ID="robot-default",
        XIAOZHI_DEFAULT_ROBOT_ADDR="http://127.0.0.1:9000",
    )
    def test_dry_run_maps_without_execution(self):
        response = self.client.post(
            "/control/api/xiaozhi/command/",
            data=json.dumps({"text": "di toi diem a", "dry_run": True}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer bridge-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertTrue(response.data["dry_run"])
        self.assertEqual(response.data["result"]["tool"], "go_to_point")
        self.assertEqual(response.data["result"]["arguments"]["name"], "A")

    @override_settings(
        XIAOZHI_BRIDGE_TOKEN="bridge-secret",
        XIAOZHI_DEFAULT_ROBOT_ID="robot-default",
        XIAOZHI_DEFAULT_ROBOT_ADDR="http://127.0.0.1:9000",
    )
    @patch("control.views.patrol_manager.start")
    def test_single_navigation_voice_command_uses_patrol_manager(self, patrol_start_mock):
        mission = PatrolMission(
            mission_id="voice_point_test",
            robot_id="robot-default",
            route_name="voice_point_A",
            points=["A"],
            wait_sec_per_point=0,
            max_retry_per_point=1,
            skip_on_fail=True,
            status="RUNNING",
        )
        patrol_start_mock.return_value = mission

        response = self.client.post(
            "/control/api/xiaozhi/command/",
            data=json.dumps({"text": "di toi diem a", "robot_addr": "http://127.0.0.1:9000"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer bridge-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["result"]["tool"], "go_to_point")
        patrol_start_mock.assert_called_once_with(
            robot_id="robot-default",
            route_name="voice_point_A",
            points=["A"],
            wait_sec_per_point=0,
        )

    @override_settings(
        XIAOZHI_BRIDGE_TOKEN="bridge-secret",
        XIAOZHI_DEFAULT_ROBOT_ID="robot-default",
        XIAOZHI_DEFAULT_ROBOT_ADDR="",
    )
    @patch("control.views.process_text_command")
    def test_falls_back_to_stored_robot_addr(self, process_text_command_mock):
        Robot.objects.update_or_create(
            id="robot-default",
            defaults={"name": "Robot Default", "addr": "http://192.168.1.50:9000"},
        )
        process_text_command_mock.return_value = {
            "ok": True,
            "robot_addr": "http://192.168.1.50:9000",
            "tool": "play_behavior",
            "arguments": {"name": "Handshake"},
            "mapping": {"matched_phrase": "bat tay"},
            "content": {"success": True},
        }

        response = self.client.post(
            "/control/api/xiaozhi/command/",
            data=json.dumps({"text": "bat tay", "robot_id": "robot-default"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer bridge-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["robot_addr"], "http://192.168.1.50:9000")
        process_text_command_mock.assert_called_once_with(
            robot_addr="http://192.168.1.50:9000",
            text="bat tay",
        )
