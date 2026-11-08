"""Reads each story aloud in its own language and accent (V9, V10; Miki, 2026-11-08).

A part is now read with the story's language named to the voice model, such as `es-ES`, and kept
under it (`SceneAudio.language`). Before, the model guessed the language from the words, and read
Spanish with a Latin American accent or an English voice's pronunciation. Parts kept from Spanish
and Catalan stories go, and their files with them once the migration commits, so the next listen
reads them again in Spain's Spanish or in Catalan. Parts of English stories were read in English,
as the model heard it, and are kept as read in `en-US`.

The schema changes come first: on Postgres, rows deleted in a transaction can hold back a later
change to their table in it.
"""

from django.db import migrations, models, transaction

# The story languages whose kept parts are read again, and what English parts were read in.
READ_AGAIN = ("es", "ca")
ENGLISH = "en-US"


def read_in_the_story_language(apps, schema_editor):
    from media.storage import delete_quietly

    SceneAudio = apps.get_model("speech", "SceneAudio")
    again = SceneAudio.objects.filter(scene__story__settings__language__in=READ_AGAIN)
    keys = [key for key in again.values_list("storage_key", flat=True) if key]
    again.delete()
    for key in keys:
        transaction.on_commit(lambda key=key: delete_quietly(key))
    SceneAudio.objects.filter(language="").update(language=ENGLISH)


class Migration(migrations.Migration):
    dependencies = [
        ("speech", "0002_forget_parts_read_with_directions"),
        ("stories", "0007_rewind"),
    ]

    operations = [
        migrations.AddField(
            model_name="sceneaudio",
            name="language",
            field=models.CharField(db_default="", default="", max_length=16),
        ),
        migrations.RemoveConstraint(
            model_name="sceneaudio",
            name="scene_audio_voice_part_unique",
        ),
        migrations.AddConstraint(
            model_name="sceneaudio",
            constraint=models.UniqueConstraint(
                fields=("scene", "voice", "language", "part"),
                name="scene_audio_voice_language_part_unique",
            ),
        ),
        migrations.RunPython(read_in_the_story_language, migrations.RunPython.noop),
    ]
