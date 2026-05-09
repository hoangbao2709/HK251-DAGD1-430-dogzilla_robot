from django.db import migrations


def prune_action_events(apps, schema_editor):
    ActionEvent = apps.get_model("control", "ActionEvent")
    robot_ids = (
        ActionEvent.objects.order_by()
        .values_list("robot_id", flat=True)
        .distinct()
    )
    for robot_id in robot_ids:
        keep_ids = list(
            ActionEvent.objects.filter(robot_id=robot_id)
            .order_by("-timestamp", "-id")
            .values_list("id", flat=True)[:20]
        )
        if keep_ids:
            ActionEvent.objects.filter(robot_id=robot_id).exclude(id__in=keep_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("control", "0012_qrlocalizationmetric_distance_sources"),
    ]

    operations = [
        migrations.RunPython(prune_action_events, migrations.RunPython.noop),
    ]
