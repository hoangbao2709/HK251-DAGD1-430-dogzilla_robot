from django.db import migrations


def prune_metric_system(apps, schema_editor):
    MetricSystem = apps.get_model("control", "MetricSystem")
    keep_ids = list(
        MetricSystem.objects.order_by("-created_at", "-id")
        .values_list("id", flat=True)[:50]
    )
    if keep_ids:
        MetricSystem.objects.exclude(id__in=keep_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0013_prune_actionevent"),
    ]

    operations = [
        migrations.RunPython(prune_metric_system, migrations.RunPython.noop),
    ]
