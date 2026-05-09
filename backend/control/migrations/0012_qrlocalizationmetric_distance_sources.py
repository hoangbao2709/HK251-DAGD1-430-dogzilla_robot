from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0011_qrlocalizationmetric_timing"),
    ]

    operations = [
        migrations.AddField(
            model_name="qrlocalizationmetric",
            name="distance_source",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="qrlocalizationmetric",
            name="camera_distance_est_m",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="qrlocalizationmetric",
            name="lidar_distance_est_m",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
