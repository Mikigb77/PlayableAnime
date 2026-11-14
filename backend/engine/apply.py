"""Apply a proposed `StateDelta` to the world, enforcing C1 (B5 step 6).

The model proposes; this module decides what sticks. A change that breaks an invariant is
rejected, not applied, and the rejection says why, so the turn can log it and the continuity check
can repair the next scene (C5). Nothing raises for a bad proposal: a forgetful or injected model
can't break the world (A7), and the rest of the delta still applies.

Who may change what:

- **Narrator and engine:** new characters, factions and places (with real names), descriptions,
  locations, small attitude nudges, condition (except harm to the player character that nothing
  recorded this turn caused: worse health, a wound or a passing state that names an injury,
  `engine.injuries`), memberships, facts, leads, the player's goals that are over (closed,
  never rewritten: one that repeats another closes into the older, N2), non-terminal status
  changes, the scene's end and the summary, and what changes hands, money
  included, which `engine.possessions` moves from giver to receiver so nobody gives what they
  don't have (C10). A lasting change to how a known character looks (`look_change`) moves their
  `look_version` on (M5, `engine.looks`).
- **Engine only:** deaths, destroyed factions and ruined places (resolve records the outcome
  before narration, F4); anything that undoes one, which also needs a recorded `Cause`; faction
  reputation (W3); rulings (A9), gains (A4), accepted backstory (N4) and rule changes (G7);
  wounds that last, and any harm to the player character (N6); and the state of powers
  (cooldowns and settled details, never changed once set), skills, techniques, ladders,
  practice and time effects (A4, G19, G20, W10a).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self

from engine import bonds, possessions
from engine import path as path_mod
from engine.base import (
    AFFINITY_MAX,
    AFFINITY_MIN,
    ESTEEM_MAX,
    ESTEEM_MIN,
    FEAR_MAX,
    FEAR_MIN,
    TRUST_MAX,
    TRUST_MIN,
)
from engine.context import TurnContext
from engine.contracts.delta import (
    WORLD,
    AttitudeShift,
    BondChange,
    CharacterChange,
    Expecting,
    FactionChange,
    GoalEnd,
    GoalMoved,
    GoalOver,
    ItemChange,
    NewRung,
    PlaceChange,
    PowerChange,
    RuleChange,
    SceneEnd,
    StateDelta,
)
from engine.injuries import names_injury
from engine.invariants import (
    ancestry,
    cause_problem,
    death_reversal_problem,
    faction_revival_problem,
    is_real_name,
    place_rebuild_problem,
)
from engine.kin import descendants
from engine.limits import adult_problem, normalize
from engine.looks import look_after
from engine.state.bible import PowerLadder, Rung
from engine.state.cast import (
    MAX_JUDGED,
    Character,
    CharacterStatus,
    DeathCertainty,
    Faction,
    FactionStatus,
    Membership,
    Place,
    PlaceStatus,
    Pregnancy,
    Prominence,
)
from engine.state.records import (
    Bond,
    BondEnd,
    BondStage,
    BondStep,
    Cause,
    CauseMechanism,
    Fact,
    GoalStatus,
    Lead,
    Origin,
    OriginKind,
    StatusChange,
)
from engine.state.scene import SceneFrame
from engine.state.sheet import (
    Attitude,
    BackstoryClaim,
    Grudge,
    Health,
    LadderPosition,
    PassingState,
    Wound,
)
from engine.state.world import ActiveTimeEffect, WorldState, natural_key
from engine.text import any_mentions
from engine.timekeeping import effect_over
from engine.world import old_age
from engine.world.geography import find_place, scene_ids, together
from engine.world.tuning import AGELESS_YEARS, GESTATION_S

# How far one narrated scene can move an attitude on its own (W4). The engine moves them further.
NARRATOR_ATTITUDE_CAP = 10
# How long the sentence on where a goal stands may be (N2).
MAX_PROGRESS = 300
# W10: why a narrated scene's word about someone it can't have in it is refused.
_ELSEWHERE = "the record has them elsewhere, and only the world brings them here"
# W6: a scene lengthens the life of nobody it doesn't reach.
_UNREACHED = "the scene doesn't reach them: only the world touches anyone elsewhere"
# G18, A4: a rung is come standing on only by someone the same delta brings into the story.
_NOBODY_LIFTED = "only someone this scene brought in comes standing on it: nobody is lifted"


class DeltaSource(StrEnum):
    ENGINE = "engine"
    NARRATOR = "narrator"


@dataclass(frozen=True)
class Rejection:
    """A proposed change that didn't stick, and why."""

    subject: str
    change: str
    reason: str

    def __str__(self) -> str:
        return f"{self.subject} {self.change}: {self.reason}"


@dataclass(frozen=True)
class Applied:
    """`came` is who walked into a narrated scene from nearby, each with the place the record
    had them at (`Door.near`): the world sends them back there in time
    (`engine.pipeline.settle_walk_ins`)."""

    state: WorldState
    rejected: tuple[Rejection, ...] = field(default_factory=tuple)
    came: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Door:
    """W4, W10, W17. Whom a narrated scene may have in it, of the people on record. Code keeps
    it, never the scene's end: in the first stories about an affair on the real model
    (2026-11-13) the narrator walked the wronged wife into the scene from her farm forty minutes
    away, listed her as present, and the record took its word, so she had seen the next move
    and the story after it followed a scene the engine never decided.

    Someone is let in when they were in the scene as it began (`scene`), when the record has
    them where the scene plays or ends (`spots`, by `together`) or places them nowhere, when
    the turn brought them (`brought`: an event, a happening or a moment is about them, or an
    event of the world fired in the player character's sight), or when this scene made them up
    (anyone not in `known`). Nobody else comes from where the record has them: only the world
    moves people between places (W10). `barred` are those this scene can't bring in or touch at
    all, whatever the record says of where they are: whoever a move in a romance wrongs and
    who didn't see it (W17). `reached` is whom the turn reached without their being there
    (`engine.pipeline.reached`): the scene may move how they feel and have them meet the player
    character, and that is all.

    And someone walks in when the world allows it (`near`, from
    `engine.pipeline.within_reach`, by the rules of `engine.world.visits`): the scene tells
    them, the map has them within a day's way, nothing holds them, no romance in the scene
    wrongs them and the turn did nothing for them to walk in on. The first plays by hand on
    the real models (2026-11-14) had a commander whose boots the last scene heard on the path,
    and a miller with a broken brace for the smith, told into scenes the record then kept them
    out of, so the story and its Memory parted ways in one scene in twenty-five. Where the
    world allows it the record follows the scene: they are at the scene's place (`comes`),
    and the world sends them back in time.
    """

    scene: frozenset[str]
    known: frozenset[str]
    spots: frozenset[str]
    reached: frozenset[str] = frozenset()
    brought: frozenset[str] = frozenset()
    barred: frozenset[str] = frozenset()
    near: frozenset[str] = frozenset()

    @classmethod
    def of(
        cls,
        state: WorldState,
        delta: StateDelta,
        *,
        reached: Sequence[str] = (),
        brought: Sequence[str] = (),
        barred: Sequence[str] = (),
        near: Sequence[str] = (),
    ) -> Self:
        """The door of the scene `delta` tells, on the state the steps left. The scene plays
        where the record has the player character by now, which is where a trip of this turn
        took them: whoever they left behind at the place the scene began in isn't there. It
        also plays where its end says it stops, when that is a place on record already (`admits`
        takes a place the delta itself makes, once it is on record)."""
        spots = {state.player.location_id or state.scene.place_id}
        if delta.scene_end is not None:
            spots.add(find_place(state.places, delta.scene_end.place_id, among=_near(state)))
        return cls(
            scene=frozenset(scene_ids(state)),
            known=frozenset(state.characters),
            spots=frozenset(spot for spot in spots if spot in state.places),
            reached=frozenset(reached),
            brought=frozenset(brought),
            barred=frozenset(barred),
            near=frozenset(near),
        )

    def admits(self, state: WorldState, character_id: str, *, at: str | None = None) -> bool:
        """Whether the scene may have them in it. `at` is one more place the scene plays in:
        where it ends, once the delta's own places are on record."""
        if character_id in self.scene or character_id not in self.known:
            return True
        if character_id in self.barred:
            return False
        if character_id in self.brought or character_id in self.near:
            return True
        return self._there(state, character_id, at)

    def _there(self, state: WorldState, character_id: str, at: str | None) -> bool:
        """Whether the record has them where the scene plays, or nowhere, which is the
        scene's to place."""
        character = state.characters.get(character_id)
        spots = {*self.spots, at} - {None}
        if character is None or character.location_id not in state.places or not spots:
            return True
        return any(together(state, character.location_id, spot) for spot in spots)

    def plays_at(self, state: WorldState, place_id: str | None) -> bool:
        """Whether a place is one the scene plays in: one of its spots, or inside or around
        one."""
        return place_id in state.places and any(
            together(state, place_id, spot) for spot in self.spots
        )

    def comes(self, state: WorldState, character_id: str, *, at: str | None = None) -> bool:
        """Whether the scene has them only because they could walk over (`near`): the record
        has them at another place, and nothing else lets them in. They are the ones it moves
        to where the scene plays, and nowhere else."""
        if character_id in self.scene or character_id not in self.known:
            return False
        if character_id in self.barred or character_id in self.brought:
            return False
        return character_id in self.near and not self._there(state, character_id, at)

    def touches(self, state: WorldState, character_id: str) -> bool:
        """Whether the scene reaches them at all: it may have them in it, or the turn reached
        them where they are."""
        if character_id in self.barred:
            return False
        return character_id in self.reached or self.admits(state, character_id)


