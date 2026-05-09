from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from typing import Any

from django.db import close_old_connections

from ..models import MetricSystem, Robot
from .ros import ROSClient

logger = logging.getLogger(__name__)

_system_sampler_started = False
_system_sampler_lock = threading.Lock()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _extract_temperature(status: dict[str, Any]) -> float | None:
    candidates = [
        status.get("temperature"),
        status.get("temp"),
        status.get("cpu_temp"),
        status.get("system", {}).get("temperature") if isinstance(status.get("system"), dict) else None,
        status.get("system", {}).get("temp") if isinstance(status.get("system"), dict) else None,
        status.get("system", {}).get("cpu_temp") if isinstance(status.get("system"), dict) else None,
    ]
    for value in candidates:
        parsed = _as_float(value)
        if parsed is not None:
            return parsed
    return None


def collect_robot_metrics(robot_id: str) -> dict[str, float | None]:
    status = ROSClient(robot_id).get_status() or {}
    telemetry = status.get("telemetry") if isinstance(status.get("telemetry"), dict) else {}
    system = status.get("system") if isinstance(status.get("system"), dict) else {}
    telemetry_system = telemetry.get("system") if isinstance(telemetry.get("system"), dict) else {}

    return {
        "cpu": _as_float(
            system.get("cpu_percent")
            or telemetry_system.get("cpu_percent")
            or status.get("cpu")
            or status.get("cpu_percent")
        ),
        "battery": _as_float(
            status.get("battery")
            or telemetry.get("battery")
            or status.get("battery_percent")
        ),
        "temperature": _extract_temperature(status),
        "ram": _as_float(
            system.get("ram")
            or telemetry_system.get("ram")
            or status.get("ram")
            or status.get("memory")
        ),
    }


def sample_for_patrol(robot_id: str) -> dict[str, dict[str, float | None]]:
    ts = time.time()
    metrics = collect_robot_metrics(robot_id)
    return {
        "cpu": {"ts": ts, "value": metrics["cpu"]},
        "battery": {"ts": ts, "value": metrics["battery"]},
        "temperature": {"ts": ts, "value": metrics["temperature"]},
        "ram": {"ts": ts, "value": metrics["ram"]},
    }


def append_patrol_sample(mission: Any) -> None:
    sample = sample_for_patrol(mission.robot_id)
    mission.cpu_samples.append(sample["cpu"])
    mission.battery_samples.append(sample["battery"])
    mission.temperature_samples.append(sample["temperature"])
    mission.ram_samples.append(sample["ram"])


def _robot_ids_to_sample() -> list[str]:
    ids = list(Robot.objects.exclude(addr="").values_list("id", flat=True))
    if ids:
        return ids
    return ["robot-a"]


def _system_sampler_loop(interval_seconds: float) -> None:
    while True:
        try:
            close_old_connections()
            for robot_id in _robot_ids_to_sample():
                try:
                    robot, _ = Robot.objects.get_or_create(
                        pk=robot_id,
                        defaults={"name": robot_id.replace("-", " ").title()},
                    )
                    metrics = collect_robot_metrics(robot_id)
                    MetricSystem.objects.create(robot=robot, **metrics)
                except Exception as exc:
                    logger.warning("MetricSystem sample failed for %s: %s", robot_id, exc)
        finally:
            close_old_connections()
        time.sleep(interval_seconds)


def start_system_metric_sampler(interval_seconds: float = 30.0) -> None:
    global _system_sampler_started
    if any(command in sys.argv for command in {"makemigrations", "migrate", "collectstatic", "test"}):
        return
    if os.environ.get("RUN_MAIN") not in {None, "true"}:
        return
    with _system_sampler_lock:
        if _system_sampler_started:
            return
        _system_sampler_started = True
        thread = threading.Thread(
            target=_system_sampler_loop,
            args=(float(interval_seconds),),
            daemon=True,
            name="metric_system_sampler",
        )
        thread.start()
