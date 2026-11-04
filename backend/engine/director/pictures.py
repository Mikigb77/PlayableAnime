"""M1, M2: whether the scene gets a picture. Code decides, never the narrator.

The triggers come from what the engine already records, at most one picture a scene, highest first:

1. The player character's portrait when the story starts (G2).
2. A key character's death the player knows of (N1).
3. The decisive blow of a fight with a key NPC or a strong monster (Miki, 2026-11-03).
4. A breakthrough on a power ladder (G19): a gain from a breakthrough, or named for a ladder or
   one of its rungs.
5. Hidden strength revealed (G20): a deed whose kind is a reveal.
6. A deed of severity 4 or 5 by the player (W1).
7. An arc ending: a premise thread, a clocked thread or one the player took up, closing (N1).
8. The start of a fight with a key NPC or a strong monster.
9. A local or world event arriving (W16).
10. The Library cover, once, from the second scene.
11. The player's place when it has changed for good since its picture, such as ruined, occupied
    or rebuilt (W7), or on the first visit to a place that is already ruined or occupied.
12. A key NPC's portrait the first time they are in a scene (W15).
13. A place on the first visit (W7).
14. The portrait of the player or of someone in the scene whose look changed for good since it
    was drawn, such as a lost eye or old age (M5, G17).

Portraits, places and the cover come once per subject and look version (`engine.looks`), and
`media` reuses each one wherever it appears (M4). A first portrait, a first visit and the cover
come outside the key-scene budget. Key scenes (2 to 9) spend the M2 budget, a bucket that refills
each turn: about one picture per ten turns on key moments, one per five on more, and none at all
when pictures are off. A key scene needs a full credit, and so does drawing a changed place or face
again (11 and 14), which waits for the credit while the place or the person is still there to see.
A fight's start and its decisive blow may borrow against the coming turns, and a decisive blow
whose fight start was pictured always may, so both pictures of a fight come and the average over
the story still holds.
"""

from dataclasses import dataclass

from engine.context import ImageSetting, TurnContext
from engine.contracts.direction import (
    DirectorPlan,
    PictureDecision,
    PictureKind,
    PictureTrigger,
    PlannedEvent,
)
from engine.director import rules
from engine.director.sources import here
from engine.director.turn import TurnFacts
from engine.looks import LASTING_PLACE_STATUSES, place_version
from engine.state.cast import Character, CharacterStatus, Place, Prominence
from engine.state.records import Visibility
from engine.state.scene import EncounterKind
from engine.state.world import DirectorState, EventSize, KeyFight, WorldState, natural_key

ONCE, SCENE, FIGHT = "once", "scene", "fight"


@dataclass(frozen=True)
class Candidate:
    trigger: PictureTrigger
    kind: PictureKind
    subject_id: str | None
    reason: str
    budget: str
    once_keys: tuple[str, ...] = ()
    version: int | None = None


def portrait_keys(character: Character) -> tuple[str, str]:
    """What a portrait marks pictured: the character, and their current look (M4, M5)."""
    return (f"portrait:{character.id}", f"portrait:{character.id}:v{character.look_version}")


def place_keys(place: Place, version: int) -> tuple[str, str]:
    """What a place's picture marks pictured: the place, and its look `version` (M1, M4)."""
    return (f"place:{place.id}", f"place:{place.id}:v{version}")


def _might(state: WorldState, character_id: str) -> int:
    sheet = state.characters[character_id].sheet
    return sheet.axes.might - sheet.condition.weakened_tiers


def strong_foe(state: WorldState, character_id: str) -> bool:
    """A key NPC, or a foe well above the player character on the might axis (A8)."""
    foe = state.characters.get(character_id)
    if foe is None:
        return False
    if foe.prominence is Prominence.KEY:
        return True
    return _might(state, character_id) >= _might(state, state.player_id) + rules.STRONG_FOE_TIERS


