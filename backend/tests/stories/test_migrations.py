import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("stories", "0001_initial")]
AFTER = [("stories", "0002_owner_required")]


@pytest.mark.django_db(transaction=True)
def test_making_owner_required_stops_with_a_clear_message_on_ownerless_stories():
    """Stories made before sign-in have no owner; deleting them is a person's call, not the
    migration's."""
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    Story = executor.loader.project_state(BEFORE).apps.get_model("stories", "Story")
    Story.objects.create(title="Before sign-in", premise="P")
    try:
        with pytest.raises(RuntimeError, match="1 stories have no owner"):
            MigrationExecutor(connection).migrate(AFTER)
        assert Story.objects.count() == 1
    finally:
        Story.objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def _world(status: str) -> dict:
    return {"player_id": "lin", "characters": {"lin": {"name": "Lin Feng", "status": status}}}


@pytest.mark.django_db(transaction=True)
def test_an_older_story_whose_character_is_dead_is_recorded_at_its_ending():
    """N6: so the Library shows it ended without loading its world state."""
    before = [("stories", "0004_story_ending")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    apps = executor.loader.project_state([*before, ("accounts", "0002_sign_in")]).apps
    User, Story = apps.get_model("accounts", "User"), apps.get_model("stories", "Story")
    owner = User.objects.create(email="older@example.com")
    dead = Story.objects.create(owner=owner, title="Dead", premise="P", state=_world("dead"))
    alive = Story.objects.create(owner=owner, title="Alive", premise="P", state=_world("alive"))
    legacy = Story.objects.create(
        owner=owner, title="Old", premise="P", state=_world("dead"), engine="legacy"
    )
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        dead.refresh_from_db()
        assert dead.ending == {
            "kind": "death",
            "character_id": "lin",
            "character": "Lin Feng",
            "self_inflicted": False,
            "turn": None,
            "closed": False,
        }
        alive.refresh_from_db()
        legacy.refresh_from_db()
        assert alive.ending is None and legacy.ending is None
    finally:
        Story.objects.all().delete()
        User.objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
