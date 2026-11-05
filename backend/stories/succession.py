"""N6: carrying a story on as someone else after its ending.

`POST /v1/stories/{id}/successor` draws a random person of the world by its population odds
(`engine.succession.draw`), or takes one of the player character's heirs (`engine.heirs`), and the
drafter fills them in (`graph.drafting.successor`). It is one drafting call, metered and charged
like a draft (K2, T9), and drawing again replaces the person drawn before. An heir too young to
act is drafted as they will be once the world has run on to the day they can (`heirs.time_jump`).
`POST /v1/stories/{id}/carry-on` makes that person the player character: the world runs on first
for an heir that needs it, the old player character stays in the world and is remembered
(`WorldState.fallen`), the ending is lifted, and the story's next turn is the newcomer's opening
(`WorldState.opening_due`).

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
from engine import heirs, succession
from engine.context import TurnContext
from engine.rng import SeededRng
from engine.state import Character, WorldState
from engine.succession import STANDING, Lot, Station
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
    # An heir the story has, rather than someone drawn at random, and how long the world runs on
    # before they can act.
    heir: heirs.Heir | None = None


class HeirOut(BaseModel):
    """API.md's `Heir`: someone the player can carry the story on as."""

    id: str
    name: str
    # child, grandchild or great-grandchild of the player character whose story ended.
    relation: str
    # Now; null for a child not born yet.
    age: int | None = None
    unborn: bool = False
    # Years the story skips before they can act: until they are 16, or born and 16.
    years: int = 0


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
    # The player character's heir, rather than someone drawn at random.
    heir: HeirOut | None = None


def heirs_of(story: Story, state: WorldState, ending: endings.EndingOut) -> list[HeirOut]:
    """Who of the player character's family can carry the story on from its ending."""
    return [_heir_out(h) for h in heirs.heirs(state, _heirs_rng(story, state, ending))]


def _heir_out(heir: heirs.Heir) -> HeirOut:
    return HeirOut(
        id=heir.id,
        name=heir.name,
        relation=heir.relation,
        age=heir.age,
        unborn=heir.unborn,
        years=heir.years,
    )


def _heirs_rng(story: Story, state: WorldState, ending: endings.EndingOut) -> SeededRng:
    # Seeded per ending, so whether a dying mother's child lives is settled once.
    return SeededRng(f"story={story.pk}/ending={ending.turn or state.turn}/heirs")


def _settled(story: Story, state: WorldState, ending: endings.EndingOut) -> WorldState:
    """The world as the ending's roll left it: a dying carrier's child it lost won't be born."""
    return heirs.settled(state, _heirs_rng(story, state, ending))


def _jump(
    story: Story, state: WorldState, ending: endings.EndingOut, heir: heirs.Heir
) -> WorldState:
    """The world when an heir can act: run on to that day, the same way every time (A3)."""
    settled = _settled(story, state, ending)
    ctx = TurnContext(story_id=str(story.pk), turn=state.turn)
    rng = SeededRng(f"story={story.pk}/turn={state.turn}/heir={heir.id}/jump")
    return heirs.jump_for(settled, heir, ctx, rng)


def _heir_now(state: WorldState, heir: heirs.Heir) -> Character:
    """The heir in the world they start in, or `heir_lost` when they didn't live to see it."""
    if heir.unborn:
        # The child born of the pregnancy they were offered as.
        character = heirs.born_of(state, heir.carrier_id or "", heir.due_s or 0)
    else:
        character = state.characters.get(heir.id)
    if character is None or not character.alive:
        raise field_error(
            "heir_id",
            f"{heir.name} didn't live to carry the story on. Choose someone else.",
            source="query",
            type="heir_lost",
        )
    return character