def apply_delta(
    state: WorldState,
    delta: StateDelta,
    ctx: TurnContext,
    *,
    source: DeltaSource,
    may_hurt_player: bool = False,
    player_acted: bool = False,
    found: Sequence[str] = (),
    reached: Sequence[str] = (),
    brought: Sequence[str] = (),
    barred: Sequence[str] = (),
    near: Sequence[str] = (),
) -> Applied:
    """Apply `delta` to a copy of `state` at the current world time, on behalf of `source`, and
    stamp what it records with `ctx.turn`. It never raises for a bad proposal: refused changes
    come back in `Applied.rejected`, and the rest still applies. It doesn't touch `state.turn`.

    Places and factions go first, so characters in the same delta can refer to them, and family
    ties after every character. The narrator hurts the player character only with
    `may_hurt_player`, when something recorded this turn is the cause (`engine.injuries`). A goal
    closes only with `player_acted`, on a turn the player acted (N2). `found` is what this turn
    made canon (`Resolution.found`): the scene's record keeps it beside what the narrator lists,
    while the scene stays in its place (R2, R3). `reached` is whom the turn reached besides the
    people in the scene (`engine.pipeline.reached`): the narrator moves the feelings of nobody
    else (W4, `scene_people`). `brought` is whom the turn brings into the scene from wherever
    the record has them (`engine.pipeline.brought`) and `barred` whom this scene can't bring in
    or touch (`engine.pipeline.kept_out`): a narrated scene has nobody else in it that the
    record has elsewhere, and moves nobody else (W10, W17, `Door`), but whoever could have
    walked over (`near`, from `engine.pipeline.within_reach`), who is then at the scene's place
    on record (`Applied.came`).
    """
    return apply_in_place(
        state.model_copy(deep=True),
        delta,
        ctx,
        source=source,
        may_hurt_player=may_hurt_player,
        player_acted=player_acted,
        found=found,
        reached=reached,
        brought=brought,
        barred=barred,
        near=near,
    )


def apply_in_place(
    state: WorldState,
    delta: StateDelta,
    ctx: TurnContext,
    *,
    source: DeltaSource,
    may_hurt_player: bool = False,
    player_acted: bool = False,
    found: Sequence[str] = (),
    reached: Sequence[str] = (),
    brought: Sequence[str] = (),
    barred: Sequence[str] = (),
    near: Sequence[str] = (),
) -> Applied:
    """`apply_delta` on a working copy the caller owns, such as `play_out`'s, which it changes
    in place instead of copying the whole state again. `Applied.state` is that same object."""
    door = None
    if source is DeltaSource.NARRATOR:
        door = Door.of(state, delta, reached=reached, brought=brought, barred=barred, near=near)
    applier = _Applier(
        state,
        source,
        ctx.turn,
        may_hurt_player=may_hurt_player,
        player_acted=player_acted,
        in_scene=scene_people(state, delta, door) if door is not None else None,
        door=door,
    )
    for change in delta.places:
        applier.place(change)
    for change in delta.factions:
        applier.faction(change)
    for change in delta.characters:
        applier.character(change)
    for change in delta.characters:
        applier.family(change)
    for rung in delta.rungs:
        applier.rung(rung)
    applier.stand()
    for fact in delta.facts:
        applier.fact(fact)
    for item in delta.items:
        applier.item(item)
    for lead in delta.leads:
        applier.lead(lead)
    for over in delta.goals_over:
        applier.goal_over(over)
    for moved in delta.goals_moved:
        applier.goal_moved(moved)
    for rule in delta.rule_changes:
        applier.rule(rule)
    for effect in delta.time_effects:
        applier.time_effect(effect)
    for moved in delta.bonds:
        applier.bond(moved)
    if delta.scene_end is not None:
        end = delta.scene_end
        new = applier.state
        with_player = _with_player(new)
        place_id = applier.scene_place(end, delta.places)
        left = new.scene.place_id
        stays = place_id is None or place_id == left
        new.scene = SceneFrame(
            place_id=place_id or new.scene.place_id,
            present_ids=applier.present(end, place_id),
            positions=end.positions,
            props=_scene_props(end.props, found if stays else ()),
            ended_on=end.ended_on,
            encounter=new.scene.encounter,
        )
        if place_id is not None:
            _gather(new, place_id, with_player, left=left)
            # C6, R8: the player character knows the place their scene ends in, and has been there.
            _add(new.places[place_id].visited_by, new.player_id)
            _add(new.places[place_id].known_by, new.player_id)
    elif found:
        # The scene goes on where it was, so its record keeps what the turn found (R2, R3).
        applier.state.scene.props = _scene_props(applier.state.scene.props, found)
    if delta.summary:
        applier.state.summary = delta.summary
    return Applied(applier.state, tuple(applier.rejected), tuple(applier.came.items()))


