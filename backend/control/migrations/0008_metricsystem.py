from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0007_alter_actionevent_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="MetricSystem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("cpu", models.FloatField(blank=True, null=True)),
                ("battery", models.FloatField(blank=True, null=True)),
                ("temperature", models.FloatField(blank=True, null=True)),
                ("ram", models.FloatField(blank=True, null=True)),
            ],
            options={
                "db_table": "metric_system",
            },
        ),
    ]