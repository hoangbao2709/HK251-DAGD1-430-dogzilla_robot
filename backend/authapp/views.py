from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile


def _get_profile(user: User) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    username = request.data.get("username")
    email = request.data.get("email")
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

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "Username already taken"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(email=email).exists():
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
    profile.password_plaintext = password
    profile.password_hash = user.password
    profile.save(update_fields=["password_plaintext", "password_hash"])

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "ok": True,
            "message": "Registered successfully",
            "email": user.email,
            "username": user.username,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response(
            {"error": "Email and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not user.check_password(password):
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    profile = _get_profile(user)
    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "ok": True,
            "email": user.email,
            "username": user.username,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "robot_url": profile.robot_url or None,
            "robot_device_id": profile.robot_device_id or None,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_user_url(request):
    url = request.data.get("url")

    if not url:
        return Response(
            {"error": "url is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    profile = _get_profile(request.user)
    profile.url = url
    profile.updated_at = timezone.now()
    profile.save(update_fields=["url", "updated_at"])

    return Response(
        {"ok": True, "message": "URL saved"},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def link_robot(request):
    secret = request.headers.get("X-Robot-Secret")
    if secret != settings.ROBOT_REG_SECRET:
        return Response(
            {"detail": "Forbidden"},
            status=status.HTTP_403_FORBIDDEN,
        )

    email = request.data.get("email")
    url = request.data.get("url")
    device_id = request.data.get("device_id")

    if not email or not url or not device_id:
        return Response(
            {"detail": "email, url, device_id are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(
            {"detail": "User not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    profile = _get_profile(user)
    profile.robot_url = url
    profile.robot_device_id = device_id
    profile.robot_updated_at = timezone.now()
    profile.save(update_fields=["robot_url", "robot_device_id", "robot_updated_at"])

    return Response({"ok": True}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def me_view(request):
    jwt_auth = JWTAuthentication()
    try:
        auth_result = jwt_auth.authenticate(request)
    except AuthenticationFailed as e:
        return Response(
            {"detail": e.detail},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if auth_result is None:
        return Response(
            {"detail": "No authentication credentials found"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    user, _validated_token = auth_result
    profile = _get_profile(user)

    return Response(
        {
            "ok": True,
            "email": user.email,
            "username": user.username,
            "robot_url": profile.robot_url or None,
            "robot_device_id": profile.robot_device_id or None,
            "robot_updated_at": profile.robot_updated_at,
        },
        status=status.HTTP_200_OK,
    )