def scene_people(state: WorldState, delta: StateDelta, door: Door) -> set[str]:
    """W4. Whose feelings a narrated scene can move: the people in it. They are those the
    last scene left there and those in its fight, chase or talks (`geography.scene_ids`),
    whoever the turn reached (`Door.reached`), and those the scene's end lists or the scene
    brings in (someone new, someone it has meet the player character or someone it puts where
    the scene is) whom the record lets it have there (`Door.admits`).

    Someone elsewhere saw none of it, however much it concerns them: a son doesn't come to hate
    his father's killer in the moment of a killing he wasn't at. What they come to know reaches
    them through the world, by a witness or by word (W2), and code moves how they feel then.
    So it is with whoever a move in a romance wrongs who didn't see it (`Door.barred`, W17):
    the scene moves nothing in them, wherever they are."""
    people = {*door.scene, *door.reached}
    listed: set[str] = set()
    here = {state.player.location_id, state.scene.place_id}
    if delta.scene_end is not None:
        listed.update(delta.scene_end.present_ids)
        here.add(delta.scene_end.place_id)
    here.discard(None)
    for change in delta.characters:
        new = change.id not in state.characters
        if new or change.meets_player or change.location_id in here:
            listed.add(change.id)
    people.update(i for i in listed if door.admits(state, i))
    return people - door.barred


# The most things a scene's record holds once code has added to the narrator's list (R3).
MAX_PROPS = 24


def _scene_props(told: list[str], found: Sequence[str]) -> list[str]:
    """R2, R3. The scene's things as the narrator listed them, then whatever this turn made
    canon there that the list doesn't name. The narrator lists what matters next and often
    leaves out the branch the character just picked up; code found it, so code keeps it, and
    the next turn's beat check finds it on record."""
    props = list(told)
    for thing in found:
        if len(props) >= MAX_PROPS:
            break
        if thing.strip() and any_mentions(props, thing) is None:
            props.append(thing.strip())
    return props


def _near(state: WorldState) -> list[str]:
    """C6. The places a scene can name by their names: those the player character knows of or
    is in, never a namesake in a city they have never heard of."""
    player = state.player_id
    return [
        *(p.id for p in state.places.values() if player in p.known_by or player in p.visited_by),
        *ancestry(state.places, state.scene.place_id),
        *ancestry(state.places, state.player.location_id),
    ]


def _with_player(state: WorldState) -> set[str]:
    """Who was with the player character as the scene ended: in the scene, at or within the
    player character's place, or placed nowhere."""
    here = state.player.location_id or state.scene.place_id
    near = set(state.scene.present_ids)
    for character_id, character in state.characters.items():
        where = character.location_id
        if where is None or here is None:
            near.add(character_id)
        elif here in ancestry(state.places, where) or where in ancestry(state.places, here):
            near.add(character_id)
    return near


