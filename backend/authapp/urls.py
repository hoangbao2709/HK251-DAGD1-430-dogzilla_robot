from django.urls import path
from .views import (
    login_view,
    register_view,
    me_view,
    robots_view,
    robot_detail_view,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("register/", register_view, name="register"),
    path("me/", me_view, name="me"),

    path("robots/", robots_view, name="robots"),
    path("robots/<int:robot_id>/", robot_detail_view, name="robot-detail"),
]