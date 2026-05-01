import json
import math
from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import ActionEvent, Robot
from .services.evaluation_metrics import build_evaluation_metrics_payload
from .services.patrol_manager import PatrolManager
from .services.patrol_store import append_history, get_history
from .services.patrol_types import PatrolMission, PatrolPointResult
from .services.ros import ROSClient
from .services.slam_payload import build_slam_ui_state


class EvaluationMetricsTests(SimpleTestCase):
    def test_builds_proxy_metrics_from_trajectory(self):
        payload = build_evaluation_metrics_payload(
            {
                "trajectory": [
                    {"t": 1.0, "x": 0.0, "y": 0.0, "theta": 0.0, "ok": True},
                    {"t": 2.0, "x": 1.0, "y": 0.0, "theta": 0.1, "ok": True},
                    {"t": 3.0, "x": 1.0, "y": 1.0, "theta": 0.2, "ok": True},
                ],
                "summary": {"run_duration_sec": 3.0, "trajectory_samples": 3},
            }
        )

        derived = payload["derived_metrics"]
        table_i = payload["paper_tables"]["table_i_localization"]

        self.assertEqual(derived["trajectory_samples"], 3)
        self.assertEqual(derived["sample_rate_hz"], 1.0)
        self.assertEqual(derived["path_length_m"], 2.0)
        self.assertEqual(derived["path_efficiency_pct"], 70.7)
        self.assertEqual(table_i["drift_m_proxy"], 1.4142)
        self.assertFalse(payload["persistence"]["eligible"])

    def test_marks_payload_eligible_when_exact_reference_metrics_exist(self):
        payload = build_evaluation_metrics_payload(
            {
                "run_started_at": 123.0,
                "trajectory": [],
                "reference_metrics": {
                    "position_rmse_m": 0.1,
                    "position_mae_m": 0.08,
                    "final_drift_m": 0.12,
                    "heading_error_final_deg": 1.5,
                },
            }
        )

        self.assertTrue(payload["paper_tables"]["table_i_localization"]["exact"])
        self.assertTrue(payload["persistence"]["eligible"])

    def test_prefers_distance_api_total_for_path_length(self):
        payload = build_evaluation_metrics_payload(
            {
                "trajectory": [
                    {"t": 100.0, "x": 0.0, "y": 0.0, "theta": 0.0, "ok": True},
                    {"t": 101.0, "x": 100.0, "y": 0.0, "theta": 0.0, "ok": True},
                ],
                "distance_metrics": {
                    "total_m": 12.34,
                    "sample_count": 120,
                    "ignored_jump_count": 0,
                    "duration_sec": 23.0,
                    "started_at": 100.0,
                    "last_update": 123.0,
                },
            }
        )

        derived = payload["derived_metrics"]
        self.assertEqual(derived["trajectory_path_length_m"], 100.0)
        self.assertEqual(derived["path_length_m"], 12.34)
        self.assertEqual(derived["path_length_source"], "distance_api")
        self.assertEqual(derived["mean_speed_mps"], 0.5365)
        self.assertEqual(derived["distance_sample_count"], 120)


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
        robot = Robot.objects.create(id="robot-a", name="Robot A")
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
        self.assertEqual(history[0].results[0].point, "A")
        self.assertEqual(history[0].results[0].status, "SUCCESS")


class PatrolManagerStopTests(TestCase):
    def test_saved_point_uses_standoff_goal_pose(self):
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
                self.goal_calls: list[tuple[float, float, float]] = []

            def get_points(self):
                return {"A": {"x": 2.0, "y": 1.0, "yaw": 0.0}}

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

        fake_client = FakeROSClient(mission.robot_id)

        with patch("control.services.patrol_manager.ROSClient", return_value=fake_client):
            manager._run_patrol(mission)

        self.assertEqual(len(fake_client.goal_calls), 1)
        goal_x, goal_y, goal_yaw = fake_client.goal_calls[0]
        self.assertAlmostEqual(goal_x, 2.0 - manager.saved_point_standoff_m)
        self.assertAlmostEqual(goal_y, 1.0)
        self.assertAlmostEqual(goal_yaw, 0.0)
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
                self.goal_calls: list[tuple[float, float, float]] = []

            def get_points(self):
                return {"A": {"x": 1.0, "y": 1.0, "yaw": 0.0}}

            def get_navigation_metrics(self):
                return {"missions": []}

            def set_goal_pose(self, x: float, y: float, yaw: float):
                self.goal_calls.append((x, y, yaw))
                manager._stop_flags[mission.robot_id] = True
                return {"success": True}

            def get_slam_state_light(self):
                return {"pose": {"ok": True, "x": 0.0, "y": 0.0, "theta": 0.0}}

        fake_client = FakeROSClient(mission.robot_id)

        with patch("control.services.patrol_manager.ROSClient", return_value=fake_client):
            manager._run_patrol(mission)

        self.assertEqual(len(fake_client.goal_calls), 1)
        self.assertEqual(mission.status, "STOPPED")
        self.assertEqual(mission.results[0].status, "ABORTED")
        self.assertEqual(mission.results[0].message, "mission stopped")