def _gather(
    state: WorldState, place_id: str, with_player: set[str], *, left: str | None = None
) -> None:
    """R3, R8, C2. The scene ends at `place_id`, so the player character is there, and so is
    everyone living in the scene who came with them: the world places witnesses and events where
    people are (W2, W16). A scene that stays where the last one was (`left`) keeps anyone at a
    more exact spot inside it there, such as at the well in the courtyard both scenes name. A
    scene that ends somewhere else has moved them, even out to the place around the one they
    were in: out of the temple into the forest it lies in, nobody stays inside the temple (R8).
    The narrator naming someone far off, or missing, as present doesn't move them: only the
    engine's own record does."""
    moved = left is not None and left != place_id
    for character_id in dict.fromkeys([state.player_id, *state.scene.present_ids]):
        character = state.characters.get(character_id)
        if character is None or not character.alive:
            continue
        if character_id != state.player_id and (
            character.status is not CharacterStatus.ALIVE or character_id not in with_player
        ):
            continue
        if moved or place_id not in ancestry(state.places, character.location_id):
            character.location_id = place_id


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class _Applier:
    def __init__(
        self,
        state: WorldState,
        source: DeltaSource,
        turn: int,
        *,
        may_hurt_player: bool = False,
        player_acted: bool = False,
        in_scene: set[str] | None = None,
        door: Door | None = None,
    ) -> None:
        self.state = state
        self.source = source
        self.turn = turn
        self.may_hurt_player = may_hurt_player
        self.player_acted = player_acted
        # W4: whose feelings the narrator may move (`scene_people`); None means anyone's.
        self.in_scene = in_scene
        # W10: who walked into the scene from nearby, with the place the record had them at.
        self.came: dict[str, str] = {}
        # W10: whom the narrator's scene may have in it and move (`Door`); None means anyone.
        self.door = door
        self.rejected: list[Rejection] = []
        # G18: who this delta brought into the story, the rung each character's change says
        # they stand on, and how many came standing on each rung this delta added.
        self.created: set[str] = set()
        self.claimed: dict[str, str] = {}
        self.came: dict[tuple[str, int], int] = {}
        # How far the narrator has moved each attitude in this delta, so several small shifts
        # can't add up past the cap: (character, toward, axis) -> total so far.
        self.nudged: dict[tuple[str, str, str], int] = {}

    @property
    def engine(self) -> bool:
        return self.source is DeltaSource.ENGINE

    @property
    def origin(self) -> Origin:
        kind = OriginKind.ENGINE if self.engine else OriginKind.NARRATOR
        return Origin(kind=kind, ref_id=f"turn-{self.turn}")

    def reject(self, subject: str, change: str, reason: str) -> None:
        self.rejected.append(Rejection(subject, change, reason))

    def longer_life(self, character: Character, years: int) -> None:
        """W6. A scene lengthened someone's life, or ended their ageing: a span of their own
        from here on, where it is longer than they already live by their people, their rung
        and any span they had (`engine.world.old_age.span`). A life is never shortened this
        way, so fewer years change nothing, and a scene lengthens the life only of someone it
        reaches: only the world touches anyone elsewhere (W10)."""
        years = min(years, AGELESS_YEARS)
        if years <= old_age.span(self.state, character):
            return
        if self.door is not None and not self.door.touches(self.state, character.id):
            self.reject(f"character {character.id}", "lifespan", _UNREACHED)
            return
        character.lifespan_years = years

    def engine_only(self, subject: str, change: str) -> bool:
        """True if the change may go ahead; records a rejection for the narrator."""
        if not self.engine:
            self.reject(subject, change, "only the engine decides this")
        return self.engine

    def history(
        self, status: str, cause, *, known: bool, from_status: str, presumed: bool = False
    ) -> StatusChange:
        player = self.state.player_id
        return StatusChange(
            status=status,
            from_status=from_status,
            presumed=presumed,
            turn=self.turn,
            world_s=self.state.world_s,
            timeline_id=self.state.timeline_id,
            cause=cause,
            known_by=[player] if known else [],
        )

    def known_to_player(self, character_id: str, flagged: bool) -> bool:
        """Whether the player character learns of a change to someone: flagged, or in the scene."""
        return flagged or character_id in self.state.scene.present_ids

    def cause_of(self, subject: str, change) -> Cause | None:
        """The change's cause, which only the engine may give (C1)."""
        if change.cause is not None and not self.engine:
            self.reject(subject, "cause", "only the engine records a cause")
            return None
        return change.cause

    # --- places -----------------------------------------------------------------------------

    def place(self, change: PlaceChange) -> None:
        subject = f"place {change.id}"
        place = self.state.places.get(change.id)
        if place is None:
            if not is_real_name(change.name):
                self.reject(subject, "create", "a new place needs a name")
                return
            place = Place(id=change.id, name=change.name)
            self.state.places[place.id] = place
        elif change.name and change.name != place.name:
            place.name = change.name
        for attr in ("kind", "description", "mood"):
            value = getattr(change, attr)
            if value is not None:
                setattr(place, attr, value)
        if change.setting is not None and change.setting is not place.setting:
            # R8: a crypt doesn't come out under the sky because a scene told it so. Only the
            # engine changes a setting once it is told, such as a roof that falls in.
            if place.setting is None or self.engine:
                place.setting = change.setting
            else:
                self.reject(subject, "setting", f"it is {place.setting.value}")
        if change.parent_id is not None:
            if change.parent_id not in self.state.places:
                self.reject(subject, "parent", f"no place {change.parent_id!r}")
            elif place.id in ancestry(self.state.places, change.parent_id):
                self.reject(subject, "parent", f"{change.parent_id!r} lies within it")
            else:
                place.parent_id = change.parent_id
        if change.controller_id is not None:
            if change.controller_id in self.state.factions or change.controller_id in (
                self.state.characters
            ):
                place.controller_id = change.controller_id
            else:
                self.reject(subject, "controller", f"no faction {change.controller_id!r}")
        for route in change.routes:
            if route.to_id not in self.state.places:
                self.reject(subject, "route", f"no place {route.to_id!r}")
                continue
            place.routes = [r for r in place.routes if r.to_id != route.to_id] + [route]
        cause = self.cause_of(subject, change)
        if change.status is not None and change.status is not place.status:
            self.place_status(place, change, cause)
        player = self.state.player_id
        if change.visited:
            _add(place.visited_by, player)
            _add(place.known_by, player)
        if change.known_to_player:
            _add(place.known_by, player)
        if change.judged and self.engine_only(subject, "judged"):
            # A3. A thing keeps the level it was first judged at.
            for judged in change.judged:
                if place.level_of(judged.key) is None:
                    place.judged.append(judged)
            del place.judged[:-MAX_JUDGED]

    def present(self, end: SceneEnd, place_id: str | None) -> list[str]:
        """R3, W10. Who is in the scene as it ends, of those its end lists: people on record
        whom the scene may have there (`Door.admits`, with `place_id` the place it ends in).
        Someone the record has elsewhere is left out, and stays where they are."""
        present = []
        for character_id in end.present_ids:
            if character_id not in self.state.characters:
                continue
            if self.door is None or self.door.admits(self.state, character_id, at=place_id):
                present.append(character_id)
                self.walk_in(character_id, place_id)
            else:
                self.reject(f"character {character_id}", "presence", _ELSEWHERE)
        return present

    def walk_in(self, character_id: str, place_id: str | None) -> None:
        """W10. Someone the scene's end has there only because they could walk over
        (`Door.comes`) is where the scene plays, on record: at `place_id`, the place it ends
        in, or where the player character is. Where they came from is kept (`came`), so the
        world sends them back. Someone the scene only has meet the player character on the
        way came and went: they are where they were."""
        door, state = self.door, self.state
        if door is None or not door.comes(state, character_id, at=place_id):
            return
        here = place_id or state.player.location_id or state.scene.place_id
        character = state.characters[character_id]
        if here not in state.places or character.location_id is None:
            return
        self.came.setdefault(character_id, character.location_id)
        character.location_id = here

    def scene_place(self, end: SceneEnd, changes: list[PlaceChange]) -> str | None:
        """R3, R8. The place the scene ends in, once this delta's places are on record, or None
        to keep the last one. The place is named by its id, or by its name however it is
        spelled; failing that, the one place the delta says the player character is now at
        (`PlaceChange.visited`) stands for it. A place on no record is refused, so the next scene
        starts where the record has the character, never somewhere it can't name."""
        state = self.state
        places = state.places
        here = state.scene.place_id
        near = [*_near(state), *(c.id for c in changes)]
        found = find_place(places, end.place_id, among=near)
        if found is not None:
            return found
        visited = {c.id for c in changes if c.visited and c.id in places and c.id != here}
        if len(visited) == 1:
            return visited.pop()
        named = (end.place_id or "").strip()
        if named:
            self.reject("scene", "place", f"no place {named!r}, so it stays at the last one")
        return None

    def place_status(self, place: Place, change: PlaceChange, cause: Cause | None) -> None:
        subject = f"place {place.id}"
        # The player character sees what happens to the place they're in.
        known = change.known_to_player or change.visited or self.state.scene.place_id == place.id
        if place.status is PlaceStatus.RUINED:
            if not self.engine_only(subject, "rebuild"):
                return
            if cause is None:
                self.reject(subject, "rebuild", "a ruined place recovers only with a cause (C1)")
                return
            problem = place_rebuild_problem(self.state, place.id, cause)
            if problem:
                self.reject(subject, "rebuild", problem)
                return
        elif change.status is PlaceStatus.RUINED and not self.engine_only(subject, "ruin"):
            return
        before = place.status
        place.status = change.status
        place.status_history.append(
            self.history(change.status.value, cause, known=known, from_status=before.value)
        )

    # --- factions ---------------------------------------------------------------------------

    def faction(self, change: FactionChange) -> None:
        subject = f"faction {change.id}"
        faction = self.state.factions.get(change.id)
        if faction is None:
            if not is_real_name(change.name):
                self.reject(subject, "create", "a new faction needs a name")
                return
            faction = Faction(id=change.id, name=change.name, origin=self.origin)
            self.state.factions[faction.id] = faction
        elif change.name and change.name != faction.name:
            faction.name = change.name
        for attr in ("kind", "description"):
            value = getattr(change, attr)
            if value is not None:
                setattr(faction, attr, value)
        if change.parent_id is not None:
            if change.parent_id not in self.state.factions:
                self.reject(subject, "parent", f"no faction {change.parent_id!r}")
            elif faction.id in ancestry(self.state.factions, change.parent_id):
                self.reject(subject, "parent", f"{change.parent_id!r} is part of it")
            else:
                faction.parent_id = change.parent_id
        if (change.esteem or change.fear) and self.engine_only(subject, "reputation"):
            rep = faction.player_reputation
            rep.esteem = _clamp(rep.esteem + change.esteem, ESTEEM_MIN, ESTEEM_MAX)
            rep.fear = _clamp(rep.fear + change.fear, FEAR_MIN, FEAR_MAX)
        cause = self.cause_of(subject, change)
        if change.status is not None and change.status is not faction.status:
            self.faction_status(faction, change, cause)
        if change.known_to_player:
            _add(faction.known_by, self.state.player_id)

    def faction_status(self, faction: Faction, change: FactionChange, cause: Cause | None) -> None:
        subject = f"faction {faction.id}"
        if faction.status is FactionStatus.DESTROYED:
            if not self.engine_only(subject, "revive"):
                return
            if cause is None:
                self.reject(subject, "revive", "a destroyed faction returns only with a cause")
                return
            problem = faction_revival_problem(self.state, faction, cause, change.status)
            if problem:
                self.reject(subject, "revive", problem)
                return
        elif change.status is FactionStatus.DESTROYED and not self.engine_only(subject, "destroy"):
            return
        before = faction.status
        faction.status = change.status
        faction.status_history.append(
            self.history(
                change.status.value,
                cause,
                known=change.known_to_player,
                from_status=before.value,
            )
        )

    # --- characters -------------------------------------------------------------------------

    def character(self, change: CharacterChange) -> None:
        subject = f"character {change.id}"
        character = self.state.characters.get(change.id)
        created = character is None
        if created:
            character = self.new_character(change)
            if character is None:
                return
        elif change.name and change.name != character.name:
            if not is_real_name(change.name):
                self.reject(subject, "rename", f"{change.name!r} isn't a name")
            else:
                _add(character.aliases, character.name)
                character.name = change.name
        for alias in change.aliases:
            if alias != character.name:
                _add(character.aliases, alias)
        look = None
        if not created:
            look = look_after(
                character, appearance=change.appearance, look_change=change.look_change
            )
        for attr in ("description", "appearance", "age", "people_id", "prominence"):
            value = getattr(change, attr)
            if value is None:
                continue
            if (
                attr == "age"
                and not self.engine
                and (value == 0 or (not created and character.age is not None))
            ):
                # W10: an age on record moves with the world's years (`engine.world.lives`),
                # never by a scene's word: a scene that tells ten years gone by would count
                # them twice. The form asks every character's age (F3, `CharacterChange`),
                # so one that differs is passed over, not refused. Nor is 0 an age a scene
                # gives: it is what a model writes in a number it was made to fill.
                continue
            setattr(character, attr, value)
        if change.lifespan_years:
            self.longer_life(character, change.lifespan_years)
        if look is not None:
            character.appearance = look
            character.look_version += 1  # M5: the portrait is drawn once more
        if change.location_id is not None:
            if change.location_id not in self.state.places:
                self.reject(subject, "location", f"no place {change.location_id!r}")
            elif self.door is not None and not self.door.admits(self.state, character.id):
                # W10. The scene says where its own people go: only the world moves anyone else.
                self.reject(subject, "location", _ELSEWHERE)
            elif self.door is not None and self.door.comes(self.state, character.id):
                # Someone who could walk over comes to where the scene plays, and nowhere else.
                if self.door.plays_at(self.state, change.location_id):
                    self.came.setdefault(character.id, character.location_id or "")
                    character.location_id = change.location_id
                else:
                    self.reject(subject, "location", _ELSEWHERE)
            else:
                character.location_id = change.location_id
        if change.faction_id is not None:
            self.membership(character, change)
        for shift in change.attitudes:
            self.attitude(character, shift)
        if change.condition is not None:
            self.condition(character, change)
        cause = self.cause_of(subject, change)
        # A new character starts in the status it was created with; see `new_character`.
        if not created and (change.status is not None or change.death_certainty is not None):
            self.character_status(character, change, cause)
        player = self.state.player_id
        if change.meets_player and not (
            self.door is None or self.door.touches(self.state, character.id)
        ):
            # W10. Nobody meets someone who isn't there.
            self.reject(subject, "meeting", _ELSEWHERE)
        elif change.meets_player:
            if player not in character.met_by:
                # W6: a first meeting. What comes to them from here on is news, and what came
                # before is who they are (`engine.world.lives`). A scene that says again of
                # someone already known that the two met leaves this alone: the news they
                # have is still theirs to tell (the first live story of a homecoming lost it
                # all this way, 2026-11-13).
                character.met_s = self.state.world_s
            # The two are together now, wherever the scene goes on to end.
            character.seen_s = self.state.world_s
            _add(character.met_by, player)
            _add(character.known_by, player)
        if change.known_to_player:
            _add(character.known_by, player)
        if change.rulings and self.engine_only(subject, "rulings"):
            self.rulings(character, change)
        if change.gains and self.engine_only(subject, "gains"):
            for gain in change.gains:
                character.sheet.growth.append(
                    gain.model_copy(update={"turn": self.turn, "world_s": self.state.world_s})
                )
        if change.backstory and self.engine_only(subject, "backstory"):
            for claim in change.backstory:
                character.sheet.backstory.append(BackstoryClaim(text=claim, turn=self.turn))
        if change.powers and self.engine_only(subject, "powers"):
            for power_change in change.powers:
                self.power(character, power_change)
        if change.techniques and self.engine_only(subject, "techniques"):
            for technique in change.techniques:
                known = character.sheet.technique(technique.id)
                if known is None:
                    character.sheet.techniques.append(technique.model_copy(deep=True))
                else:
                    # A4. A technique they have keeps what it is: only how well they have it
                    # moves, with use and practice.
                    known.mastery, known.uses = technique.mastery, technique.uses
        if change.ladders and self.engine_only(subject, "ladders"):
            for position in change.ladders:
                self.ladder(character, position)
        if change.rung:
            # G18: settled once the delta's own rungs are in (`stand`).
            self.claimed[character.id] = change.rung
        if change.practice and self.engine_only(subject, "practice"):
            for practice in change.practice:
                kept = [p for p in character.sheet.practice if p.key != practice.key]
                character.sheet.practice = [*kept, practice.model_copy()]
        if change.talent_rulings and self.engine_only(subject, "talent rulings"):
            # A4, A9. Ruled once: a thing already ruled on keeps its ruling.
            when = {"turn": self.turn, "world_s": self.state.world_s}
            for ruling in change.talent_rulings:
                if character.sheet.talent_ruling(ruling.key) is None:
                    character.sheet.talent_rulings.append(ruling.model_copy(update=when))
        if change.bridges and self.engine_only(subject, "bridges"):
            when = {"turn": self.turn, "world_s": self.state.world_s}
            for bridge in change.bridges:
                character.sheet.bridges.append(bridge.model_copy(update=when))
        if change.axes is not None and self.engine_only(subject, "axes"):
            # F1: only someone the engine makes real comes with their measure; anyone known
            # keeps theirs.
            if created:
                character.sheet.axes = change.axes.model_copy()
            else:
                self.reject(subject, "axes", "a known character's measure doesn't change here")
        if change.attributes is not None and self.engine_only(subject, "attributes"):
            # F1, G13: like their measure, only someone the engine makes real comes with a body.
            if created:
                character.sheet.attributes = change.attributes.model_copy()
            else:
                self.reject(subject, "attributes", "a known character's body doesn't change here")
        if change.skills and self.engine_only(subject, "skills"):
            for skill in change.skills:
                wanted = skill.name.casefold()
                kept = [s for s in character.sheet.skills if s.name.casefold() != wanted]
                character.sheet.skills = [*kept, skill.model_copy()]

    def new_character(self, change: CharacterChange) -> Character | None:
        """A character the story hasn't met before. One can start dead or missing, such as a body
        that is found or a father who vanished years ago: that is news, not a death this turn
        caused. Everything else, from location to attitudes, applies like a change to a known
        character."""
        subject = f"character {change.id}"
        if not is_real_name(change.name):
            self.reject(subject, "create", "a new character needs a name (C1)")
            return None
        status = change.status or CharacterStatus.ALIVE
        certainty = None
        if status is CharacterStatus.DEAD:
            certainty = change.death_certainty or DeathCertainty.CONFIRMED
        character = Character(
            id=change.id,
            name=change.name,
            prominence=change.prominence or Prominence.MINOR,
            status=status,
            death_certainty=certainty,
            origin=self.origin,
        )
        self.state.characters[character.id] = character
        self.created.add(character.id)
        return character

    def family(self, change: CharacterChange) -> None:
        """N6: parents and a child on the way, once everyone in the delta is there, so a child
        and their parent can arrive in the same scene in either order."""
        character = self.state.characters.get(change.id)
        if character is None:
            return  # its creation was refused
        if change.parent_ids:
            self.parents(character, change.parent_ids)
        if change.expecting is not None:
            self.expecting(character, change.expecting)

    def parents(self, character: Character, parent_ids: list[str]) -> None:
        """N6: parents are added, never taken back, two at most, and never a descendant. The
        player character's own family is drafted, claimed by the player (N4) or born in play,
        never the narrator's to make up."""
        subject = f"character {character.id}"
        player = self.state.player_id
        if character.id == player and not self.engine:
            self.reject(subject, "parents", "the player character's parents aren't the narrator's")
            return
        for parent_id in parent_ids:
            if parent_id in character.parent_ids:
                continue
            if parent_id == player and not self.engine:
                self.reject(
                    subject, "parents", "the player character's children aren't the narrator's"
                )
            elif parent_id == character.id or parent_id not in self.state.characters:
                self.reject(subject, "parents", f"no one else called {parent_id!r}")
            elif len(character.parent_ids) >= 2:
                self.reject(subject, "parents", "two parents at most")
            elif parent_id in descendants(self.state, character.id):
                self.reject(subject, "parents", f"{parent_id!r} descends from them")
            else:
                character.parent_ids.append(parent_id)

    def expecting(self, character: Character, expecting: Expecting) -> None:
        """N6: a child on the way, due a gestation from now, or a pregnancy that ended without a
        birth. Both parents are adults (F3)."""
        subject = f"character {character.id}"
        now = self.state.world_s
        other_id = expecting.other_parent_id
        other = self.state.characters.get(other_id or "")
        if expecting.ended:
            if character.expecting is None:
                self.reject(subject, "expecting", "they carry no child")
            character.expecting = None  # its birth, still pending, finds nobody expecting
        elif not character.alive:
            self.reject(subject, "expecting", "the dead carry no child")
        elif character.expecting is not None:
            self.reject(subject, "expecting", "they already carry a child")
        elif other_id is not None and (other is None or other_id == character.id):
            self.reject(subject, "expecting", f"no other parent called {other_id!r}")
        elif problem := adult_problem(character) or (other and adult_problem(other)):
            self.reject(subject, "expecting", f"only adults have children here ({problem})")
        else:
            character.expecting = Pregnancy(
                other_parent_id=other_id, conceived_s=now, due_s=now + GESTATION_S
            )

    def membership(self, character: Character, change: CharacterChange) -> None:
        if change.faction_id not in self.state.factions:
            self.reject(f"character {character.id}", "faction", f"no faction {change.faction_id!r}")
            return
        for m in character.memberships:
            if m.faction_id == change.faction_id:
                if change.rank is not None:
                    m.rank = change.rank
                return
        character.memberships.append(
            Membership(faction_id=change.faction_id, rank=change.rank or "")
        )

    def attitude(self, character: Character, shift: AttitudeShift) -> None:
        toward = shift.toward_id or self.state.player_id
        if toward not in self.state.characters or toward == character.id:
            self.reject(f"character {character.id}", "attitude", f"no one else called {toward!r}")
            return
        if not self.engine and self.in_scene is not None and character.id not in self.in_scene:
            # W4. Only what reaches someone moves how they feel, and the world carries it (W2).
            self.reject(
                f"character {character.id}",
                "attitude",
                "they aren't in the scene: the engine moves how they feel once word reaches them",
            )
            return
        attitudes = character.sheet.disposition.attitudes
        current = attitudes.setdefault(toward, Attitude())
        current.affinity = _clamp(
            current.affinity + self.allowed(character.id, toward, "affinity", shift.affinity),
            AFFINITY_MIN,
            AFFINITY_MAX,
        )
        current.fear = _clamp(
            current.fear + self.allowed(character.id, toward, "fear", shift.fear),
            FEAR_MIN,
            FEAR_MAX,
        )
        current.trust = _clamp(
            current.trust + self.allowed(character.id, toward, "trust", shift.trust),
            TRUST_MIN,
            TRUST_MAX,
        )
        if shift.grudge:
            current.grudges.append(Grudge(reason=shift.grudge, since_turn=self.turn))
        if shift.attraction and self.engine_only(f"character {character.id}", "attraction"):
            # W17. Their own heart, which rests from the moment it moves.
            current.attraction = _clamp(current.attraction + shift.attraction, 0, 100)
            current.heart_moved_s = self.state.world_s

    def allowed(self, character_id: str, toward: str, axis: str, amount: int) -> int:
        """How much of a shift sticks. The engine moves attitudes freely; the narrator by at most
        `NARRATOR_ATTITUDE_CAP` per attitude per delta, however it splits the shift (W4)."""
        if self.engine or amount == 0:
            return amount
        key = (character_id, toward, axis)
        used = self.nudged.get(key, 0)
        total = _clamp(used + amount, -NARRATOR_ATTITUDE_CAP, NARRATOR_ATTITUDE_CAP)
        self.nudged[key] = total
        return total - used

    def condition(self, character: Character, change: CharacterChange) -> None:
        """Health, wounds and passing states. Only the engine harms the player character (N6,
        `engine.injuries`): every blow and fall that can is settled before the scene is told, so
        the narrator may show them heal but never hurt them, unless `may_hurt_player` says
        something recorded this turn did. A new wound on an unhurt body leaves it hurt."""
        subject = f"character {character.id}"
        condition = character.sheet.condition
        update = change.condition
        guarded = (
            not self.engine and not self.may_hurt_player and character.id == self.state.player_id
        )
        if update.health is not None:
            if guarded and update.health.worse_than(condition.health):
                self.reject(subject, "harm", "only the engine harms the player character (N6)")
            else:
                condition.set_health(update.health)
        if update.wounds:
            if guarded:
                self.reject(subject, "wound", "only the engine wounds the player character (N6)")
            else:
                condition.wounds.extend(Wound(text=w) for w in update.wounds)
                if condition.health is Health.UNHURT:
                    condition.set_health(Health.HURT)
        if update.lasting_wounds and self.engine_only(subject, "lasting wound"):
            condition.wounds.extend(Wound(text=w, lasting=True) for w in update.lasting_wounds)
        cleared = {s.casefold() for s in update.cleared_states}
        condition.states = [s for s in condition.states if s.name.casefold() not in cleared]
        for state_name in update.states:
            if guarded and names_injury(state_name):
                self.reject(subject, "injury", "only the engine hurts the player character (N6)")
            elif is_real_name(state_name) and not any(
                s.name.casefold() == state_name.casefold() for s in condition.states
            ):
                condition.states.append(PassingState(name=state_name))

    def character_status(
        self, character: Character, change: CharacterChange, cause: Cause | None
    ) -> None:
        subject = f"character {character.id}"
        before = character.status
        target = change.status or before
        certainty = change.death_certainty
        known = self.known_to_player(character.id, change.known_to_player or change.meets_player)
        if before is CharacterStatus.DEAD and target is CharacterStatus.DEAD:
            if certainty is None or certainty is character.death_certainty:
                return
            if certainty is DeathCertainty.PRESUMED:
                self.reject(subject, "death", "a confirmed death never becomes presumed")
                return
            if not self.engine_only(subject, "confirm death"):
                return
            character.death_certainty = certainty
            character.status_history.append(
                self.history("dead", cause, known=known, from_status="dead")
            )
            self.widowed(character)
            return
        if before is CharacterStatus.DEAD:
            if not self.engine_only(subject, "return from death"):
                return
            if cause is None:
                self.reject(subject, "return from death", "the dead stay dead without a cause")
                return
            problem = death_reversal_problem(self.state, character, cause)
            if problem:
                self.reject(subject, "return from death", problem)
                return
            character.status = target
            character.death_certainty = None
        elif target is CharacterStatus.DEAD:
            if not self.engine:
                self.reject(subject, "death", "deaths come from the engine's resolution (F4)")
                return
            character.status = target
            character.death_certainty = certainty or DeathCertainty.CONFIRMED
        elif target is not before:
            character.status = target
        else:
            return
        presumed = character.death_certainty is DeathCertainty.PRESUMED
        character.status_history.append(
            self.history(
                target.value, cause, known=known, from_status=before.value, presumed=presumed
            )
        )
        self.widowed(character)

    def widowed(self, character: Character) -> None:
        """W17. A death ends the romances of the dead. One that is only presumed ends none:
        the record still holds that they may be alive."""
        if character.alive or character.death_certainty is not DeathCertainty.CONFIRMED:
            return
        bonds.end_by_death(self.state, character, turn=self.turn, world_s=self.state.world_s)

    def rulings(self, character: Character, change: CharacterChange) -> None:
        sheet = character.sheet
        for ruling in change.rulings:
            settled = sheet.ruling(ruling.topic, ruling.power_id)
            if settled is not None:
                if (settled.answer, settled.holds) != (ruling.answer, ruling.holds):
                    self.reject(
                        f"character {character.id}",
                        f"ruling {ruling.topic}",
                        f"settled for good on turn {settled.turn} (A9)",
                    )
                continue
            sheet.rulings.append(
                ruling.model_copy(update={"turn": self.turn, "world_s": self.state.world_s})
            )

    def power(self, character: Character, change: PowerChange) -> None:
        """A power's cooldown, and details settled once and never changed (A9)."""
        subject = f"character {character.id}"
        power = character.sheet.power(change.id)
        if power is None:
            self.reject(subject, f"power {change.id}", "no such power")
            return
        if change.ready_at_personal_s is not None:
            power.ready_at_personal_s = change.ready_at_personal_s
        if change.hit_mode is not None:
            if power.time is None:
                self.reject(subject, f"power {change.id} hit mode", "not a power over time")
            elif power.time.hit_mode is None:
                power.time.hit_mode = change.hit_mode
            elif power.time.hit_mode is not change.hit_mode:
                self.reject(subject, f"power {change.id} hit mode", "settled for good (A9)")
        for setting in change.settings:
            settled = power.settings.get(setting.key)
            if settled is None:
                power.settings[setting.key] = setting.value
            elif settled != setting.value:
                self.reject(
                    subject, f"power {change.id} setting {setting.key}", "settled for good (A9)"
                )

    def ladder(self, character: Character, position: LadderPosition) -> None:
        """A new place on one of the world's ladders (G19), or strength hidden (G20)."""
        subject = f"character {character.id}"
        ladder = self.state.bible.ladder(position.ladder_id)
        if ladder is None:
            self.reject(subject, f"ladder {position.ladder_id}", "no such ladder")
            return
        if position.rung >= len(ladder.rungs):
            self.reject(subject, f"ladder {position.ladder_id}", "no such rung")
            return
        if position.shown_rung is not None and position.shown_rung > position.rung:
            self.reject(subject, f"ladder {position.ladder_id}", "can't show more than they have")
            return
        kept = [p for p in character.sheet.ladders if p.ladder_id != position.ladder_id]
        character.sheet.ladders = [*kept, position.model_copy()]

    def rung(self, new: NewRung) -> None:
        """G18, G7. A rung the story put above a ladder's highest, where the story has reached
        that far (`engine.path.beyond_problem`). It stands as far above the last rung as the
        ladder's rungs usually lie apart, is as loud to break through to, and lists no way
        there: nobody has told one. How long whoever stands on it lives the record can't say,
        so old age takes none of them (`engine.world.old_age`). A second rung in the same
        delta is refused like any other above a top nobody has heard of or climbed to.

        Whoever came into the story in this same delta can stand on it, three at most: that
        is who they are. Nobody already on record is put there (A4): they climb to it like
        anyone, the player character by their own work (G19) and everyone else over the
        years (W6)."""
        subject = f"ladder {new.ladder_id}"
        ladder = self.state.bible.ladder(new.ladder_id)
        if ladder is None:
            self.reject(subject, "rung", "no such ladder")
            return
        problem = path_mod.beyond_problem(self.state, ladder, new.name)
        if problem:
            self.reject(subject, f"rung {new.name}", problem)
            return
        tier = path_mod.above_tier(ladder)
        assert tier is not None  # `beyond_problem` found room on the scale
        # G7: the discovery breaks the open rules that held the ladder at its old top, for
        # everyone. They are struck: from now on the ladder itself says how far it goes, and
        # a rule that nobody passes the old top would rule out every climb to the new rung.
        struck = {rule.id for rule in path_mod.ceilings(self.state, ladder)}
        bible = self.state.bible
        bible.rules = [rule for rule in bible.rules if rule.id not in struck]
        for kind in bible.extraordinary:
            kind.rule_ids = [rule_id for rule_id in kind.rule_ids if rule_id not in struck]
        ladder.rungs.append(
            Rung(
                name=new.name,
                tier=tier,
                description=new.description.strip(),
                loud=ladder.rungs[-1].loud,
                added_s=self.state.world_s,
            )
        )
        index = len(ladder.rungs) - 1
        self.came[ladder.id, index] = 0
        for character_id in dict.fromkeys(new.stands):
            character = self.state.characters.get(character_id)
            if character is None:
                self.reject(f"character {character_id}", f"rung {new.name}", _NOBODY_LIFTED)
                continue
            self.stands(character, ladder, index)

    def stand(self) -> None:
        """G18, A4. Someone the story brings in comes standing where their change says: on a
        rung the world's ladders have, this delta's own included, by its name or by a few words
        that hold that one name (`path.rung_said`). Only someone this delta created, since
        nobody on record is lifted: they climb, the player character by their own work (G19)
        and everyone else over the years (W6). For someone on record, a change that says their
        own rung or one under it says nothing new, and moves nobody down."""
        for character_id, name in self.claimed.items():
            character = self.state.characters.get(character_id)
            if character is None:
                continue
            found = path_mod.rung_said(self.state, name)
            if found is None:
                self.reject(f"character {character_id}", f"rung {name}", "no ladder has that rung")
                continue
            ladder, index = found
            if path_mod.own_rung(character, ladder.id) >= index:
                continue
            self.stands(character, ladder, index)

    def stands(self, character: Character, ladder: PowerLadder, index: int) -> None:
        """Puts someone this delta brought into the story on a rung, with the ladder's axis at
        the rung's tier: a rung is the world's name for a tier on its axis (G18). At most
        `CAME_WITH` come standing on a rung this same delta added."""
        subject, rung = f"character {character.id}", ladder.rungs[index]
        if character.id not in self.created:
            self.reject(subject, f"rung {rung.name}", _NOBODY_LIFTED)
            return
        new = (ladder.id, index)
        if new in self.came:
            if self.came[new] >= path_mod.CAME_WITH:
                self.reject(subject, f"rung {rung.name}", "three come with a rung at most")
                return
            self.came[new] += 1
        sheet = character.sheet
        kept = [p for p in sheet.ladders if p.ladder_id != ladder.id]
        sheet.ladders = [*kept, LadderPosition(ladder_id=ladder.id, rung=index)]
        setattr(sheet.axes, ladder.axis.value, max(sheet.axes.on(ladder.axis), rung.tier))

    def time_effect(self, effect: ActiveTimeEffect) -> None:
        """W10a. A time power taking hold, replacing the same power's earlier effect. Effects that
        have run out on their user's clock are cleared."""
        subject = f"character {effect.character_id}"
        if not self.engine_only(subject, "time effect"):
            return
        character = self.state.characters.get(effect.character_id)
        if character is None or character.sheet.power(effect.power_id) is None:
            self.reject(subject, f"time effect {effect.power_id}", "no such power")
            return
        same = (effect.character_id, effect.power_id)
        self.state.time_effects = [
            e
            for e in self.state.time_effects
            if (e.character_id, e.power_id) != same and not effect_over(self.state, e)
        ]
        if not effect_over(self.state, effect):
            self.state.time_effects.append(effect.model_copy())

    # --- records ----------------------------------------------------------------------------

    def bond(self, change: BondChange) -> None:
        """W17. A romance comes to a stage, which only the engine decides. The first change
        between two people opens their bond, between living adults (F3) who aren't close
        family. After that it moves
        forward, or to its end, and one that is over stays over (`bonds.can_move`)."""
        subject = f"bond {change.a_id}/{change.b_id}"
        if not self.engine_only(subject, "romance"):
            return
        first = self.state.characters.get(change.a_id)
        second = self.state.characters.get(change.b_id)
        if first is None or second is None or first.id == second.id:
            self.reject(subject, "romance", "no such two people")
            return
        step = BondStep(
            stage=change.stage,
            turn=self.turn,
            world_s=self.state.world_s,
            by_id=change.by_id,
            how=change.how,
        )
        current = bonds.live(self.state, first.id, second.id)
        if current is None:
            if change.stage is BondStage.OVER:
                self.reject(subject, "romance", "there is nothing between them to end")
            elif not (first.alive and second.alive):
                self.reject(subject, "romance", "the dead start no romance")
            elif problem := adult_problem(first) or adult_problem(second):
                self.reject(subject, "romance", f"a romance is between adults ({problem})")
            elif bonds.kin(self.state.characters, first.id, second.id):
                self.reject(subject, "romance", "the two are close family")
            else:
                bond_id = self.state.new_id("bond")
                self.state.bonds[bond_id] = Bond(
                    id=bond_id, a_id=first.id, b_id=second.id, stage=change.stage, steps=[step]
                )
            return
        if current.stage is change.stage:
            return
        if not bonds.can_move(current, change.stage):
            self.reject(
                subject,
                "romance",
                f"a romance doesn't go from {current.stage.value} to {change.stage.value}",
            )
            return
        current.stage = change.stage
        current.end = BondEnd.PARTED if change.stage is BondStage.OVER else None
        current.steps.append(step)

    def fact(self, change) -> None:
        known_by = [i for i in change.known_by if i in self.state.characters]
        if change.known_to_player:
            _add(known_by, self.state.player_id)
        fact = Fact(
            id=self.state.new_id("fact"),
            text=change.text,
            kind=change.kind,
            importance=change.importance,
            is_true=change.is_true,
            subject_ids=change.subject_ids,
            known_by=list(dict.fromkeys(known_by)),
            turn=self.turn,
            world_s=self.state.world_s,
            timeline_id=self.state.timeline_id,
            origin=self.origin,
        )
        self.state.facts[fact.id] = fact

    def item(self, change: ItemChange) -> None:
        """C10. One thing changing hands, by `engine.possessions`: nobody gives what they don't
        have, and what leaves the giver reaches the receiver."""
        reason = possessions.move(self.state, change, turn=self.turn, origin=self.origin.kind)
        if reason is not None:
            sides = f"{change.from_id or WORLD} to {change.to_id or WORLD}"
            self.reject(f"character {sides}", f"item {change.name}", reason)

    def lead(self, change) -> None:
        now = self.state.world_s
        lead = Lead(
            id=self.state.new_id("lead"),
            text=change.text,
            kind=change.kind,
            from_id=change.from_id if change.from_id in self.state.characters else None,
            place_id=change.place_id if change.place_id in self.state.places else None,
            offered_turn=self.turn,
            offered_s=now,
            expires_s=now + change.expires_in_s if change.expires_in_s else None,
        )
        self.state.leads[lead.id] = lead

    def goal_over(self, change: GoalOver) -> None:
        """N2: a goal that is over closes, on a turn the player acted. One that repeats another
        closes into the older of the two, so the words the player set first stay. Nothing
        rewrites a goal."""
        subject = f"goal {change.goal_id}"
        if not self.player_acted:
            self.reject(subject, change.how.value, "the player didn't act this turn")
            return
        goal = self.state.goals.get(change.goal_id)
        if goal is None or goal.status is not GoalStatus.ACTIVE:
            self.reject(subject, change.how.value, "not an active goal")
            return
        if change.how is not GoalEnd.REPEATS:
            achieved = change.how is GoalEnd.ACHIEVED
            goal.status = GoalStatus.ACHIEVED if achieved else GoalStatus.FAILED
            goal.closed_turn = self.turn
            goal.closed_s = self.state.world_s
            return
        other = self.state.goals.get(change.same_as or "")
        if other is None or other.id == goal.id or other.status is not GoalStatus.ACTIVE:
            self.reject(subject, change.how.value, "it repeats no other active goal")
            return
        older, later = sorted((goal, other), key=lambda g: (g.set_turn, natural_key(g.id)))
        later.status = GoalStatus.MERGED
        later.merged_into = older.id
        later.closed_turn = self.turn
        later.closed_s = self.state.world_s
        # What the story did with the later one, it did with the goal that stays.
        if later.moved_turn is not None and later.moved_turn >= (older.moved_turn or 0):
            older.moved_turn = later.moved_turn
            older.progress = later.progress or older.progress

    def goal_moved(self, change: GoalMoved) -> None:
        """N2, C6: where a goal stands after this scene, as far as the character knows. It is
        kept beside the goal, whose own words nothing rewrites, and the goal the story last
        moved is the thread the player follows (`engine.director.goals.followed`)."""
        subject = f"goal {change.goal_id}"
        goal = self.state.goals.get(change.goal_id)
        if goal is None or goal.status is not GoalStatus.ACTIVE:
            self.reject(subject, "moved", "not an active goal")
            return
        progress = " ".join(change.progress.split())[:MAX_PROGRESS].strip()
        if not progress or normalize(progress) == normalize(goal.text):
            self.reject(subject, "moved", "it says nothing beyond the goal's own words")
            return
        goal.progress = progress
        goal.moved_turn = self.turn

    def rule(self, change: RuleChange) -> None:
        subject = f"rule {change.rule_id}"
        if not self.engine_only(subject, "change"):
            return
        rule = self.state.bible.rule(change.rule_id)
        if rule is None:
            self.reject(subject, "change", "no such rule")
            return
        if rule.fixed:
            self.reject(subject, "change", "a fixed rule never changes (G7)")
            return
        problem = cause_problem(
            self.state,
            change.cause,
            subject_id=None,
            since_s=0,
            allowed={CauseMechanism.DISCOVERY},
        )
        if problem:
            self.reject(subject, "change", problem)
            return
        rule.text = change.text


def _add(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
