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
