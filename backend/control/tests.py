from django.test import SimpleTestCase

from .services.evaluation_metrics import build_evaluation_metrics_payload


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
