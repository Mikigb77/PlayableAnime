"""Apply a proposed `StateDelta` to the world, enforcing C1 (B5 step 6).

The model proposes; this module decides what sticks. A change that breaks an invariant is
rejected, not applied, and the rejection says why, so the turn can log it and the continuity check
can repair the next scene (C5). Nothing raises for a bad proposal: a forgetful or injected model
can't break the world (A7), and the rest of the delta still applies.

Who may change what:

- **Narrator and engine:** new characters, factions and places (with real names), descriptions,
  locations, small attitude nudges, condition, memberships, facts, items, leads, non-terminal
  status changes, the scene's end and the summary. A lasting change to how a known character
  looks (`look_change`) moves their `look_version` on (M5, `engine.looks`).
- **Engine only:** deaths, destroyed factions and ruined places (resolve records the outcome
  before narration, F4); anything that undoes one, which also needs a recorded `Cause`; faction
  reputation (W3); rulings (A9), gains (A4), accepted backstory (N4) and rule changes (G7); and
  the state of powers (cooldowns and settled details, never changed once set), skills,
  techniques, ladders, practice and time effects (A4, G19, G20, W10a).
"""

from dataclasses import dataclass, field
from enum import StrEnum

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
    AttitudeShift,
    CharacterChange,
    FactionChange,
    ItemChange,
    PlaceChange,
    PowerChange,
    RuleChange,
    StateDelta,
)
from engine.invariants import (
    ancestry,
    cause_problem,
    death_reversal_problem,
    faction_revival_problem,
    is_real_name,
    place_rebuild_problem,
)
from engine.looks import look_after
from engine.state.cast import (
    Character,
    CharacterStatus,
    DeathCertainty,
    Faction,
    FactionStatus,
    Membership,
    Place,
    PlaceStatus,
    Prominence,
)
from engine.state.records import (
    Cause,
    CauseMechanism,
    Fact,
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
    Item,
    ItemKind,
    LadderPosition,
    PassingState,
    Wound,
)
from engine.state.world import ActiveTimeEffect, WorldState
from engine.timekeeping import effect_over

# How far one narrated scene can move an attitude on its own (W4). The engine moves them further.
NARRATOR_ATTITUDE_CAP = 10


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
    state: WorldState
    rejected: tuple[Rejection, ...] = field(default_factory=tuple)


def apply_delta(
    state: WorldState, delta: StateDelta, ctx: TurnContext, *, source: DeltaSource
) -> Applied:
    """Apply `delta` to a copy of `state` at the current world time, on behalf of `source`, and
    stamp what it records with `ctx.turn`. It never raises for a bad proposal: refused changes
    come back in `Applied.rejected`, and the rest still applies. It doesn't touch `state.turn`.

    Places and factions go first, so characters in the same delta can refer to them.
    """
    return apply_in_place(state.model_copy(deep=True), delta, ctx, source=source)


def apply_in_place(
    state: WorldState, delta: StateDelta, ctx: TurnContext, *, source: DeltaSource
) -> Applied:
    """`apply_delta` on a working copy the caller owns, such as `play_out`'s, which it changes
    in place instead of copying the whole state again. `Applied.state` is that same object."""
    applier = _Applier(state, source, ctx.turn)
    for change in delta.places:
        applier.place(change)
    for change in delta.factions:
        applier.faction(change)
    for change in delta.characters:
        applier.character(change)
    for fact in delta.facts:
        applier.fact(fact)
    for item in delta.items:
        applier.item(item)
    for lead in delta.leads:
        applier.lead(lead)
    for rule in delta.rule_changes:
        applier.rule(rule)
    for effect in delta.time_effects:
        applier.time_effect(effect)
    if delta.scene_end is not None:
        end = delta.scene_end
        new = applier.state
        with_player = _with_player(new)
        new.scene = SceneFrame(
            place_id=end.place_id if end.place_id in new.places else new.scene.place_id,
            present_ids=[i for i in end.present_ids if i in new.characters],
            positions=end.positions,
            props=end.props,
            ended_on=end.ended_on,
            encounter=new.scene.encounter,
        )
        if end.place_id in new.places:
            _gather(new, end.place_id, with_player)
    if delta.summary:
        applier.state.summary = delta.summary
    return Applied(applier.state, tuple(applier.rejected))


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