async def draw(request: HttpRequest, story: Story, heir_id: str | None = None) -> SuccessorOut:
    """Draws someone new to carry the story on, or takes the heir `heir_id`, replacing anyone
    drawn before."""
    state = WorldState.model_validate(story.state)
    ending = _ready(story, state)
    count = Drawn.model_validate(story.successor).draws + 1 if story.successor else 1
    heir = None
    if heir_id is not None:
        heir = next(
            (h for h in heirs.heirs(state, _heirs_rng(story, state, ending)) if h.id == heir_id),
            None,
        )
        if heir is None:
            raise field_error(
                "heir_id",
                "Nobody by that id can carry this story on.",
                source="query",
                type="unknown_heir",
            )
        # Years of the world's life: off the thread the database work shares.
        now = await sync_to_async(_jump, thread_sensitive=False)(story, state, ending, heir)
        character = _heir_now(now, heir)
        lot = _heir_lot(now, character)
    else:
        now = state
        # Seeded per ending and per draw, so drawing again, or after a later ending, is someone
        # new.
        seed = f"story={story.pk}/ending={ending.turn or state.turn}/successor={count}"
        lot = succession.draw(state, SeededRng(seed))
    async with model_call(
        request, rating=story.rating, action="successor", premise_id=None
    ) as call:
        if heir is not None:
            proposal = await drafting.propose_heir(
                call.client, now, character, years=heir.years, rating=story.rating
            )
            character, situation = drafting.build_heir(
                now, character, proposal, grown=heir.jump_s > 0
            )
        else:
            proposal = await drafting.propose(call.client, state, lot, rating=story.rating)
            character, situation = drafting.build(state, lot, proposal)
        # Read as they will be once they carry the story on, so the old player character's goals
        # and what they knew aren't theirs.
        preview = succession.carry_on(now, character, situation, ending="death", turn=state.turn)
        if not public_text(preview, situation):
            # It names someone they don't know, or quotes a secret (C6).
            situation = drafting.ordinary_day(now, character)
        drawn = Drawn(
            draws=count,
            lot=lot,
            character=character,
            situation=situation,
            lines=character_lines(preview),
            heir=heir,
        )
        drawn = await sync_to_async(_keep)(story, drawn, call)
    return successor_out(now, drawn)


def _heir_lot(state: WorldState, heir: Character) -> Lot:
    """An heir as a draw would describe them: where they live, their standing and might."""
    influence = heir.sheet.axes.influence
    parents = [state.characters[p] for p in heir.parent_ids if p in state.characters]
    influence = max([influence, *(p.sheet.axes.influence for p in parents)])
    station = next(
        (s for s in (Station.ROYAL, Station.NOBLE, Station.NOTABLE) if influence >= STANDING[s][0]),
        Station.COMMON,
    )
    return Lot(
        place_id=heir.location_id,
        station=station,
        might=heir.sheet.axes.might,
        age=heir.age if heir.age is not None else heirs.AGE_OF_ACTION,
        people_id=heir.people_id,
        one_in=1,
    )


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


async def carry_on(story: Story, expected_version: int) -> Story:
    """Makes the person drawn the player character, with the story's version moving on (T10).
    An heir's years run first, off the database's thread and outside the row lock: the jump plays
    the same every time, so it is used if the story is still as it was read."""
    ahead = None
    if story.version == expected_version and story.successor:
        state = WorldState.model_validate(story.state)
        drawn = Drawn.model_validate(story.successor)
        ending = endings.of_story(story.ending, state)
        if drawn.heir is not None and ending is not None and not ending.closed:
            ahead = await sync_to_async(_jump, thread_sensitive=False)(
                story, state, ending, drawn.heir
            )
    return await sync_to_async(_carry_on)(story, expected_version, ahead)


def _carry_on(story: Story, expected_version: int, ahead: WorldState | None) -> Story:
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
        now = _settled(current, state, ending)
        if drawn.heir is not None:
            # The world runs on to the day the heir can act, as it did when they were drawn.
            same = current.state == story.state and current.successor == story.successor
            now = ahead if ahead is not None and same else _jump(current, state, ending, drawn.heir)
            _heir_now(now, drawn.heir)
        carried = succession.carry_on(
            now,
            drawn.character,
            drawn.situation,
            ending=ending.kind,
            turn=ending.turn if ending.turn is not None else state.turn,
            ended_s=state.world_s,
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
        heir=_heir_out(drawn.heir) if drawn.heir is not None else None,
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
