from urllib.parse import urlparse

from .models import Robot


def _extract_host(value: str) -> str:
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""

    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    return (parsed.hostname or "").strip().lower()


def resolve_robot(robot_ref: str) -> Robot | None:
    ref = (robot_ref or "").strip()
    if not ref:
        return None

    robot = Robot.objects.filter(pk=ref).first()
    if robot is not None:
        return robot

    normalized_ref = ref.rstrip("/").lower()
    robot = Robot.objects.filter(addr__iexact=normalized_ref).first()
    if robot is not None:
        return robot

    host = _extract_host(ref)
    if not host:
        return None

    for candidate in Robot.objects.exclude(addr=""):
        if _extract_host(candidate.addr) == host:
            return candidate

    return None


def get_or_create_robot(robot_ref: str) -> Robot:
    robot = resolve_robot(robot_ref)
    if robot is not None:
        return robot

    robot, _ = Robot.objects.get_or_create(
        pk=robot_ref,
        defaults={
            "name": robot_ref.replace("-", " ").title(),
        },
    )
    return robot
