from django.urls import path
from .views import (
    RobotListView, RobotStatusView, ConnectView, FPVView,
    MoveCommandView, SpeedModeView, PostureView, BehaviorView,
    LidarView, BodyAdjustView, StabilizingModeView, CameraProcessView,
    TextCommandView
)

urlpatterns = [

    path('api/robots/', RobotListView.as_view(), name='robots-list'),
    path('api/robots/<str:robot_id>/connect/', ConnectView.as_view(), name='robot-connect'),
    path('api/robots/<str:robot_id>/status/', RobotStatusView.as_view(), name='robot-status'),
    path('api/robots/<str:robot_id>/fpv/', FPVView.as_view(), name='robot-fpv'),


    path('api/robots/<str:robot_id>/command/move/', MoveCommandView.as_view(), name='robot-move'),
    path('api/robots/<str:robot_id>/command/speed/', SpeedModeView.as_view(), name='robot-speed'),
    path('api/robots/<str:robot_id>/command/posture/', PostureView.as_view(), name='robot-posture'),
    path('api/robots/<str:robot_id>/command/behavior/', BehaviorView.as_view(), name='robot-behavior'),
    path('api/robots/<str:robot_id>/command/lidar/', LidarView.as_view(), name='robot-lidar'),
    path('api/robots/<str:robot_id>/command/body_adjust/', BodyAdjustView.as_view(), name='robot-body'),
    path("api/robots/<str:robot_id>/command/stabilizing_mode/", StabilizingModeView.as_view(),name="stabilizing_mode", ),

    path('api/robots/<str:robot_id>/camera/', CameraProcessView.as_view(), name='robot-camera'),
    
    path('api/robots/<str:robot_id>/command/text/', TextCommandView.as_view(), name='robot-text-command'),
]
