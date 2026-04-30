from django.contrib import admin

from .models import UserProfile, RobotDevice


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "url",
        "robot_url",
        "robot_device_id",
        "password_plaintext",
        "password_hash",
        "updated_at",
        "robot_updated_at",
    )
    search_fields = ("user__username", "user__email", "robot_device_id")


@admin.register(RobotDevice)
class RobotDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "name",
        "ip",
        "url",
        "status",
        "battery",
        "updated_at",
    )
    search_fields = ("user__username", "user__email", "name", "ip", "url")
    list_filter = ("status",)