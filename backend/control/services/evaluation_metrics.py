import math
from typing import Any


def _safe_round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _present(value: Any) -> bool:
    return value is not None


def _compute_from_trajectory(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    points = [
        (
            float(item["t"]),
            float(item["x"]),
            float(item["y"]),
            float(item["theta"]),
        )
        for item in trajectory
        if item.get("ok") is True
    ]

    if not points:
        return {
            "trajectory_samples": 0,
            "trajectory_window_sec": None,
            "sample_rate_hz": None,
            "path_length_m": None,
            "mean_speed_mps": None,
            "max_instant_speed_mps": None,
            "mean_step_m": None,
            "max_step_m": None,
            "net_displacement_m": None,
            "final_drift_from_origin_m": None,
            "origin_position_rmse_m": None,
            "origin_position_mae_m": None,
            "mean_heading_abs_deg": None,
            "final_heading_abs_deg": None,
            "std_x_m": None,
            "std_y_m": None,
            "std_theta_deg": None,
            "bbox_x_m": None,
            "bbox_y_m": None,
        }

    xs = [x for _, x, _, _ in points]
    ys = [y for _, _, y, _ in points]
    thetas = [theta for _, _, _, theta in points]

    dts: list[float] = []
    distances: list[float] = []
    for previous, current in zip(points, points[1:]):
        dt = current[0] - previous[0]
        if dt <= 0:
            continue
        dts.append(dt)
        distances.append(math.hypot(current[1] - previous[1], current[2] - previous[2]))

    trajectory_window_sec = points[-1][0] - points[0][0] if len(points) > 1 else 0.0
    sample_rate_hz = (1.0 / (sum(dts) / len(dts))) if dts else None
    path_length_m = sum(distances) if distances else 0.0
    mean_speed_mps = (path_length_m / trajectory_window_sec) if trajectory_window_sec > 0 else None
    max_instant_speed_mps = (
        max(distance / dt for distance, dt in zip(distances, dts)) if dts and distances else None
    )

    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    mean_theta = sum(thetas) / len(thetas)

    std_x_m = (sum((x - mean_x) ** 2 for x in xs) / len(xs)) ** 0.5
    std_y_m = (sum((y - mean_y) ** 2 for y in ys) / len(ys)) ** 0.5
    std_theta_deg = math.degrees((sum((theta - mean_theta) ** 2 for theta in thetas) / len(thetas)) ** 0.5)

    origin_distances = [math.hypot(x, y) for x, y in zip(xs, ys)]
    origin_position_rmse_m = (sum(distance**2 for distance in origin_distances) / len(origin_distances)) ** 0.5
    origin_position_mae_m = sum(origin_distances) / len(origin_distances)

    return {
        "trajectory_samples": len(points),
        "trajectory_window_sec": _safe_round(trajectory_window_sec, 3),
        "sample_rate_hz": _safe_round(sample_rate_hz, 2),
        "path_length_m": _safe_round(path_length_m, 4),
        "mean_speed_mps": _safe_round(mean_speed_mps, 4),
        "max_instant_speed_mps": _safe_round(max_instant_speed_mps, 4),
        "mean_step_m": _safe_round((sum(distances) / len(distances)) if distances else 0.0, 5),
        "max_step_m": _safe_round(max(distances) if distances else 0.0, 5),
        "net_displacement_m": _safe_round(
            math.hypot(points[-1][1] - points[0][1], points[-1][2] - points[0][2]),
            4,
        ),
        "final_drift_from_origin_m": _safe_round(math.hypot(points[-1][1], points[-1][2]), 4),
        "origin_position_rmse_m": _safe_round(origin_position_rmse_m, 4),
        "origin_position_mae_m": _safe_round(origin_position_mae_m, 4),
        "mean_heading_abs_deg": _safe_round(
            sum(abs(math.degrees(theta)) for theta in thetas) / len(thetas),
            3,
        ),
        "final_heading_abs_deg": _safe_round(abs(math.degrees(points[-1][3])), 3),
        "std_x_m": _safe_round(std_x_m, 5),
        "std_y_m": _safe_round(std_y_m, 5),
        "std_theta_deg": _safe_round(std_theta_deg, 3),
        "bbox_x_m": [_safe_round(min(xs), 4), _safe_round(max(xs), 4)],
        "bbox_y_m": [_safe_round(min(ys), 4), _safe_round(max(ys), 4)],
    }


def compute_path_efficiency(raw_metrics: dict[str, Any]) -> float | None:
    """
    Estimate path efficiency as straight-line distance over actual path length.
    """
    trajectory = raw_metrics.get("trajectory") or []
    path_length_m = raw_metrics.get("path_length_m")

    if path_length_m is None:
        path_length_m = _compute_from_trajectory(trajectory).get("path_length_m")

    try:
        path_length = float(path_length_m)
    except (TypeError, ValueError):
        return None

    if path_length <= 0:
        return None

    points = [item for item in trajectory if isinstance(item, dict)]
    if len(points) < 2:
        return None

    start = points[0]
    end = points[-1]

    try:
        dx = float(end.get("x", 0)) - float(start.get("x", 0))
        dy = float(end.get("y", 0)) - float(start.get("y", 0))
    except (TypeError, ValueError):
        return None

    optimal_distance = math.hypot(dx, dy)
    if optimal_distance <= 0:
        return None

    return min(100.0, round((optimal_distance / path_length) * 100, 1))


def build_evaluation_metrics_payload(raw_metrics: dict[str, Any]) -> dict[str, Any]:
    trajectory_metrics = _compute_from_trajectory(raw_metrics.get("trajectory") or [])
    trajectory_metrics["path_efficiency_pct"] = compute_path_efficiency(
        {
            **raw_metrics,
            "path_length_m": trajectory_metrics.get("path_length_m"),
        }
    )
    summary = raw_metrics.get("summary") or {}
    run_meta = raw_metrics.get("run_meta") or {}
    reference_metrics = raw_metrics.get("reference_metrics") or {}
    qr_stats = raw_metrics.get("qr_stats") or {}
    payload_mode = raw_metrics.get("payload_mode") or {}
    missions = raw_metrics.get("missions") or []
    run_started_at = raw_metrics.get("run_started_at")

    exact_localization = all(
        _present(reference_metrics.get(key))
        for key in ("position_rmse_m", "position_mae_m", "final_drift_m")
    ) and any(
        _present(reference_metrics.get(key))
        for key in ("heading_error_final_deg", "heading_error_mean_deg")
    )

    exact_qr_ablation = (
        _present(raw_metrics.get("condition") or run_meta.get("condition"))
        and _present(raw_metrics.get("weighting_mode") or run_meta.get("weighting_mode"))
        and all(
            _present(qr_stats.get(key))
            for key in ("detection_count", "accept_count", "reject_count", "false_correction_count")
        )
    )

    exact_navigation = all(
        _present(summary.get(key))
        for key in ("success_rate", "mean_time_to_goal_sec", "mean_path_deviation_m", "mean_intervention_count")
    ) or any(
        all(
            _present(mission.get(key))
            for key in (
                "duration_sec",
                "intervention_count",
                "mean_path_deviation_m",
                "max_path_deviation_m",
                "final_goal_error_m",
            )
        )
        for mission in missions
    )

    table_i = {
        "rmse_m": reference_metrics.get("position_rmse_m"),
        "mean_m": reference_metrics.get("position_mae_m"),
        "drift_m": reference_metrics.get("final_drift_m"),
        "head_err_deg": reference_metrics.get("heading_error_final_deg")
        or reference_metrics.get("heading_error_mean_deg"),
        "rmse_m_proxy": trajectory_metrics["origin_position_rmse_m"],
        "mean_m_proxy": trajectory_metrics["origin_position_mae_m"],
        "drift_m_proxy": trajectory_metrics["final_drift_from_origin_m"],
        "head_err_deg_proxy": trajectory_metrics["final_heading_abs_deg"],
        "exact": exact_localization,
        "note": "Exact metrics use reference_metrics when available; proxy metrics are origin-referenced.",
    }

    table_ii = {
        "condition": run_meta.get("condition") or raw_metrics.get("condition"),
        "weighting_mode": run_meta.get("weighting_mode") or raw_metrics.get("weighting_mode"),
        "qr_detection_count": qr_stats.get("detection_count"),
        "qr_accept_count": qr_stats.get("accept_count"),
        "qr_reject_count": qr_stats.get("reject_count"),
        "false_correction_count": qr_stats.get("false_correction_count"),
        "mean_distance_m": qr_stats.get("mean_distance_m"),
        "mean_view_angle_deg": qr_stats.get("mean_view_angle_deg"),
        "occlusion_ratio": qr_stats.get("occlusion_ratio"),
        "blur_score": qr_stats.get("blur_score"),
        "exact": exact_qr_ablation,
        "supported": any(qr_stats.values()),
    }

    table_iii = {
        "success_rate": summary.get("success_rate"),
        "mean_time_to_goal_sec": summary.get("mean_time_to_goal_sec"),
        "mean_path_deviation_m": summary.get("mean_path_deviation_m"),
        "mean_intervention_count": summary.get("mean_intervention_count"),
        "planner_replan_count": (raw_metrics.get("planner_stats") or {}).get("replan_count"),
        "exact": exact_navigation,
        "supported": bool(missions),
    }

    reasons: list[str] = []
    if exact_localization:
        reasons.append("exact_localization")
    if exact_qr_ablation:
        reasons.append("exact_qr_ablation")
    if exact_navigation:
        reasons.append("exact_navigation")
    if not reasons:
        reasons.append("no_exact_metrics")

    return {
        "run_meta": {
            "method": raw_metrics.get("method") or run_meta.get("method"),
            "route_id": raw_metrics.get("route_id") or run_meta.get("route_id"),
            "trial_id": raw_metrics.get("trial_id") or run_meta.get("trial_id"),
            "condition": raw_metrics.get("condition") or run_meta.get("condition"),
            "weighting_mode": raw_metrics.get("weighting_mode") or run_meta.get("weighting_mode"),
        },
        "payload_mode": payload_mode,
        "summary": {
            "run_duration_sec": summary.get("run_duration_sec"),
            "trajectory_samples": summary.get("trajectory_samples"),
            "mission_count": summary.get("mission_count"),
            "completed_missions": summary.get("completed_missions"),
            "failed_or_aborted_missions": summary.get("failed_or_aborted_missions"),
        },
        "derived_metrics": trajectory_metrics,
        "paper_tables": {
            "table_i_localization": table_i,
            "table_ii_qr_ablation": table_ii,
            "table_iii_navigation": table_iii,
        },
        "persistence": {
            "eligible": _present(run_started_at) and (exact_localization or exact_qr_ablation or exact_navigation),
            "reasons": reasons,
        },
        "raw_metrics": raw_metrics,
    }


def build_snapshot_key(robot_id: str, raw_metrics: dict[str, Any], payload: dict[str, Any]) -> str:
    run_meta = payload.get("run_meta") or {}
    run_started_at = raw_metrics.get("run_started_at")
    return "|".join(
        [
            robot_id,
            str(run_started_at),
            str(run_meta.get("method") or "-"),
            str(run_meta.get("route_id") or "-"),
            str(run_meta.get("trial_id") or "-"),
            str(run_meta.get("condition") or "-"),
            str(run_meta.get("weighting_mode") or "-"),
        ]
    )
