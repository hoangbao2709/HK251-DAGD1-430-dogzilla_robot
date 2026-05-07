from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0005_patrolhistory_total_distance_m"),
    ]

    operations = [
        migrations.AddField(
            model_name="patrolhistory",
            name="cpu_samples",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="patrolhistory",
            name="battery_samples",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="patrolhistory",
            name="temperature_samples",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="patrolhistory",
            name="ram_samples",
            field=models.JSONField(blank=True, default=list),
        ),
    ]