def _knows_death(state: WorldState, character_id: str, facts: TurnFacts) -> bool:
    character = state.characters[character_id]
    if character_id in facts.touched or character_id in state.scene.present_ids:
        return True
    return any(
        h.status == CharacterStatus.DEAD.value
        and h.turn == facts.turn
        and state.player_id in h.known_by
        for h in character.status_history
    )


def _follow_fight(
    state: WorldState, memory: DirectorState, facts: TurnFacts
) -> tuple[KeyFight | None, bool, str | None, bool]:
    """The key fight the director follows: whether it started this turn, and who took the
    decisive blow this turn if anyone did. The last value says whether the fight is still on."""
    encounter = state.scene.encounter
    on = (
        encounter is not None
        and encounter.kind is EncounterKind.FIGHT
        and (encounter.key or any(strong_foe(state, i) for i in encounter.opponent_ids))
    )
    fight = memory.fight.model_copy(deep=True) if memory.fight else None
    started = False
    if on:
        if fight is None or fight.started_turn != encounter.started_turn:
            fight = KeyFight(
                opponent_ids=list(encounter.opponent_ids), started_turn=encounter.started_turn
            )
            started = True
        else:
            fight.opponent_ids = list(dict.fromkeys([*fight.opponent_ids, *encounter.opponent_ids]))
    struck: str | None = None
    if fight is not None and not fight.blow_pictured:
        opponents = set(fight.opponent_ids)
        fallen = (facts.died | facts.gravely_hurt) & (opponents | {state.player_id})
        hit = {
            subject
            for deed in facts.deeds
            if deed.severity >= 3
            for subject in deed.subject_ids
            if subject in opponents
        }
        down = sorted(fallen | hit, key=natural_key)
        if down:
            struck = next((i for i in down if i != state.player_id), down[0])
    return fight, started, struck, on


