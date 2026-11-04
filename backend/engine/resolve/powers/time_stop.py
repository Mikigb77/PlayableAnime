"""Time stop (W10a, G22, A9): the user's clock runs while the world's stands still.

Three conventions every setting shares bend physics just enough for the power to work and be fun:

- **The user moves and breathes freely.** The air moves with them, so nothing the player didn't
  raise, such as friction or a wall of frozen air, gets in the way of what they do in the stop.
- **What they hold joins the stop.** What they pick up moves with them, as heavy as ever, and what
  they let go freezes again just past their reach. A person they carry stays frozen inside and
  knows nothing of it.
- **The power shields its user while the stop lasts,** and only then: once time restarts, the
  blast of their own hit is as real for them as for anyone else.

How hard stopped-time hits land is a setting of the power, decided with the world and never asked
of the player (A9), settled once and then followed as logic (A2):

- **Normal force:** a blow lands as it would have; the target just couldn't defend. A thrown stone
  hangs in the air and carries on at throwing speed when time restarts.
- **Relative speed:** whatever moved during the stop got where it is in no time at all, so it lands
  with overwhelming force: a blade goes through steel like butter, and a pebble arrives at close to
  the speed of light, 100 grams hitting like three megatons. Nothing caps it, a thrower too close
  dies in their own blast, and anything tougher than the hit survives it.
- **Untouchable:** frozen things can't be moved or changed until time restarts, so the stop is for
  moving, escaping and placing what the user already carries.

By default an overpowered stop hits at relative speed and a modest one with normal force (G22).
A technique found later can change how its throws land (A4, A9): released gradually, a stone
merges back into time carrying its motion, or lands as hard as the user chooses.
"""

from dataclasses import dataclass, field

from engine.contracts.delta import (
    CharacterChange,
    ConditionChange,
    FactionChange,
    PlaceChange,
    StateDelta,
)
from engine.contracts.intent import Contact, IntentStep
from engine.contracts.resolution import ProposedDeed
from engine.resolve.power import scale, standing
from engine.resolve.powers import force as force_mod
from engine.resolve.powers import sensing
from engine.resolve.words import cap, is_are, name, stems
from engine.state.cast import Character, CharacterStatus, DeathCertainty, FactionStatus, PlaceStatus
from engine.state.records import Trace, TraceKind
from engine.state.sheet import (
    GiftStrength,
    Health,
    HitMode,
    Power,
    PowerAxis,
    Ruling,
    RulingSource,
    TimeEffect,
)
from engine.state.world import WorldState

HIT_MODE = "hit_mode"  # the topic of the ruling on how hits land
MOVE_FROZEN = "move_frozen"  # the topic of the ruling on picking up frozen things
THROWS = "throws"  # a setting: "relative_speed" once a technique makes throws land that way
CONTROL = "control"  # a setting: "controlled" once the user can choose how hard hits land
STOP_IMMUNITY = "stop_immunity"  # a setting: "yes" when the user moves in others' stops
DRAIN = "drain"  # a setting: "heavy" when a yes came with a heavier drain (A9, G22)
RELATIVE = "relative_speed"
CONTROLLED = "controlled"
HEAVY = "heavy"
YES, NO = "yes", "no"

# A thrown thing lands about this far away when nothing says, if it lands where the thrower is.
DEFAULT_RANGE_M = 10.0
# Walking pace, to turn a route's travel time into a rough distance.
WALK_M_S = 1.4
UNKNOWN_DISTANCE_M = 1000.0
# A body this many tiers tougher than the hit takes it; within this of it, it's a close call.
TAKES_IT_MARGIN = 0.5
# A controlled hit lands this many tiers past the toughest target's body: hard enough, no more.
CONTROLLED_MARGIN = 1.0
# How long a stop or haste lasts, in its user's seconds, when the sheet doesn't say.
UNSTATED_LASTS_S = 5
# A crowd sees a body drop the moment time restarts (W13); alone, it may lie unfound a while.
CROWD_BODY_STRENGTH = 100
LONE_BODY_STRENGTH = 40