def _gather(state: WorldState, place_id: str, with_player: set[str]) -> None:
    """R3, C2. The scene ends at `place_id`, so the player character is there, and so is everyone
    living in the scene who came with them: the world places witnesses and events where people
    are (W2, W16). Someone already somewhere inside that place, such as at the well in the
    courtyard the scene names, stays where they are. The narrator naming someone far off, or
    missing, as present doesn't move them: only the engine's own record does."""
    for character_id in dict.fromkeys([state.player_id, *state.scene.present_ids]):
        character = state.characters.get(character_id)
        if character is None or not character.alive:
            continue
        if character_id != state.player_id and (
            character.status is not CharacterStatus.ALIVE or character_id not in with_player
        ):
            continue
        if place_id not in ancestry(state.places, character.location_id):
            character.location_id = place_id


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class _Applier:
    def __init__(self, state: WorldState, source: DeltaSource, turn: int) -> None:
        self.state = state
        self.source = source
        self.turn = turn
        self.rejected: list[Rejection] = []
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
            if value is not None:
                setattr(character, attr, value)
        if look is not None:
            character.appearance = look
            character.look_version += 1  # M5: the portrait is drawn once more
        if change.location_id is not None:
            if change.location_id in self.state.places:
                character.location_id = change.location_id
            else:
                self.reject(subject, "location", f"no place {change.location_id!r}")
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
        if change.meets_player:
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
                if character.sheet.technique(technique.id) is None:
                    character.sheet.techniques.append(technique.model_copy(deep=True))
        if change.ladders and self.engine_only(subject, "ladders"):
            for position in change.ladders:
                self.ladder(character, position)
        if change.practice and self.engine_only(subject, "practice"):
            for practice in change.practice:
                kept = [p for p in character.sheet.practice if p.key != practice.key]
                character.sheet.practice = [*kept, practice.model_copy()]
        if change.axes is not None and self.engine_only(subject, "axes"):
            # F1: only someone the engine makes real comes with their measure; anyone known
            # keeps theirs.
            if created:
                character.sheet.axes = change.axes.model_copy()
            else:
                self.reject(subject, "axes", "a known character's measure doesn't change here")
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
        return character

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
        condition = character.sheet.condition
        update = change.condition
        if update.health is not None:
            condition.health = update.health
        condition.wounds.extend(Wound(text=w) for w in update.wounds)
        cleared = {s.casefold() for s in update.cleared_states}
        condition.states = [s for s in condition.states if s.name.casefold() not in cleared]
        for state_name in update.states:
            if is_real_name(state_name) and not any(
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
        owner_id = change.owner_id or self.state.player_id
        owner = self.state.characters.get(owner_id)
        subject = f"character {owner_id}"
        if owner is None:
            self.reject(subject, f"item {change.name}", "no such character")
            return
        items = owner.sheet.resources.items
        wanted = change.name.casefold()
        found = next(
            (
                i
                for i in items
                if (change.item_id and i.id == change.item_id)
                or (not change.item_id and i.name.casefold() == wanted)
            ),
            None,
        )
        if found is None:
            if change.quantity <= 0:
                self.reject(subject, f"item {change.name}", "they don't have it")
                return
            found = Item(
                id=change.item_id or self.state.new_id("item"),
                name=change.name,
                kind=change.kind or ItemKind.OTHER,
                quantity=0,
            )
            items.append(found)
        found.quantity += change.quantity
        if change.description is not None:
            found.description = change.description
        if change.kind is not None:
            found.kind = change.kind
        if change.carried is not None:
            found.carried = change.carried
        if found.quantity <= 0:
            items.remove(found)

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
