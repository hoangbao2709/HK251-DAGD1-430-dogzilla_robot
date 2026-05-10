from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0010_qrlocalizationmetric"),
    ]

    operations = [
        migrations.AddField(
            model_name="qrlocalizationmetric",
            name="qr_detect_time_ms",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="qrlocalizationmetric",
            name="docker_save_time_ms",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="qrlocalizationmetric",
            name="docker_save_success",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="qrlocalizationmetric",
            name="docker_save_error",
            field=models.TextField(blank=True, default=""),
        ),
    ]
