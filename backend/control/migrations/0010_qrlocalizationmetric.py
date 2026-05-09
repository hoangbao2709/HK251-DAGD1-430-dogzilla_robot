from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0009_metricsystem_robot_created_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="QRLocalizationMetric",
            fields=[
                ("id", models.CharField(editable=False, max_length=40, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("label", models.CharField(blank=True, default="", max_length=128)),
                ("trial_name", models.CharField(blank=True, default="", max_length=128)),
                ("source", models.CharField(blank=True, default="manual", max_length=64)),
                ("detected", models.BooleanField(default=False)),
                ("qr_text", models.CharField(blank=True, default="", max_length=256)),
                ("distance_gt_m", models.FloatField(blank=True, null=True)),
                ("distance_est_m", models.FloatField(blank=True, null=True)),
                ("distance_error_m", models.FloatField(blank=True, null=True)),
                ("angle_gt_deg", models.FloatField(blank=True, null=True)),
                ("angle_est_deg", models.FloatField(blank=True, null=True)),
                ("angle_error_deg", models.FloatField(blank=True, null=True)),
                ("qr_world_gt_x", models.FloatField(blank=True, null=True)),
                ("qr_world_gt_y", models.FloatField(blank=True, null=True)),
                ("qr_world_est_x", models.FloatField(blank=True, null=True)),
                ("qr_world_est_y", models.FloatField(blank=True, null=True)),
                ("qr_world_error_m", models.FloatField(blank=True, null=True)),
                ("nav_goal_x", models.FloatField(blank=True, null=True)),
                ("nav_goal_y", models.FloatField(blank=True, null=True)),
                ("nav_stop_x", models.FloatField(blank=True, null=True)),
                ("nav_stop_y", models.FloatField(blank=True, null=True)),
                ("nav_error_m", models.FloatField(blank=True, null=True)),
                ("robot_pose_x", models.FloatField(blank=True, null=True)),
                ("robot_pose_y", models.FloatField(blank=True, null=True)),
                ("robot_pose_theta", models.FloatField(blank=True, null=True)),
                ("qr_lateral_x_m", models.FloatField(blank=True, null=True)),
                ("qr_forward_z_m", models.FloatField(blank=True, null=True)),
                ("processing_time_ms", models.FloatField(blank=True, null=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "robot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="qr_localization_metrics",
                        to="control.robot",
                    ),
                ),
            ],
            options={
                "db_table": "qr_localization_metric",
                "ordering": ["-created_at"],
            },
        ),
    ]
