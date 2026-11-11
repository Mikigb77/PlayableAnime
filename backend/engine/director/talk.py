"""W2: the talk of the place, offered softly.

A place the player character is in may be saying things they haven't heard: the rumors that
reached it before them (`engine.world.hearsay`). Miki, 2026-11-11: "don't force it, like arriving
at a place, immediately hearing stuff ... if there is a rumor in a place, we might hear it at
some point, but it should be soft ... it should also blend with the story. And you might miss
some rumors, that's also okay."

So the director only decides that a scene may carry one piece of that talk. Never a scene that
is about something else: an encounter, an event, a decision with stakes, a trip, or one inside
stopped time. And only now and then (`rules.TALK_CHANCE`), so a rumor waits for a moment it
fits and some are never heard, and never within minutes of the last small thing
(`clock.small_thing_fits`, W10), so a run of short scenes isn't a run of things overheard. A
scene in which the character only looks on (the standing action, S2) is such a moment: what the
place is saying is always on offer to it. Where the
record holds nothing they haven't heard, the place's talk is the narrator's to make up, more
rarely (`rules.OWN_TALK_CHANCE`). Whether the scene has room for it is the narrator's call, and
only what a scene told is recorded as heard (`pipeline.hear_talk`).

Asking is something else. A player who has their character ask what people are saying, or
listen for the talk of the place (`StepFacts.asks_talk`), gets what the place is saying: the
newest thing it has for them, whatever else the scene carries and whatever the clock says, or
talk of the narrator's own making when the record holds nothing new to them. Only a fight, a
scene with something at stake, the road and stopped time leave no room for an answer.
"""

from engine.contracts.direction import PlannedTalk
from engine.contracts.intent import ActionKind
from engine.contracts.resolution import Resolution
from engine.director import rules
from engine.director.pressure import Pressure
from engine.director.sources import here
from engine.rng import SeededRng
from engine.state.world import WorldState
from engine.timekeeping import world_stopped
from engine.world import hearsay


def plan_talk(
    state: WorldState,
    resolution: Resolution,
    rng: SeededRng,
    *,
    pressure: Pressure,
    busy: bool,
    small: bool = True,
    asked: bool = False,
) -> PlannedTalk | None:
    """The talk this scene may carry, if any. `busy` is whether the director already has
    something for the scene to tell: an event, a moment, or happenings that came due. `small`
    is whether the story's clock leaves room for a small thing (`clock.small_thing_fits`).
    `asked` is whether the player character asked or listened for it this turn."""
    if not resolution.steps or pressure.encounter or pressure.stakes:
        return None  # an opening has no steps: it has the premise's own situation to tell
    if busy and not asked:
        return None
    if world_stopped(state) or state.journey is not None:
        return None
    if any(step.trip is not None for step in resolution.steps):
        return None  # a scene that went somewhere is about the going, and the arriving
    place_id = here(state)
    if place_id not in state.places:
        return None
    waiting = hearsay.talk_of(state, state.player_id, place_id, state.world_s)
    if asked:
        # They asked: the place answers with what it is saying, or the narrator makes it up.
        return PlannedTalk(rumor_id=waiting[0].id if waiting else None, asked=True)
    looking_on = all(step.kind is ActionKind.OBSERVE for step in resolution.steps)
    if waiting and looking_on:
        return PlannedTalk(rumor_id=waiting[0].id)  # they are listening: whatever the clock says
    if not small:
        return None  # W10: minutes after the last small thing is too soon for another
    if waiting:
        return PlannedTalk(rumor_id=waiting[0].id) if rng.chance(rules.TALK_CHANCE) else None
    return PlannedTalk() if rng.chance(rules.OWN_TALK_CHANCE) else None