HIT_MODE_ANSWERS = {
    HitMode.RELATIVE_SPEED: (
        "Hits in stopped time land at relative speed: to the frozen world, whatever moved during"
        " the stop got there in no time at all, so it lands with overwhelming force."
    ),
    HitMode.NORMAL_FORCE: (
        "Hits in stopped time land with normal force: a blow lands as it would have, and a thrown"
        " stone hangs in the air and carries on at throwing speed when time restarts."
    ),
    HitMode.UNTOUCHABLE: (
        "Frozen things can't be moved or changed until time restarts, so the stop is for moving,"
        " escaping and placing what the user already carries."
    ),
}
MOVE_FROZEN_ANSWERS = {
    YES: "What the user picks up in stopped time joins the stop, as heavy as ever.",
    NO: "Frozen things can't be picked up or moved until time restarts.",
}
HEAVY_DRAIN_COST = "Each stop drains far more and takes twice as long to recover."

# Words a hindrance uses when it is about air, friction or breath, which the conventions settle.
_CONVENTION_STEMS = stems(
    "air friction drag wind breath breathe breathing suffocate vacuum resistance turbulence"
)
_YES = frozenset({"yes", "true", "immune"})
_IMMUNE_STEMS = stems("immune immunity unaffected unbound untouched")
_MOVES_STEMS = stems("move moves sees walks acts")
_TIME_STEMS = stems("time")
_STOP_STEMS = stems("stop stopped frozen freeze")


@dataclass
class Settlements:
    """What this plan has settled about powers so far, by (power id, key), before play_out
    records it, so a later step of the same plan already follows it."""

    values: dict[tuple[str, str], str] = field(default_factory=dict)

    def get(self, power: Power, key: str) -> str | None:
        found = self.values.get((power.id, key))
        if found is not None:
            return found
        if key == HIT_MODE and power.time is not None and power.time.hit_mode is not None:
            return power.time.hit_mode.value
        return power.settings.get(key)

    def put(self, power: Power, key: str, value: str) -> None:
        self.values[(power.id, key)] = value


def stops_time(power: Power | None) -> bool:
    return power is not None and power.time is not None and power.time.effect is TimeEffect.STOP


def immune(character: Character) -> bool:
    """W10a. Whether something on the sheet lets the character move or see in someone else's
    stopped time: a power's `stop_immunity` setting, or a power, technique, trait or item that
    says so. A stop of one's own that "only its user moves in" says nothing about anyone else's
    stop, so it only counts when it says immune or unaffected."""
    sheet = character.sheet
    if any(p.settings.get(STOP_IMMUNITY, "").strip().casefold() in _YES for p in sheet.powers):
        return True
    texts = [(f"{p.name} {p.description}", stops_time(p)) for p in sheet.powers]
    texts += [(f"{t.name} {t.effect}", False) for t in sheet.techniques]
    texts += [(f"{t.name} {t.description}", False) for t in sheet.traits]
    texts += [(f"{i.name} {i.description}", False) for i in sheet.resources.items if i.carried]
    for text, own_stop in texts:
        said = stems(text)
        if not (_TIME_STEMS & said and _STOP_STEMS & said):
            continue
        if _IMMUNE_STEMS & said or (not own_stop and _MOVES_STEMS & said):
            return True
    return False


def default_hit_mode(power: Power) -> HitMode:
    """G22. An overpowered stop hits at relative speed, a modest one with normal force."""
    strength = power.strength
    return HitMode.RELATIVE_SPEED if strength is GiftStrength.OVERPOWERED else HitMode.NORMAL_FORCE


def known_hit_mode(power: Power, settled: Settlements) -> HitMode | None:
    value = settled.get(power, HIT_MODE)
    return HitMode(value) if value else None


def ruling(
    power: Power,
    topic: str,
    *,
    question: str,
    answer: str,
    holds: bool,
    source: RulingSource,
    cost: str = "",
) -> Ruling:
    return Ruling(
        id=f"ruling-{power.id}-{topic}",
        topic=topic,
        power_id=power.id,
        question=question,
        answer=answer,
        holds=holds,
        cost=cost,
        source=source,
    )


def throw_mode(power: Power, mode: HitMode, settled: Settlements) -> HitMode:
    """How a stopped-time throw lands: the power's way, unless a technique merges throws back
    into time carrying their motion (A9)."""
    if settled.get(power, THROWS) == RELATIVE:
        return HitMode.RELATIVE_SPEED
    return mode


def controlled(power: Power, settled: Settlements) -> bool:
    return settled.get(power, CONTROL) == CONTROLLED


