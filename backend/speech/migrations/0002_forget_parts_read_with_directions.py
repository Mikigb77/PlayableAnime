"""Forgets every part read before 2026-11-07 (V9, V10).

Those parts were read with style directions before the scene's words, and the studio voice
sometimes read the directions aloud. Each part is kept and replayed, so a player would go on
hearing them: the rows go, and their files with them once the migration commits. The next
listen reads each part again, without directions.
"""

from django.db import migrations, transaction


def forget_parts(apps, schema_editor):
    from media.storage import delete_quietly

    SceneAudio = apps.get_model("speech", "SceneAudio")
    keys = [key for key in SceneAudio.objects.values_list("storage_key", flat=True) if key]
    SceneAudio.objects.all().delete()
    for key in keys:
        transaction.on_commit(lambda key=key: delete_quietly(key))


class Migration(migrations.Migration):
    dependencies = [
        ("speech", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forget_parts, migrations.RunPython.noop),
    ]
