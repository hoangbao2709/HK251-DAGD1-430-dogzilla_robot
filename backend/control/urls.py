from django.urls import path
from .views import (
    RobotListView,
    ConnectView,
    RobotStatusView,
    FPVView,
    SpeedModeView,
    MoveCommandView,
    PostureView,
    BehaviorView,
    LidarView,
    BodyAdjustView,
    StabilizingModeView,
    CameraProcessView,
    TextCommandView,
    QRStateView,
    QRPositionView,
    QRVideoFeedView,
    SlamStateView,
    SlamMapView,
    PointsView,
    DeletePointView,
    GoToPointView,
    GoToMarkerView,
)

urlpatterns = [
    path("api/robots/", RobotListView.as_view(), name="robots-list"),
    path("api/robots/<str:robot_id>/connect/", ConnectView.as_view(), name="robot-connect"),
    path("api/robots/<str:robot_id>/status/", RobotStatusView.as_view(), name="robot-status"),
    path("api/robots/<str:robot_id>/fpv/", FPVView.as_view(), name="robot-fpv"),
    path("api/robots/<str:robot_id>/camera/", CameraProcessView.as_view(), name="robot-camera"),

    path("api/robots/<str:robot_id>/command/move/", MoveCommandView.as_view(), name="robot-move"),
    path("api/robots/<str:robot_id>/command/speed/", SpeedModeView.as_view(), name="robot-speed"),
    path("api/robots/<str:robot_id>/command/posture/", PostureView.as_view(), name="robot-posture"),
    path("api/robots/<str:robot_id>/command/behavior/", BehaviorView.as_view(), name="robot-behavior"),
    path("api/robots/<str:robot_id>/command/lidar/", LidarView.as_view(), name="robot-lidar"),
    path("api/robots/<str:robot_id>/command/body_adjust/", BodyAdjustView.as_view(), name="robot-body-adjust"),
    path(
        "api/robots/<str:robot_id>/command/stabilizing_mode/",
        StabilizingModeView.as_view(),
        name="robot-stabilizing-mode",
    ),
    path("api/robots/<str:robot_id>/command/text/", TextCommandView.as_view(), name="robot-text-command"),

    path("api/robots/<str:robot_id>/qr/state/", QRStateView.as_view(), name="robot-qr-state"),
    path("api/robots/<str:robot_id>/qr/position/", QRPositionView.as_view(), name="robot-qr-position"),
    path("api/robots/<str:robot_id>/qr/video-feed/", QRVideoFeedView.as_view(), name="robot-qr-video-feed"),

    path("api/robots/<str:robot_id>/slam/state/", SlamStateView.as_view(), name="robot-slam-state"),
    path("api/robots/<str:robot_id>/slam/map.png", SlamMapView.as_view(), name="robot-slam-map"),

    path("api/robots/<str:robot_id>/points/", PointsView.as_view(), name="robot-points"),
    path("api/robots/<str:robot_id>/delete-point/", DeletePointView.as_view(), name="robot-delete-point"),
    path("api/robots/<str:robot_id>/go-to-point/", GoToPointView.as_view(), name="robot-go-to-point"),
    path("api/robots/<str:robot_id>/go-to-marker/", GoToMarkerView.as_view(), name="robot-go-to-marker"),
]