def lasts_s(power: Power) -> int:
    """How long one use of a stop or haste lasts on its user's own clock. A sheet that doesn't
    say gets a few heartbeats, so an unstated length never holds the world for good."""
    lasts = power.time.lasts_s if power.time is not None else None
    return UNSTATED_LASTS_S if lasts is None else lasts


def recharge_s(power: Power, settled: Settlements) -> int:
    """How long the power takes to recover after a stop ends, on the user's own clock."""
    base = (power.time.recharge_s or 0) if power.time is not None else 0
    return base * 2 if settled.get(power, DRAIN) == HEAVY else base


def drop_convention_hindrances(hindrances: list[str]) -> list[str]:
    """The user moves and breathes freely in their own stop: hindrances about air, friction or
    breath are settled by the conventions and never block what the world allows (A9, W10a)."""
    return [h for h in hindrances if not (stems(h) & _CONVENTION_STEMS)]


def contact_of(step: IntentStep) -> Contact:
    """A harmful step that doesn't say how it lands is a blow that stays in hand."""
    if step.contact is Contact.NONE and step.aim.harmful:
        return Contact.STRIKE
    return step.contact


@dataclass(frozen=True)
class StoppedHit:
    """How one step lands in stopped time."""

    mode: HitMode
    contact: Contact
    reason: str = ""  # how it lands, in the world's words
    blocked: str | None = None  # why it can't happen at all
    force_tier: float | None = None  # the hit's force on the world's tiers, when not the arm's
    overwhelming: bool = False  # the means are clearly enough, whatever the arm could do
    blast: force_mod.Blast | None = None
    controlled: bool = False


def stopped_hit(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    power: Power,
    mode: HitMode,
    settled: Settlements,
    targets: list[Character],
) -> StoppedHit:
    """W10a, A2. Follow the power's setting through to how the step lands."""
    contact = contact_of(step)
    if contact is Contact.LIFT:
        if mode is HitMode.UNTOUCHABLE:
            return StoppedHit(mode, contact, blocked=MOVE_FROZEN_ANSWERS[NO])
        mass = step.mass_kg
        can = force_mod.lift_kg(actor.sheet.attributes.strength)
        if mass is not None and mass > can:
            who = name(state, actor.id)
            return StoppedHit(
                mode,
                contact,
                blocked=f"It joins the stop as heavy as ever, more than {who} can lift.",
            )
        return StoppedHit(mode, contact, reason=MOVE_FROZEN_ANSWERS[YES])
    if contact is Contact.NONE:
        return StoppedHit(mode, contact)

    if contact is Contact.THROW:
        mode = throw_mode(power, mode, settled)
    if mode is HitMode.UNTOUCHABLE:
        if contact is Contact.THROW:
            return StoppedHit(
                HitMode.NORMAL_FORCE,
                contact,
                reason="The stone freezes past the hand and carries on at throwing speed when"
                " time restarts",
            )
        return StoppedHit(
            mode, contact, blocked="Frozen in stopped time, nothing can be touched or changed"
        )
    if mode is HitMode.NORMAL_FORCE:
        reason = ""
        if contact is Contact.THROW:
            reason = (
                "The stone hangs in the air and carries on at throwing speed when time restarts"
            )
        return StoppedHit(mode, contact, reason=reason)

    # Relative speed: overwhelming, unless the user has learned to choose how hard it lands.
    scale_ = state.bible.force
    default = force_mod.PEBBLE_KG if contact is Contact.THROW else force_mod.HELD_KG
    joules = force_mod.relative_speed_joules(force_mod.bounded_kg(step.mass_kg, default))
    tier = force_mod.tier_for(joules, scale_)
    if controlled(power, settled) and not step.full_force and targets:
        # Just past what the toughest target's body takes, never more than the power can give.
        needed = max(_tier(state, t) for t in targets) + CONTROLLED_MARGIN
        return StoppedHit(
            mode,
            contact,
            reason="Let back into time gradually, it lands exactly as hard as it needs to",
            force_tier=min(tier, needed),
            overwhelming=True,
            controlled=True,
        )
    if contact is Contact.THROW:
        hit_blast = force_mod.blast(joules)
        reason = (
            f"Released into time, it arrives at close to the speed of light and hits like"
            f" {hit_blast.words}"
        )
        return StoppedHit(
            mode, contact, reason=reason, force_tier=tier, overwhelming=True, blast=hit_blast
        )
    reason = "It arrives in no time at all and goes through like butter"
    return StoppedHit(mode, contact, reason=reason, force_tier=tier, overwhelming=True)


