"""N6: a story saved before endings were recorded, whose player character is already dead, is at
its ending. Recording it on the row lets the Library show it without loading the world state."""

from django.db import migrations


def record_older_deaths(apps, schema_editor):
    Story = apps.get_model("stories", "Story")
    stories = Story.objects.filter(engine="graph", ending__isnull=True).only("id", "state")
    for story in stories.iterator(chunk_size=200):
        state = story.state if isinstance(story.state, dict) else {}
        player_id = state.get("player_id")
        characters = state.get("characters")
        player = characters.get(player_id) if isinstance(characters, dict) else None
        if not isinstance(player, dict) or player.get("status") != "dead":
            continue
        story.ending = {
            "kind": "death",
            "character_id": player_id,
            "character": player.get("name") or "",
            "self_inflicted": False,
            "turn": None,
            "closed": False,
        }
        story.save(update_fields=["ending"])


class Migration(migrations.Migration):
    dependencies = [
        ("stories", "0004_story_ending"),
    ]

    operations = [
        migrations.RunPython(record_older_deaths, migrations.RunPython.noop),
    ]
