from django.contrib import admin

from .models import UserProfile


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