def _tier(state: WorldState, character: Character) -> float:
    measure = scale(state, PowerAxis.MIGHT, character)
    return standing(state, character, PowerAxis.MIGHT, measure).tier


def takes_it(state: WorldState, character: Character, force_tier: float) -> Health | None:
    """What a hit of `force_tier` does to a body: None if it takes it unhurt, otherwise the worst
    it does short of death (badly wounded on a close call), or `Health.DYING` for death."""
    margin = _tier(state, character) - force_tier
    if margin >= TAKES_IT_MARGIN:
        return None
    if margin > -TAKES_IT_MARGIN:
        return Health.BADLY_WOUNDED
    return Health.DYING


def force_ceiling_margin(state: WorldState, bodies: list[Character], force_tier: float):
    """The toughest body among `bodies` and how many tiers it stands above the hit."""
    toughest = max(bodies, key=lambda c: (_tier(state, c), c.id))
    return _tier(state, toughest) - force_tier, toughest


@dataclass
class BlastOutcome:
    effects: StateDelta
    deed: ProposedDeed | None
    actor_dies: bool
    reason: str


def blast_outcome(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    hit: StoppedHit,
    targets: list[Character],
) -> BlastOutcome:
    """W10a, A2, N6. Where a relative-speed throw's energy goes when it strikes. Everyone at the
    place it lands is inside its deadly reach unless their body takes it; the place it lands in
    is ruined, and so is the thrower's if the blast reaches it; a host it was thrown at is wiped
    out; and the thrower, shielded only while the stop lasts, meets their own blast when time
    restarts. The aim's own targets are settled by the step itself, not here."""
    assert hit.blast is not None and hit.force_tier is not None
    impact = impact_place(state, actor, step)
    here = actor.location_id or state.scene.place_id
    distance = thrower_distance(state, step, impact, here)
    blast = hit.blast
    target_ids = {t.id for t in targets}

    characters: list[CharacterChange] = []
    killed: list[str] = []
    hurt: list[str] = []
    caught = [(p, True) for p in _near(state, impact, exclude={actor.id, *target_ids})]
    if here != impact and distance <= blast.harm_m:
        # Those beside the thrower are as far from the blast as they are.
        seen = {p.id for p, _ in caught} | {actor.id, *target_ids}
        lethal = distance <= blast.lethal_m
        caught += [(p, lethal) for p in _near(state, here, exclude=seen)]
    for person, lethal in caught:
        harm = takes_it(state, person, hit.force_tier) if lethal else Health.HURT
        if harm is None:
            continue
        if harm is Health.DYING:
            characters.append(_death(person.id))
            killed.append(person.id)
        else:
            characters.append(_wound(person.id, harm, "caught in the blast"))
            hurt.append(person.id)

    actor_dies = False
    fate = ""
    if distance <= blast.lethal_m:
        harm = takes_it(state, actor, hit.force_tier)
        if harm is Health.DYING:
            actor_dies = True
            characters.append(_death(actor.id))
            fate = "Once time restarts, the blast reaches the thrower too"
        elif harm is not None:
            characters.append(_wound(actor.id, harm, "caught in the edge of their own blast"))
            fate = "Once time restarts, the blast catches the thrower"
    elif distance <= blast.harm_m:
        characters.append(_wound(actor.id, Health.HURT, "knocked down by the distant blast"))
        fate = "Once time restarts, the distant blast knocks the thrower off their feet"

    places: list[PlaceChange] = []
    ruined: list[str] = []
    status = None
    if blast.lethal_m >= force_mod.RUIN_LETHAL_M:
        status = PlaceStatus.RUINED
    elif blast.lethal_m >= force_mod.DAMAGE_LETHAL_M:
        status = PlaceStatus.DAMAGED
    wrecked = [impact] + ([here] if here != impact and distance <= blast.lethal_m else [])
    for place_id in dict.fromkeys(p for p in wrecked if p in state.places):
        place = state.places[place_id]
        if status is None or place.status is PlaceStatus.RUINED:
            continue
        if status is PlaceStatus.DAMAGED and place.status is not PlaceStatus.THRIVING:
            continue
        places.append(PlaceChange(id=place_id, status=status, known_to_player=True))
        ruined.append(place_id)

    factions: list[FactionChange] = []
    hosts: list[str] = []
    for faction_id in dict.fromkeys(step.target_ids):
        faction = state.factions.get(faction_id)
        if faction is None or faction.status is FactionStatus.DESTROYED:
            continue
        wiped = blast.lethal_m >= force_mod.HOST_LETHAL_M
        factions.append(
            FactionChange(
                id=faction_id,
                status=FactionStatus.DESTROYED if wiped else FactionStatus.WEAKENED,
                known_to_player=True,
            )
        )
        hosts.append(faction_id)

    effects = StateDelta(characters=characters, places=places, factions=factions)
    deed = _blast_deed(state, actor, step, hit, impact, killed, hurt, ruined, hosts)
    where = state.places[impact].name if impact in state.places else "where it lands"
    reason = f"The blast tears through {where}"
    if fate:
        reason = f"{reason}. {fate}"
    return BlastOutcome(effects=effects, deed=deed, actor_dies=actor_dies, reason=reason)