def candidates(
    state: WorldState,
    ctx: TurnContext,
    facts: TurnFacts,
    memory: DirectorState,
    *,
    event: PlannedEvent | None,
    closed_threads: list[str],
    fight: KeyFight | None,
    fight_started: bool,
    struck: str | None,
) -> list[Candidate]:
    pictured = set(memory.pictured)
    player = state.player_id
    found: list[Candidate] = []

    if ctx.turn <= 1 and f"portrait:{player}" not in pictured:
        found.append(
            Candidate(
                PictureTrigger.STORY_START,
                PictureKind.PORTRAIT,
                player,
                "The story starts.",
                ONCE,
                portrait_keys(state.player),
                state.player.look_version,
            )
        )
    for character_id in sorted(facts.died, key=natural_key):
        character = state.characters[character_id]
        key = character.prominence is Prominence.KEY or character_id == player
        if key and _knows_death(state, character_id, facts):
            found.append(
                Candidate(
                    PictureTrigger.DEATH,
                    PictureKind.SCENE,
                    character_id,
                    f"{character.name} dies.",
                    SCENE,
                )
            )
    if struck is not None:
        found.append(
            Candidate(
                PictureTrigger.DECISIVE_BLOW,
                PictureKind.SCENE,
                struck,
                "The fight's decisive blow.",
                FIGHT,
            )
        )
    # Growth records a breakthrough as a gain named for the rung reached (G19); a ladder's own id
    # or name counts too.
    ladders = {
        name.casefold()
        for ladder in state.bible.ladders
        for name in (ladder.id, ladder.name, *(rung.name for rung in ladder.rungs))
    }
    for character_id, gain in facts.gains:
        if character_id == player and (
            gain.source == "breakthrough" or gain.what.casefold() in ladders
        ):
            found.append(
                Candidate(
                    PictureTrigger.BREAKTHROUGH,
                    PictureKind.SCENE,
                    player,
                    f"A breakthrough: {gain.change}.",
                    SCENE,
                )
            )
            break
    for deed in facts.deeds:
        if "reveal" in deed.kind.casefold() and deed.visibility is not Visibility.SECRET:
            if player in deed.known_by:
                found.append(
                    Candidate(
                        PictureTrigger.STRENGTH_REVEALED,
                        PictureKind.SCENE,
                        deed.actor_id,
                        "Hidden strength is revealed.",
                        SCENE,
                    )
                )
                break
    for deed in facts.deeds:
        if deed.actor_id == player and deed.severity >= rules.BIG_DEED:
            found.append(
                Candidate(
                    PictureTrigger.BIG_DEED,
                    PictureKind.SCENE,
                    deed.id,
                    f"A deed of severity {deed.severity}.",
                    SCENE,
                )
            )
            break
    for thread_id in closed_threads:
        thread = state.threads.get(thread_id)
        if thread is not None and player in thread.known_by:
            found.append(
                Candidate(
                    PictureTrigger.ARC_END,
                    PictureKind.SCENE,
                    thread_id,
                    f"{thread.title} comes to an end.",
                    SCENE,
                )
            )
            break
    if fight is not None and fight_started:
        foe = next(
            (i for i in fight.opponent_ids if strong_foe(state, i)),
            fight.opponent_ids[0] if fight.opponent_ids else None,
        )
        found.append(
            Candidate(
                PictureTrigger.FIGHT_START,
                PictureKind.SCENE,
                foe,
                "A fight with a key opponent begins.",
                FIGHT,
            )
        )
    if event is not None and event.needs_decision and event.size is not EventSize.PERSONAL:
        found.append(
            Candidate(
                PictureTrigger.EVENT,
                PictureKind.SCENE,
                event.thread_id,  # a world event's source is a pending event, not a subject
                f"{event.title} arrives.",
                SCENE,
            )
        )
    if ctx.turn >= 2 and "cover" not in pictured:
        found.append(
            Candidate(
                PictureTrigger.COVER,
                PictureKind.COVER,
                None,
                "The Library cover.",
                ONCE,
                ("cover",),
            )
        )
    place_id = here(state)
    place = state.places.get(place_id) if place_id else None
    version = place_version(place) if place is not None else None
    if place is not None:
        seen, now = place_keys(place, version)
        if seen in pictured and version > 1 and now not in pictured:
            found.append(
                Candidate(
                    PictureTrigger.PLACE_CHANGED,
                    PictureKind.PLACE,
                    place.id,
                    f"{place.name}, {place.status.value} now.",
                    SCENE,
                    (now,),
                    version,
                )
            )
        elif seen not in pictured and place.status in LASTING_PLACE_STATUSES:
            found.append(
                Candidate(
                    PictureTrigger.FIRST_VISIT,
                    PictureKind.PLACE,
                    place.id,
                    f"{place.name}, {place.status.value}.",
                    ONCE,
                    (seen, now),
                    version,
                )
            )
    present = [*state.scene.present_ids, *(event.cast_ids if event else []), *sorted(facts.touched)]
    for character_id in dict.fromkeys(present):
        character = state.characters.get(character_id)
        if (
            character is None
            or character_id == player
            or character.prominence is not Prominence.KEY
            or not character.alive
            or f"portrait:{character_id}" in pictured
        ):
            continue
        found.append(
            Candidate(
                PictureTrigger.FIRST_MEETING,
                PictureKind.PORTRAIT,
                character_id,
                f"Meeting {character.name}.",
                ONCE,
                portrait_keys(character),
                character.look_version,
            )
        )
        break
    if place is not None and f"place:{place.id}" not in pictured:
        found.append(
            Candidate(
                PictureTrigger.FIRST_VISIT,
                PictureKind.PLACE,
                place.id,
                f"Arriving at {place.name}.",
                ONCE,
                place_keys(place, version),
                version,
            )
        )
    in_scene = [player, *state.scene.present_ids, *(event.cast_ids if event else [])]
    for character_id in dict.fromkeys(in_scene):
        character = state.characters.get(character_id)
        if character is None or not character.alive or character.look_version <= 1:
            continue
        seen, now = portrait_keys(character)
        if seen in pictured and now not in pictured:
            found.append(
                Candidate(
                    PictureTrigger.LOOK_CHANGED,
                    PictureKind.PORTRAIT,
                    character_id,
                    f"{character.name} has changed for good.",
                    SCENE,
                    (now,),
                    character.look_version,
                )
            )
            break
    return found


