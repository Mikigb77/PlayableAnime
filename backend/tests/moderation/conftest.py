from datetime import date

import pytest

from stories.models import Engine, Scene, Story

TEEN_BIRTH_DATE = date(2012, 1, 1)


@pytest.fixture
def make_story(db):
    def make(owner, *, rating="teen", scenes=2, **fields) -> Story:
        story = Story.objects.create(
            owner=owner,
            title=fields.pop("title", "The Well"),
            premise="A disciple at the outer-court well.",
            rating=rating,
            engine=fields.pop("engine", Engine.GRAPH),
            turn=scenes,
            **fields,
        )
        for turn in range(1, scenes + 1):
            Scene.objects.create(
                story=story,
                turn=turn,
                kind="opening" if turn == 1 else "action",
                player_action=None if turn == 1 else f"secret action {turn}",
                narration=f"Secret narration of turn {turn}.",
            )
        return story

    return make


@pytest.fixture
def story(player, make_story) -> Story:
    return make_story(player)