def impact_place(state: WorldState, actor: Character, step: IntentStep) -> str | None:
    """Where a throw lands: a place it names, else where its first target stands, else here."""
    for ref in step.target_ids:
        if ref in state.places:
            return ref
    for ref in step.target_ids:
        character = state.characters.get(ref)
        if character is not None and character.location_id:
            return character.location_id
    return state.scene.place_id or actor.location_id


def thrower_distance(
    state: WorldState, step: IntentStep, impact: str | None, here: str | None
) -> float:
    """How far the thrower stands from where it lands: what the step says, else a stone's throw
    when it lands where they are, else a route's travel time at a walk."""
    if step.range_m is not None:
        return float(step.range_m)
    if impact is None or impact == here:
        return DEFAULT_RANGE_M
    place = state.places.get(here) if here else None
    travel = place.travel_s_to(impact) if place is not None else None
    return travel * WALK_M_S if travel is not None else UNKNOWN_DISTANCE_M


def _within(state: WorldState, place_id: str | None, root: str) -> bool:
    seen: set[str] = set()
    while place_id is not None and place_id not in seen:
        if place_id == root:
            return True
        seen.add(place_id)
        place = state.places.get(place_id)
        place_id = place.parent_id if place is not None else None
    return False


def _near(state: WorldState, impact: str | None, *, exclude: set[str]) -> list[Character]:
    """Living characters at the place a throw lands, or anywhere inside it, and everyone in the
    scene when it lands where the scene is."""
    if impact is None:
        return []
    found: dict[str, Character] = {}
    for character in sorted(state.characters.values(), key=lambda c: c.id):
        if not character.alive or character.id in exclude:
            continue
        here = character.location_id
        in_scene = impact == state.scene.place_id and character.id in state.scene.present_ids
        if in_scene or (here is not None and _within(state, here, impact)):
            found[character.id] = character
    return list(found.values())


def _death(character_id: str) -> CharacterChange:
    return CharacterChange(
        id=character_id, status=CharacterStatus.DEAD, death_certainty=DeathCertainty.CONFIRMED
    )


def _wound(character_id: str, health: Health, why: str) -> CharacterChange:
    return CharacterChange(id=character_id, condition=ConditionChange(health=health, wounds=[why]))


