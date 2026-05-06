from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0002_actionevent"),
    ]

    operations = [
        migrations.CreateModel(
            name="PatrolHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mission_id", models.CharField(db_index=True, max_length=64, unique=True)),
                ("route_name", models.CharField(blank=True, default="", max_length=128)),
                ("status", models.CharField(db_index=True, max_length=32)),
                ("started_at", models.FloatField(db_index=True)),
                ("finished_at", models.FloatField(blank=True, db_index=True, null=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "robot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="patrol_history",
                        to="control.robot",
                    ),
                ),
            ],
            options={
                "ordering": ["-finished_at", "-started_at"],
            },
        ),
    ]
