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

    def __str__(self):
        return self.name


class ActionEvent(models.Model):
    MAX_EVENTS_PER_ROBOT = 20

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
        self.prune_for_robot(self.robot_id)

    @classmethod
    def prune_for_robot(cls, robot_id: str, keep: int | None = None) -> int:
        limit = keep or cls.MAX_EVENTS_PER_ROBOT
        if limit <= 0:
            deleted, _ = cls.objects.filter(robot_id=robot_id).delete()
            return deleted

        keep_ids = list(
            cls.objects.filter(robot_id=robot_id)
            .order_by("-timestamp", "-id")
            .values_list("id", flat=True)[:limit]
        )
        if not keep_ids:
            return 0

        deleted, _ = cls.objects.filter(robot_id=robot_id).exclude(id__in=keep_ids).delete()
        return deleted

    def __str__(self) -> str:
        return f"{self.robot_id} {self.event}"


class PatrolHistory(models.Model):
    mission_id = models.CharField(max_length=64, unique=True, db_index=True)
    robot = models.ForeignKey(
        Robot,
        on_delete=models.CASCADE,
        related_name="patrol_history",
    )
    route_name = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=32, db_index=True)

    started_at = models.FloatField(db_index=True)
    finished_at = models.FloatField(null=True, blank=True, db_index=True)

    total_distance_m = models.FloatField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    cpu_samples = models.JSONField(default=list, blank=True)
    battery_samples = models.JSONField(default=list, blank=True)
    temperature_samples = models.JSONField(default=list, blank=True)
    ram_samples = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-finished_at", "-started_at"]

    def __str__(self) -> str:
        return f"{self.robot_id} {self.mission_id} {self.status}"
class MetricSystem(models.Model):
    MAX_SAMPLES = 50

    robot = models.ForeignKey(
        Robot,
        on_delete=models.CASCADE,
        related_name="system_metrics",
        null=True,
        blank=True,
    )
    cpu = models.FloatField(null=True, blank=True)
    battery = models.FloatField(null=True, blank=True)
    temperature = models.FloatField(null=True, blank=True)
    ram = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "metric_system"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"CPU={self.cpu}, Battery={self.battery}, Temp={self.temperature}, RAM={self.ram}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.prune_samples()

    @classmethod
    def prune_samples(cls, keep: int | None = None) -> int:
        limit = keep or cls.MAX_SAMPLES
        if limit <= 0:
            deleted, _ = cls.objects.all().delete()
            return deleted

        keep_ids = list(
            cls.objects.order_by("-created_at", "-id").values_list("id", flat=True)[:limit]
        )
        if not keep_ids:
            return 0

        deleted, _ = cls.objects.exclude(id__in=keep_ids).delete()
        return deleted


class QRLocalizationMetric(models.Model):
    id = models.CharField(primary_key=True, max_length=40, editable=False)
    robot = models.ForeignKey(
        Robot,
        on_delete=models.CASCADE,
        related_name="qr_localization_metrics",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    label = models.CharField(max_length=128, blank=True, default="")
    trial_name = models.CharField(max_length=128, blank=True, default="")
    source = models.CharField(max_length=64, blank=True, default="manual")

    detected = models.BooleanField(default=False)
    qr_text = models.CharField(max_length=256, blank=True, default="")

    distance_gt_m = models.FloatField(null=True, blank=True)
    distance_est_m = models.FloatField(null=True, blank=True)
    distance_error_m = models.FloatField(null=True, blank=True)
    distance_source = models.CharField(max_length=32, blank=True, default="")
    camera_distance_est_m = models.FloatField(null=True, blank=True)
    lidar_distance_est_m = models.FloatField(null=True, blank=True)

    angle_gt_deg = models.FloatField(null=True, blank=True)
    angle_est_deg = models.FloatField(null=True, blank=True)
    angle_error_deg = models.FloatField(null=True, blank=True)

    qr_world_gt_x = models.FloatField(null=True, blank=True)
    qr_world_gt_y = models.FloatField(null=True, blank=True)
    qr_world_est_x = models.FloatField(null=True, blank=True)
    qr_world_est_y = models.FloatField(null=True, blank=True)
    qr_world_error_m = models.FloatField(null=True, blank=True)

    nav_goal_x = models.FloatField(null=True, blank=True)
    nav_goal_y = models.FloatField(null=True, blank=True)
    nav_stop_x = models.FloatField(null=True, blank=True)
    nav_stop_y = models.FloatField(null=True, blank=True)
    nav_error_m = models.FloatField(null=True, blank=True)

    robot_pose_x = models.FloatField(null=True, blank=True)
    robot_pose_y = models.FloatField(null=True, blank=True)
    robot_pose_theta = models.FloatField(null=True, blank=True)
    qr_lateral_x_m = models.FloatField(null=True, blank=True)
    qr_forward_z_m = models.FloatField(null=True, blank=True)

    processing_time_ms = models.FloatField(null=True, blank=True)
    qr_detect_time_ms = models.FloatField(null=True, blank=True)
    docker_save_time_ms = models.FloatField(null=True, blank=True)
    docker_save_success = models.BooleanField(null=True, blank=True)
    docker_save_error = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "qr_localization_metric"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = f"qrmet-{uuid.uuid4().hex[:12]}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.robot_id} {self.qr_text or self.label} {self.created_at}"


class VoiceConversationMetric(models.Model):
    id = models.CharField(primary_key=True, max_length=40, editable=False)
    robot = models.ForeignKey(
        Robot,
        on_delete=models.CASCADE,
        related_name="voice_conversation_metrics",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    input_text = models.TextField(blank=True, default="")
    robot_addr = models.CharField(max_length=256, blank=True, default="")
    planner_source = models.CharField(max_length=64, blank=True, default="")
    success = models.BooleanField(default=False)
    dry_run = models.BooleanField(default=False)
    response_time_ms = models.FloatField(null=True, blank=True)

    reply_text = models.TextField(blank=True, default="")
    llm_error = models.TextField(blank=True, default="")
    error_code = models.CharField(max_length=64, blank=True, default="")

    plan_json = models.JSONField(default=dict, blank=True)
    result_json = models.JSONField(null=True, blank=True)
    results_json = models.JSONField(default=list, blank=True)
    response_json = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "voice_conversation_metric"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = f"voicem-{uuid.uuid4().hex[:12]}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.robot_id} {self.input_text[:32]} {self.created_at}"
