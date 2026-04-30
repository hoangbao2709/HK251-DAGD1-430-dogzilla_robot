from django.contrib.auth.models import User
from django.db.models import Q
from urllib.parse import urlparse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserProfile, RobotDevice


def _get_profile(user: User) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def _normalize_robot_addr(robot_ip: str, robot_url: str = "") -> tuple[str, str]:
    raw_url = str(robot_url or "").strip()
    raw_ip = str(robot_ip or "").strip()
    candidate = raw_url or raw_ip

    if not candidate:
        return "", ""

    if "://" not in candidate:
        candidate_url = f"http://{candidate.rstrip('/')}"
    else:
        candidate_url = candidate.rstrip("/")

    parsed = urlparse(candidate_url)
    host = parsed.hostname or raw_ip
    if not host:
        return "", ""

    port = parsed.port
    scheme = parsed.scheme or "http"
    netloc = f"{host}:{port}" if port else host
    normalized_url = f"{scheme}://{netloc}"

    if not port and raw_url:
        normalized_url = f"{scheme}://{host}:9000"
    elif not port and raw_ip and ":" not in raw_ip:
        normalized_url = f"{scheme}://{host}:9000"

    return host, normalized_url.rstrip("/")


def _remember_robot_for_login(request, user: User, robot_ip: str, robot_url: str = ""):
    ip, url = _normalize_robot_addr(robot_ip, robot_url)
    if not ip:
        return None

    request.session["robot_ip"] = ip
    request.session["robot_url"] = url

    profile = _get_profile(user)
    profile.robot_url = url
    profile.robot_device_id = ip
    profile.save(update_fields=["robot_url", "robot_device_id"])

    robot, _created = RobotDevice.objects.update_or_create(
        user=user,
        ip=ip,
        defaults={
            "name": "Robot",
            "url": url,
            "status": "unknown",
            "battery": 100,
        },
    )
    return robot


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    username = str(request.data.get("username") or "").strip()
    email = User.objects.normalize_email(str(request.data.get("email") or "").strip()).lower()
    password = request.data.get("password")

    if not username or not email or not password:
        return Response(
            {"error": "Username, email and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(password) < 6:
        return Response(
            {"error": "Password must be at least 6 characters"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(username__iexact=username).exists():
        return Response(
            {"error": "Username already taken"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(email__iexact=email).exists():
        return Response(
            {"error": "Email already registered"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
    )
    profile = _get_profile(user)
    profile.password_plaintext = ""
    profile.password_hash = user.password
    profile.save(update_fields=["password_plaintext", "password_hash"])

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "ok": True,
            "message": "Registered successfully",
            "email": user.email,
            "username": user.username,
            "authenticated": True,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    identifier = str(
        request.data.get("identifier")
        or request.data.get("email")
        or request.data.get("username")
        or ""
    ).strip()
    password = request.data.get("password")
    robot_ip = str(
        request.data.get("robot_ip")
        or request.data.get("ip")
        or ""
    ).strip()
    robot_url = str(
        request.data.get("robot_url")
        or request.data.get("url")
        or request.data.get("robot_addr")
        or ""
    ).strip()

    if not identifier or not password:
        return Response(
            {"error": "Email/username and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.filter(
        Q(email__iexact=identifier) | Q(username__iexact=identifier)
    ).first()

    if user is None:
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.check_password(password):
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    robot = _remember_robot_for_login(request, user, robot_ip, robot_url)
    refresh = RefreshToken.for_user(user)
    data = {
        "ok": True,
        "email": user.email,
        "username": user.username,
        "authenticated": True,
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }
    if robot is not None:
        data.update(
            {
                "robot_ip": robot.ip,
                "robot_url": robot.url,
                "robot_device_id": robot.id,
            }
        )

    return Response(data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def me_view(request):
    jwt_auth = JWTAuthentication()
    try:
        auth_result = jwt_auth.authenticate(request)
    except AuthenticationFailed as e:
        auth_result = None

    if auth_result is None:
        return Response(
            {
                "ok": True,
                "authenticated": False,
                "email": None,
                "username": "Guest",
            },
            status=status.HTTP_200_OK,
        )

    user, _validated_token = auth_result

    return Response(
        {
            "ok": True,
            "authenticated": True,
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "robot_ip": request.session.get("robot_ip") or "",
            "robot_url": request.session.get("robot_url") or "",
        },
        status=status.HTTP_200_OK,
    )
def _authenticate_user(request):
    jwt_auth = JWTAuthentication()

    try:
        auth_result = jwt_auth.authenticate(request)
    except AuthenticationFailed:
        auth_result = None

    if auth_result is None:
        return None

    user, _validated_token = auth_result
    return user


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def robots_view(request):
    user = _authenticate_user(request)

    if user is None:
        return Response(
            {"error": "Authentication required"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if request.method == "GET":
        robots = RobotDevice.objects.filter(user=user).order_by("-updated_at")

        data = [
            {
                "id": robot.id,
                "name": robot.name,
                "ip": robot.ip,
                "url": robot.url,
                "status": robot.status,
                "battery": robot.battery,
            }
            for robot in robots
        ]

        return Response(data, status=status.HTTP_200_OK)

    name = str(request.data.get("name") or "Robot").strip()
    ip = str(request.data.get("ip") or "").strip()
    url = str(request.data.get("url") or "").strip()
    robot_status = str(request.data.get("status") or "unknown").strip()
    battery = request.data.get("battery") or 100

    if not ip:
        return Response(
            {"error": "Robot IP is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    robot, _created = RobotDevice.objects.update_or_create(
        user=user,
        ip=ip,
        defaults={
            "name": name,
            "url": url,
            "status": robot_status,
            "battery": battery,
        },
    )

    return Response(
        {
            "id": robot.id,
            "name": robot.name,
            "ip": robot.ip,
            "url": robot.url,
            "status": robot.status,
            "battery": robot.battery,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([AllowAny])
def robot_detail_view(request, robot_id):
    user = _authenticate_user(request)

    if user is None:
        return Response(
            {"error": "Authentication required"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        robot = RobotDevice.objects.get(id=robot_id, user=user)
    except RobotDevice.DoesNotExist:
        return Response(
            {"error": "Robot not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    robot.delete()

    return Response({"ok": True}, status=status.HTTP_200_OK)
