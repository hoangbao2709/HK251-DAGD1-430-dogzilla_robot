import uuid

from django.db import models

class Robot(models.Model):
    id = models.CharField(primary_key=True, max_length=64) 
    name = models.CharField(max_length=128, default="Robot A")
    addr = models.CharField(max_length=256, blank=True, default="")  

    location_lat = models.FloatField(null=True, blank=True)
    location_lon = models.FloatField(null=True, blank=True)
    cleaning_progress = models.FloatField(default=0)
    floor = models.CharField(max_length=16, default="1st")
    status_text = models.CharField(max_length=64, default="Resting")
    water_level = models.IntegerField(default=50)
    battery = models.IntegerField(default=85)
    fps = models.IntegerField(default=30)

    def __str__(self): return self.name


class ActionEvent(models.Model):
    class Severity(models.TextChoices):
        INFO = "Info", "Info"
        WARNING = "Warning", "Warning"
        CRITICAL = "Critical", "Critical"

    class Status(models.TextChoices):
        SUCCESS = "Success", "Success"
        FAILED = "Failed", "Failed"
        ACTIVE = "Active", "Active"

    id = models.CharField(primary_key=True, max_length=32, editable=False)
    robot = models.ForeignKey(Robot, on_delete=models.CASCADE, related_name="events")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    event = models.CharField(max_length=128)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.INFO)
    duration_seconds = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUCCESS)
    action = models.CharField(max_length=64, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    detail = models.TextField(blank=True, default="")

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = f"evt-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.robot_id} {self.event}"
