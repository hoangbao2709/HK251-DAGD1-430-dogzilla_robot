from datetime import timedelta
from pathlib import Path
import shutil
import uuid
import zipfile
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .models import ActionEvent, Robot
from .services.evaluation_metrics import build_evaluation_metrics_payload
from .services.patrol_manager import PatrolManager
from .services.patrol_store import append_history, get_history
from .services.patrol_types import PatrolMission, PatrolPointResult
from .services.slam_map_files import find_saved_slam_map_file, save_raw_slam_map_bundle
from .services.slam_map_renderer import render_raw_occupancy_grid_png
from .services.slam_payload import build_slam_ui_state


def _test_map_root() -> Path:
    return Path(settings.BASE_DIR) / f".test_slam_maps_{uuid.uuid4().hex}"


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


class SlamMapRendererTests(SimpleTestCase):
    def test_renders_raw_occupancy_grid_png_on_backend(self):
        raw = bytes([0, 100, 255, 0])
        headers = {
            "X-Map-Version": "1",
            "X-Map-Width": "2",
            "X-Map-Height": "2",
            "X-Map-Resolution": "0.05",
            "X-Map-Origin-X": "0.0",
            "X-Map-Origin-Y": "0.0",
        }

        png = render_raw_occupancy_grid_png(raw, headers, robot_id="test")

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 20)


class SlamMapFileTests(SimpleTestCase):
    def test_saves_raw_map_bundle_on_backend(self):
        raw = bytes([0, 100, 255, 0])
        headers = {
            "X-Map-Version": "1",
            "X-Map-Width": "2",
            "X-Map-Height": "2",
            "X-Map-Resolution": "0.05",
            "X-Map-Origin-X": "-1.0",
            "X-Map-Origin-Y": "-2.0",
            "X-Map-Frame-Id": "map",
        }

        root = _test_map_root()
        root.mkdir(parents=True, exist_ok=True)
        try:
            with override_settings(SLAM_MAP_SAVE_ROOT=root):
                result = save_raw_slam_map_bundle(
                    robot_id="robot-a",
                    name="demo map",
                    raw_data=raw,
                    headers=headers,
                )

                self.assertEqual(result["bundle"], "demo_map.bundle.zip")
                path = find_saved_slam_map_file("robot-a", result["bundle"])
                self.assertIsNotNone(path)
                assert path is not None

                with zipfile.ZipFile(path, "r") as zf:
                    names = set(zf.namelist())
                    self.assertIn("metadata.json", names)
                    self.assertIn("preview.png", names)
                    self.assertIn("demo_map.pgm", names)
                    self.assertIn("demo_map.yaml", names)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class SlamMapFileViewTests(TestCase):
    def test_serves_backend_saved_bundle(self):
        raw = bytes([0, 100, 255, 0])
        headers = {
            "X-Map-Version": "1",
            "X-Map-Width": "2",
            "X-Map-Height": "2",
            "X-Map-Resolution": "0.05",
            "X-Map-Origin-X": "0.0",
            "X-Map-Origin-Y": "0.0",
        }

        root = _test_map_root()
        root.mkdir(parents=True, exist_ok=True)
        try:
            with override_settings(SLAM_MAP_SAVE_ROOT=root):
                result = save_raw_slam_map_bundle(
                    robot_id="robot-a",
                    name="demo",
                    raw_data=raw,
                    headers=headers,
                )

                response = self.client.get(f"/control/api/robots/robot-a/slam/maps/{result['bundle']}")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertTrue(response.content.startswith(b"PK"))


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
                self.go_to_calls: list[str] = []

            def get_points(self):
                return {"A": {"x": 1.0, "y": 1.0}}

            def go_to_point(self, point_name: str):
                self.go_to_calls.append(point_name)
                manager._stop_flags[mission.robot_id] = True
                return {"success": True}

            def get_slam_state_light(self):
                return {"pose": {"ok": True, "x": 0.0, "y": 0.0}}

        fake_client = FakeROSClient(mission.robot_id)

        with patch("control.services.patrol_manager.ROSClient", return_value=fake_client):
            manager._run_patrol(mission)

        self.assertEqual(fake_client.go_to_calls, ["A"])
        self.assertEqual(mission.status, "STOPPED")
        self.assertEqual(mission.results[0].status, "ABORTED")
        self.assertEqual(mission.results[0].message, "mission stopped")
