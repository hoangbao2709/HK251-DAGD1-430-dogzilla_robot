from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0008_metricsystem"),
    ]

    operations = [
        migrations.AddField(
            model_name="metricsystem",
            name="robot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="system_metrics",
                to="control.robot",
            ),
        ),
        migrations.AddField(
            model_name="metricsystem",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                db_index=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name="metricsystem",
            options={"ordering": ["-created_at"]},
        ),
    ]