def _blast_deed(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    hit: StoppedHit,
    impact: str | None,
    killed: list[str],
    hurt: list[str],
    ruined: list[str],
    hosts: list[str],
) -> ProposedDeed | None:
    """W1, W13. The blast is a deed of its own, secret because the world was frozen, with the
    traces nobody can miss: a blast seen and heard for miles, the ruins and the dead."""
    if not (killed or hurt or ruined or hosts):
        return None
    massacre = len(killed) + (len(hosts) * 5) >= 5
    if massacre:
        kind, severity = "massacre", 5
    elif killed:
        kind, severity = "kill", 4
    elif ruined:
        kind, severity = "raze", 4
    else:
        kind, severity = "destroy", 2
    assert hit.blast is not None
    traces = [
        Trace(
            kind=TraceKind.NOISE,
            text=f"A blast of {hit.blast.words}, seen and heard for miles.",
            strength=100,
        )
    ]
    if ruined:
        names = ", ".join(state.places[p].name for p in ruined)
        traces.append(
            Trace(kind=TraceKind.DAMAGE, text=f"Ruins where {names} stood.", strength=100)
        )
    if killed:
        traces.append(Trace(kind=TraceKind.BODY, text="The dead of the blast.", strength=100))
    actor_id = actor.id if actor.id != state.player_id else None
    return ProposedDeed(
        kind=kind,
        text=f"A stopped-time throw strikes with {hit.blast.words}",
        actor_id=actor_id,
        victim_ids=[*killed, *hurt],
        target_ids=[*ruined, *hosts],
        place_id=impact,
        severity=severity,
        witness_ids=witnesses(state, actor, exclude=set(killed)),
        traces=traces,
        in_stopped_time=True,
    )


def witnesses(state: WorldState, actor: Character, *, exclude: set[str] = frozenset()) -> list[str]:
    """W10a. Only someone immune to the stop sees what is done in it."""
    return [
        cid
        for cid in state.scene.present_ids
        if cid != actor.id
        and cid not in exclude
        and cid in state.characters
        and state.characters[cid].alive
        and immune(state.characters[cid])
    ]


def stopped_traces(
    state: WorldState,
    actor: Character,
    power: Power,
    hit: StoppedHit | None,
    killed: list[Character],
) -> list[Trace]:
    """W10a, W13. What a deed done in stopped time leaves behind: to everyone else, the guard
    simply drops dead, and a wound only such a power makes points at a user the world knows of."""
    traces: list[Trace] = []
    if killed:
        crowd = [
            cid
            for cid in state.scene.present_ids
            if cid != actor.id and cid not in {k.id for k in killed} and cid in state.characters
        ]
        names = ", ".join(k.name for k in killed)
        verb = "drops" if len(killed) == 1 else "drop"
        traces.append(
            Trace(
                kind=TraceKind.BODY,
                text=f"{names} {verb} dead with nobody near.",
                strength=CROWD_BODY_STRENGTH if crowd else LONE_BODY_STRENGTH,
            )
        )
    if hit is not None and hit.mode is HitMode.RELATIVE_SPEED and not power.secret and killed:
        traces.append(
            Trace(
                kind=TraceKind.WOUND,
                text=f"Wounds only {power.name} makes.",
                strength=60,
            )
        )
    return traces


def frozen_lead(state: WorldState, character: Character) -> str:
    return f"{cap(name(state, character.id))} {is_are(state, character.id)} frozen in stopped time"


def might_with_powers(state: WorldState, character: Character) -> int:
    """A8, W5, G20. The might the world can measure a character by. Hidden strength counts as
    the rung it shows. A time stop whose hits land at relative speed counts once the world could
    know of it: the power isn't secret, or a deed done with it has been laid at their door. A
    light-speed thrower then counts as far above anything that can't take three megatons, so
    factions answer with fear, offers or plots."""
    might = sensing.apparent_tier(state, character, character.sheet.axes.might)
    for power in character.sheet.powers:
        if not stops_time(power):
            continue
        settled = Settlements()
        mode = known_hit_mode(power, settled) or default_hit_mode(power)
        if throw_mode(power, mode, settled) is not HitMode.RELATIVE_SPEED:
            continue
        if power.secret and not stopped_time_deeds_known(state, character):
            continue
        joules = force_mod.relative_speed_joules(force_mod.PEBBLE_KG)
        might = max(might, int(force_mod.tier_for(joules, state.bible.force)))
    return might


def stopped_time_deeds_known(
    state: WorldState, character: Character, *, besides: str | None = None
) -> bool:
    """Whether a deed this character did in stopped time, other than `besides`, has been laid
    at their door: a witness or a faction knows who did it, or a true rumor names them."""
    mine = [
        d
        for d in state.deeds.values()
        if d.actor_id == character.id and d.in_stopped_time and d.id != besides
    ]
    if any(d.known_by_factions or any(k != character.id for k in d.known_by) for d in mine):
        return True
    ids = {d.id for d in mine}
    return bool(ids) and any(
        r.deed_id in ids and r.is_true and character.id in r.about_ids
        for r in state.rumors.values()
    )
