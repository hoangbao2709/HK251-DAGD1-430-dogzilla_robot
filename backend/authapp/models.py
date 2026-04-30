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


class RobotDevice(models.Model):
    STATUS_CHOICES = (
        ("online", "Online"),
        ("offline", "Offline"),
        ("unknown", "Unknown"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="robot_devices",
    )
    name = models.CharField(max_length=128, default="Robot")
    ip = models.CharField(max_length=255)
    url = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="unknown",
    )
    battery = models.IntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "ip")

    def __str__(self):
        return f"{self.name} - {self.ip}"