from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    url = models.CharField(max_length=512, blank=True, default="")
    robot_url = models.CharField(max_length=512, blank=True, default="")
    robot_device_id = models.CharField(max_length=128, blank=True, default="")
    password_plaintext = models.CharField(max_length=255, blank=True, default="")
    password_hash = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(null=True, blank=True)
    robot_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.user.username} profile"
