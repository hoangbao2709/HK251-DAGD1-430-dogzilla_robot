from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0004_patrolhistory"),
    ]

    operations = [
        migrations.AddField(
            model_name="patrolhistory",
            name="total_distance_m",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