def decide_picture(
    state: WorldState,
    ctx: TurnContext,
    facts: TurnFacts,
    memory: DirectorState,
    *,
    event: PlannedEvent | None,
    closed_threads: list[str],
) -> PictureDecision | None:
    """The scene's picture, if it gets one. Updates `memory` (a working copy): the budget, the
    subjects pictured and the key fight being followed."""
    fight, started, struck, on = _follow_fight(state, memory, facts)
    setting = ctx.settings.images
    decision = None
    if setting is not ImageSetting.OFF:
        credit = min(
            rules.PICTURE_CAP[setting], memory.picture_credit + rules.PICTURE_REFILL[setting]
        )
        for candidate in candidates(
            state,
            ctx,
            facts,
            memory,
            event=event,
            closed_threads=closed_threads,
            fight=fight,
            fight_started=started,
            struck=struck,
        ):
            if candidate.budget == SCENE and credit < 1:
                continue
            if candidate.budget == FIGHT:
                borrowed = (
                    candidate.trigger is PictureTrigger.DECISIVE_BLOW
                    and fight is not None
                    and fight.start_pictured
                )
                floor = rules.PICTURE_FLOOR + 1 if borrowed else 0
                if credit < floor:
                    continue
            if candidate.budget in (SCENE, FIGHT):
                credit = max(rules.PICTURE_FLOOR, credit - 1)
            memory.pictured = [*memory.pictured, *candidate.once_keys]
            memory.auto_pictures += 1
            if fight is not None and candidate.trigger is PictureTrigger.FIGHT_START:
                fight.start_pictured = True
            if fight is not None and candidate.trigger is PictureTrigger.DECISIVE_BLOW:
                fight.blow_pictured = True
            decision = PictureDecision(
                kind=candidate.kind,
                trigger=candidate.trigger,
                subject_id=candidate.subject_id,
                version=candidate.version,
                reason=candidate.reason,
            )
            break
        memory.picture_credit = round(credit, 3)
    if fight is not None and struck is not None:
        fight.blow_pictured = True  # one decisive blow per fight, pictured or not
    memory.fight = fight if on else None
    return decision


def settle_look(state: WorldState, plan: DirectorPlan) -> tuple[WorldState, DirectorPlan]:
    """M4, M5: the look a planned portrait or place is drawn at, once the narrator's update is in.

    The director decides before the scene is told, so a scene that changes the look it pictures,
    such as a first meeting that leaves a scar or a first visit as the town falls, draws the new
    look. The director's memory marks that look drawn too, so the next scene doesn't draw it again.
    Returns the state and the plan, copied where they change."""
    decision = plan.picture
    if decision is None or decision.subject_id is None:
        return state, plan
    if decision.kind is PictureKind.PORTRAIT and decision.subject_id in state.characters:
        character = state.characters[decision.subject_id]
        version, (_, key) = character.look_version, portrait_keys(character)
    elif decision.kind is PictureKind.PLACE and decision.subject_id in state.places:
        place = state.places[decision.subject_id]
        version = place_version(place)
        key = place_keys(place, version)[1]
    else:
        return state, plan
    if decision.version == version:
        return state, plan
    pictured = list(dict.fromkeys([*state.director.pictured, key]))
    director = state.director.model_copy(update={"pictured": pictured})
    picture = decision.model_copy(update={"version": version})
    return (
        state.model_copy(update={"director": director}),
        plan.model_copy(update={"picture": picture}),
    )
