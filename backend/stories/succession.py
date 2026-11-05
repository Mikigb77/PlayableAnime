"""N6: carrying a story on as someone else after its ending.

`POST /v1/stories/{id}/successor` draws a random person of the world by its population odds
(`engine.succession.draw`), and the drafter fills them in (`graph.drafting.successor`). It is one
drafting call, metered and charged like a draft (K2, T9), and drawing again replaces the person
drawn before. `POST /v1/stories/{id}/carry-on` makes that person the player character: the old one
stays in the world and is remembered (`WorldState.fallen`), the ending is lifted, and the story's
next turn is the newcomer's opening (`WorldState.opening_due`).

Neither works on a story that hasn't reached an ending, or that the player closed.
"""

from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import F
from django.http import HttpRequest
from django.utils import timezone
from pydantic import BaseModel

from drafts.service import model_call
from engine import succession
from engine.rng import SeededRng
from engine.state import Character, WorldState
from engine.succession import Lot, Station
from graph.drafting import successor as drafting
from graph.drafting.view import character_lines, public_text
from lucid.errors import field_error, version_conflict
from stories import endings
from stories.models import Story


class Drawn(BaseModel):
    """The person drawn to carry the story on, as kept on `Story.successor` until the player
    starts as them or draws again."""

    draws: int
    lot: Lot
    character: Character
    situation: str
    # Who they are, in the world's words, as the player reads them (G2, G16).
    lines: list[str]


class SuccessorOut(BaseModel):
    """API.md's `Successor`."""

    name: str
    age: int | None = None
    station: Station
    # How rare a person like this is: one in this many (1 for the commonest).
    one_in: int
    # A hidden master: the player knows, and the world doesn't.
    master: bool = False
    place: str | None = None
    people: str | None = None
    # Who they are, in the world's own words (G2, G16).
    lines: list[str]
    # The moment their first scene opens on.
    situation: str
    # How many people have been drawn for this ending so far.
    draws: int


async def draw(request: HttpRequest, story: Story) -> SuccessorOut:
    """Draws someone new to carry the story on, replacing anyone drawn before."""
    state = WorldState.model_validate(story.state)
    ending = _ready(story, state)
    count = Drawn.model_validate(story.successor).draws + 1 if story.successor else 1
    # Seeded per ending and per draw, so drawing again, or after a later ending, is someone new.
    seed = f"story={story.pk}/ending={ending.turn or state.turn}/successor={count}"
    lot = succession.draw(state, SeededRng(seed))
    async with model_call(
        request, rating=story.rating, action="successor", premise_id=None
    ) as call:
        proposal = await drafting.propose(call.client, state, lot, rating=story.rating)
        character, situation = drafting.build(state, lot, proposal)
        # Read as they will be once they carry the story on, so the old player character's goals
        # and what they knew aren't theirs.
        preview = succession.carry_on(state, character, situation, ending="death", turn=state.turn)
        if not public_text(preview, situation):
            # It names someone they don't know, or quotes a secret (C6).
            situation = drafting.ordinary_day(state, character)
        drawn = Drawn(
            draws=count,
            lot=lot,
            character=character,
            situation=situation,
            lines=character_lines(preview),
        )
        drawn = await sync_to_async(_keep)(story, drawn, call)
    return successor_out(state, drawn)


def _keep(story: Story, drawn: Drawn, call) -> Drawn:
    with transaction.atomic():
        current = (
            Story.objects.select_for_update()
            .only("ending", "state", "successor", "version")
            .get(pk=story.pk)
        )
        _ready(current, WorldState.model_validate(current.state))
        if current.version != story.version:
            # Carried on and played on meanwhile: this person was drawn from another world.
            raise version_conflict(current.version)
        # Another draw may have landed meanwhile; this one counts after it.
        before = Drawn.model_validate(current.successor).draws if current.successor else 0
        drawn = drawn.model_copy(update={"draws": before + 1})
        story.successor = drawn.model_dump(mode="json")
        # Not `updated_at`: the Library lists stories by when they were last played.
        story.save(update_fields=["successor"])
        call.charge()
    return drawn


def carry_on(story: Story, expected_version: int) -> Story:
    """Makes the person drawn the player character, with the story's version moving on (T10)."""
    with transaction.atomic():
        current = (
            Story.objects.select_for_update()
            .only("ending", "state", "successor", "version")
            .get(pk=story.pk)
        )
        if current.version != expected_version:
            raise version_conflict(current.version)
        state = WorldState.model_validate(current.state)
        ending = _ready(current, state)
        if not current.successor:
            raise field_error(
                "story_id",
                "Draw someone to carry the story on as first.",
                source="path",
                type="no_successor",
            )
        drawn = Drawn.model_validate(current.successor)
        carried = succession.carry_on(
            state,
            drawn.character,
            drawn.situation,
            ending=ending.kind,
            turn=ending.turn if ending.turn is not None else state.turn,
        )
        Story.objects.filter(pk=story.pk).update(
            state=carried.model_dump(mode="json"),
            ending=None,
            successor=None,
            version=F("version") + 1,
            updated_at=timezone.now(),
        )
    story.refresh_from_db()
    return story


def successor_out(state: WorldState, drawn: Drawn) -> SuccessorOut:
    """What the player sees of the person drawn: in the world's words, never their numbers."""
    character = drawn.character
    place = state.places.get(drawn.lot.place_id or "")
    people = next((p for p in state.bible.peoples if p.id == drawn.lot.people_id), None)
    return SuccessorOut(
        name=character.name,
        age=character.age,
        station=drawn.lot.station,
        one_in=drawn.lot.one_in,
        master=drawn.lot.master,
        place=place.name if place else None,
        people=people.name if people else None,
        lines=drawn.lines,
        situation=drawn.situation,
        draws=drawn.draws,
    )


def drawn_of(story: Story) -> Drawn | None:
    return Drawn.model_validate(story.successor) if story.successor else None


def _ready(story: Story, state: WorldState) -> endings.EndingOut:
    """The story's ending, which must be there and not closed for someone to carry it on."""
    ending = endings.of_story(story.ending, state)
    if ending is None:
        raise field_error(
            "story_id",
            "This story hasn't reached an ending, so nobody needs to carry it on.",
            source="path",
            type="not_ended",
        )
    if ending.closed:
        raise field_error(
            "story_id",
            "This story is closed. Start again from its premise instead.",
            source="path",
            type="closed",
        )
    return ending
