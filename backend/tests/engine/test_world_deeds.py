"""How the world answers deeds, from the gaps the story evals found (W4, W5, W8, W11, W13, G16,
G24): a beast hunt is no crime, a known time stopper's signature points at them, survivors of a
massacre remember, the world tells deeds in its own words, and a faction answers an attempt on
one of its own by one of its own."""

from engine.base import DAY, HOUR, MINUTE
from engine.contracts import ProposedDeed
from engine.samples import cultivation_world
from engine.state import (
    Attitude,
    Character,
    CharacterSheet,
    CharacterStatus,
    Creature,
    DeathCertainty,
    Deed,
    Faction,
    HitMode,
    Membership,
    PassingState,
    Place,
    PowerAxes,
    Prominence,
    Route,
    Trace,
    TraceKind,
    Visibility,
    WorldState,
)
from engine.visibility import attitude_label
from engine.world import Kind
from engine.world.answers import Answer
from engine.world.carriers import would_report
from engine.world.discovery import attribution_odds, name_the_doer
from engine.world.norms import Nature, assess_severity, deed_nature, is_crime
from engine.world.telling import account, found, listing
from engine.world.tuning import BODY_NEARBY_STRENGTH, TRACE_ATTRIBUTION

from .test_world import at, deed_step, idle, moved_on, pending_of, play, the_deed

# --- Beasts and hunts (G24, W4, W11) ------------------------------------------------------------


def ashwood() -> WorldState:
    """Lin in the Ashwood, where an ash wolf pack hunts: a lone wolf by the stream, its alpha
    watching from the treeline, two more in the den, and a disciple gathering herbs."""
    state = cultivation_world()
    state.bible.creatures.append(
        Creature(id="ash-wolf", name="ash wolf", tier=2, habitat="the Ashwood")
    )
    state.places["ashwood"] = Place(
        id="ashwood",
        name="the Ashwood",
        kind="forest",
        parent_id="azure-peak",
        routes=[Route(to_id="well", travel_s=3 * HOUR)],
    )
    state.places["den"] = Place(id="den", name="the den", kind="den", parent_id="ashwood")
    state.factions["ash-pack"] = Faction(
        id="ash-pack", name="the Ashwood pack", kind="pack", leader_ids=["alpha"]
    )
    for wolf_id, name, place in (
        ("stray", "a lone ash wolf", "ashwood"),
        ("alpha", "the pack's alpha", "ashwood"),
        ("wolf-2", "an ash wolf", "den"),
        ("wolf-3", "an ash wolf", "den"),
    ):
        state.characters[wolf_id] = Character(
            id=wolf_id,
            name=name,
            people_id="ash-wolf",
            location_id=place,
            memberships=[Membership(faction_id="ash-pack", rank="wolf")],
            sheet=CharacterSheet(axes=PowerAxes(might=2)),
        )
    state.characters["herbalist"] = Character(
        id="herbalist",
        name="Wei the herbalist",
        location_id="ashwood",
        memberships=[Membership(faction_id="outer-court", rank="outer disciple")],
    )
    state.characters["herbalist"].sheet.disposition.attitudes["lin"] = Attitude(affinity=30)
    state.characters["lin"].location_id = "ashwood"
    state.scene.place_id = "ashwood"
    state.scene.present_ids = ["lin", "stray", "alpha", "herbalist"]
    return state


def hunt(victim: str = "stray", text: str = "kill the lone ash wolf (it worked)") -> ProposedDeed:
    return ProposedDeed(kind="attack", text=text, victim_ids=[victim], severity=4)


def test_killing_a_beast_is_a_hunt_no_crime_and_its_pack_remembers():
    state = ashwood()
    after = play(state, deed_step(hunt(), dead=("stray",))).state
    deed = the_deed(after)

    assert deed_nature(after, deed) is Nature.HUNT
    assert deed.severity == 1  # a forest wolf is a trifle to everyone but its pack
    assert not is_crime(after, deed)
    assert not pending_of(after, Kind.REPORT) and not pending_of(after, Kind.ANSWER)
    alpha = after.characters["alpha"].attitude_toward("lin")
    assert alpha.grudges and alpha.affinity < 0
    # The herbalist saw a wolf fall, nothing more.
    assert after.characters["herbalist"].attitude_toward("lin").affinity == 30
    assert after.places["azure-peak"].player_reputation.esteem == 0

    after, fired = idle(after, after.world_s + 30 * DAY)

    assert not [e for e in fired if e.payload.get("answer") == Answer.ARREST.value]


def test_putting_down_a_whole_pack_is_still_a_hunt():
    """A deed aimed at the pack itself, as a host, harms no person either (G24)."""
    state = ashwood()
    wolves = ["stray", "alpha", "wolf-2", "wolf-3"]
    cull = ProposedDeed(
        kind="massacre",
        text="wipe out the Ashwood pack (it worked)",
        target_ids=["ash-pack"],
        victim_ids=wolves,
        severity=5,
    )
    after = play(state, deed_step(cull, dead=tuple(wolves))).state
    deed = the_deed(after)

    assert deed_nature(after, deed) is Nature.HUNT
    assert not is_crime(after, deed) and deed.severity < 5


def test_the_player_remembers_a_beast_they_never_named_by_its_kind():
    """C6, G16: Lin never learned the wolf's name or the forest's, so his memory holds the
    kind of beast he killed."""
    from engine.visibility import memory_view

    after = play(ashwood(), deed_step(hunt(), dead=("stray",))).state

    (deed,) = memory_view(after).deeds
    assert deed.text == "You killed an ash wolf."


def test_two_wolves_never_named_are_two_wolves():
    from engine.visibility import memory_view

    cull = ProposedDeed(
        kind="kill", text="kill both wolves (it worked)", victim_ids=["stray", "alpha"], severity=2
    )
    after = play(ashwood(), deed_step(cull, dead=("stray", "alpha"))).state

    (deed,) = memory_view(after).deeds
    assert deed.text == "You killed an ash wolf and one other."


def test_a_beast_tells_nobody_but_its_own_pack():
    state = ashwood()
    after = play(state, deed_step(hunt(), dead=("stray",))).state
    deed = the_deed(after)
    alpha = after.characters["alpha"]

    assert not would_report(after, alpha, "azure-cloud", deed)
    assert would_report(after, alpha, "ash-pack", deed)


def test_word_of_a_person_s_death_reaches_their_friends_but_not_their_beasts():
    """Tidings are talk, which beasts don't follow (G24)."""
    state = ashwood()
    state.characters["wolf-2"].sheet.disposition.attitudes["herbalist"] = Attitude(affinity=60)
    state.characters["mei"] = Character(id="mei", name="Mei", location_id="well")
    state.characters["mei"].sheet.disposition.attitudes["herbalist"] = Attitude(affinity=60)
    # Someone who can talk sees it: the wolves there carry no word of it (W2, G24).
    state.characters["pan"] = Character(id="pan", name="Old Pan", location_id="ashwood")
    state.scene.present_ids.append("pan")
    murder = ProposedDeed(
        kind="kill", text="kill Wei (it worked)", victim_ids=["herbalist"], severity=4
    )
    after = play(state, deed_step(murder, dead=("herbalist",))).state
    assert not pending_of(after, Kind.TIDINGS)  # nobody who saw it has told anyone yet (W2)

    after, fired = idle(moved_on(after), after.world_s + 2 * HOUR)

    tidings = [*pending_of(after, Kind.TIDINGS), *(e for e in fired if e.kind == Kind.TIDINGS)]
    told = {e.payload.get("character_id") for e in tidings}
    assert "mei" in told and "wolf-2" not in told


def test_slaying_a_notable_beast_is_news_but_still_no_crime():
    state = ashwood()
    state.bible.creatures.append(Creature(id="dragon", name="dragon", tier=14))
    state.characters["dragon"] = Character(
        id="dragon",
        name="the ancient dragon",
        people_id="dragon",
        prominence=Prominence.KEY,
        location_id="ashwood",
        sheet=CharacterSheet(axes=PowerAxes(might=14)),
    )
    state.scene.present_ids.append("dragon")
    slay = hunt("dragon", text="slay the ancient dragon (it worked)")

    after = play(state, deed_step(slay, dead=("dragon",))).state
    deed = the_deed(after)

    assert deed.severity == 4  # what resolve proposed, under the dragon's five
    assert not is_crime(after, deed)
    assert after.characters["herbalist"].attitude_toward("lin").fear > 0
    after, _ = idle(moved_on(after), after.world_s + 2 * HOUR)  # once the herbalist can talk
    assert [r for r in after.rumors.values() if r.deed_id == deed.id]


def test_an_unwitnessed_beast_kill_leaves_its_body_for_the_pack_to_find():
    state = ashwood()
    for wolf in ("alpha", "herbalist"):
        state.characters[wolf].location_id = "den" if wolf == "alpha" else "well"
    state.scene.present_ids = ["lin", "stray"]

    after = play(state, deed_step(hunt(), dead=("stray",))).state
    deed = the_deed(after)

    assert deed.visibility is Visibility.SECRET
    (body,) = [t for t in deed.traces if t.kind is TraceKind.BODY]
    assert body.strength == BODY_NEARBY_STRENGTH and "lone ash wolf" in body.text

    after, fired = idle(after, after.world_s + 30 * DAY)

    assert after.deeds[deed.id].discovered
    assert not [e for e in fired if e.payload.get("answer") == Answer.INVESTIGATE.value]


def test_a_body_left_where_someone_unaware_lies_is_found_at_once():
    state = cultivation_world()
    state.characters["wei"] = Character(
        id="wei",
        name="Wei",
        location_id="well",
        sheet=CharacterSheet(),
    )
    state.characters["wei"].sheet.condition.states.append(PassingState(name="asleep"))
    kill = ProposedDeed(kind="kill", text="Lin kills Zhao", victim_ids=["zhao"])

    after = play(state, deed_step(kill, dead=("zhao",))).state
    deed = the_deed(after)

    (body,) = [t for t in deed.traces if t.kind is TraceKind.BODY]
    assert deed.visibility is Visibility.SECRET and body.strength == 100


# --- A known time stopper's signature, and word reaching a kingdom (W10a, W13, W5) ---------------


def stopped_kill(state: WorldState) -> Deed:
    return Deed(
        id="deed-blast",
        actor_id="lin",
        kind="massacre",
        text="A stopped-time throw strikes",
        turn=1,
        world_s=state.world_s,
        place_id="well",
        victim_ids=["zhao"],
        severity=5,
        traces=[Trace(kind=TraceKind.BODY, text="Zhao drops dead with nobody near.")],
        in_stopped_time=True,
    )


def test_death_with_nobody_near_points_at_a_time_stopper_the_world_knows_of():
    state = cultivation_world()
    deed = stopped_kill(state)
    state.deeds[deed.id] = deed
    power = state.characters["lin"].sheet.power("time-stop")

    assert power.secret and attribution_odds(state, deed, 0) == 0
    power.secret = False
    assert attribution_odds(state, deed, 0) == TRACE_ATTRIBUTION["wound"]


def kingdom_and_army() -> WorldState:
    state = cultivation_world()
    state.characters["lin"].sheet.power("time-stop").time.hit_mode = HitMode.RELATIVE_SPEED
    state.characters["lin"].sheet.power("time-stop").secret = False
    state.places["plain"] = Place(id="plain", name="the plain", kind="plain")
    state.factions["kingdom"] = Faction(id="kingdom", name="the Northern Kingdom", kind="kingdom")
    state.factions["army"] = Faction(
        id="army", name="the Black Banner army", kind="army", parent_id="kingdom"
    )
    for n in range(3):
        state.characters[f"soldier-{n}"] = Character(
            id=f"soldier-{n}",
            name=f"soldier {n + 1}",
            location_id="plain",
            memberships=[Membership(faction_id="army", rank="soldier")],
        )
    return state


def test_word_of_who_wiped_out_an_army_reaches_the_kingdom_it_served():
    state = kingdom_and_army()
    blast = ProposedDeed(
        kind="massacre",
        text="A stopped-time throw strikes with about 3 megatons",
        victim_ids=[f"soldier-{n}" for n in range(3)],
        target_ids=["plain", "army"],
        place_id="plain",
        severity=5,
        traces=[Trace(kind=TraceKind.NOISE, text="A blast seen for miles.", strength=100)],
        in_stopped_time=True,
    )
    after = play(state, deed_step(blast, dead=tuple(f"soldier-{n}" for n in range(3)))).state
    deed = the_deed(after)
    name_the_doer(at(after), deed)

    words = {
        e.payload["faction_id"]: e
        for e in pending_of(after, Kind.TIDINGS)
        if "faction_id" in e.payload
    }
    assert set(words) == {"army", "kingdom"}  # its host, and the kingdom the host sits in
    assert "the Black Banner army" in words["kingdom"].title

    after, fired = idle(after, after.world_s + 30 * DAY)

    assert "kingdom" in after.deeds[deed.id].known_by_factions
    answers = [e for e in fired if e.kind == Kind.ANSWER and e.payload["faction_id"] == "kingdom"]
    answers += [e for e in pending_of(after, Kind.ANSWER) if e.payload["faction_id"] == "kingdom"]
    assert answers
    # Nothing it has could win, so it never sends force (A9, W5).
    assert all(e.payload["answer"] not in (Answer.ARMY.value, Answer.ELITE.value) for e in answers)


# --- Survivors remember (W4, W8, W12) -----------------------------------------------------------


def willow_ford() -> WorldState:
    state = cultivation_world()
    state.places["village"] = Place(id="village", name="Willow Ford", kind="village")
    state.places["fields"] = Place(
        id="fields", name="the fields", kind="fields", parent_id="village"
    )
    state.factions["villagers"] = Faction(id="villagers", name="Willow Ford", kind="village")
    for n in range(6):
        state.characters[f"villager-{n}"] = Character(
            id=f"villager-{n}",
            name=f"Villager {n}",
            location_id="village",
            memberships=[Membership(faction_id="villagers")],
        )
    state.characters["peddler"] = Character(id="peddler", name="Fen", location_id="village")
    state.characters["farmer"] = Character(
        id="farmer",
        name="Shu",
        location_id="fields",
        memberships=[Membership(faction_id="villagers")],
    )
    for character_id in ("peddler", "farmer"):
        state.characters[character_id].sheet.disposition.attitudes["lin"] = Attitude(affinity=40)
    state.characters["lin"].location_id = "village"
    state.scene.place_id = "village"
    state.scene.present_ids = ["lin", "peddler", *(f"villager-{n}" for n in range(6))]
    return state


def test_whoever_lived_through_a_massacre_turns_against_the_one_who_did_it():
    state = willow_ford()
    victims = [f"villager-{n}" for n in range(6)]
    massacre = ProposedDeed(
        kind="massacre", text="cut down the villagers (it worked)", victim_ids=victims
    )

    after = play(state, deed_step(massacre, dead=tuple(victims))).state
    peddler = after.characters["peddler"].attitude_toward("lin")

    assert attitude_label(peddler.affinity) in ("Cold", "Hostile") and peddler.grudges

    after, _ = idle(after, after.world_s + DAY)
    farmer = after.characters["farmer"].attitude_toward("lin")

    assert attitude_label(farmer.affinity) in ("Cold", "Hostile") and farmer.grudges


def test_a_brawl_barely_moves_a_bystander():
    state = willow_ford()
    brawl = ProposedDeed(kind="assault", text="shove a villager", victim_ids=["villager-0"])

    after = play(state, deed_step(brawl)).state

    peddler = after.characters["peddler"].attitude_toward("lin")
    assert attitude_label(peddler.affinity) == "Friendly" and not peddler.grudges


# --- The world's words (G16) --------------------------------------------------------------------


def test_names_are_listed_as_people_say_them():
    assert listing([]) == ""
    assert listing(["Old Pan"]) == "Old Pan"
    assert listing(["Old Pan", "Hua"]) == "Old Pan and Hua"
    assert listing(["A", "B", "C"]) == "A, B and C"
    assert listing(["A", "B", "C", "D", "E", "F"]) == "A, B and four others"
    # Those the teller can't name are counted, never named (C6).
    assert listing([], more=1) == "someone"
    assert listing([], more=3) == "three people"
    assert listing(["Old Pan"], more=1) == "Old Pan and one other"
    assert listing(["A", "B", "C"], more=2) == "A, B and three others"


def test_rumors_and_grudges_tell_a_deed_in_the_world_s_words():
    state = cultivation_world()
    state.characters["wei"] = Character(
        id="wei",
        name="Wei",
        location_id="well",
        memberships=[Membership(faction_id="outer-court", rank="outer disciple")],
    )
    state.scene.present_ids.append("wei")
    kill = ProposedDeed(kind="kill", text="cut Zhao's throat (it worked)", victim_ids=["zhao"])

    after = play(state, deed_step(kill, dead=("zhao",))).state
    deed = the_deed(after)
    after, _ = idle(moved_on(after), after.world_s + 2 * HOUR)  # once Wei can talk
    (rumor,) = [r for r in after.rumors.values() if r.deed_id == deed.id]

    assert rumor.text == "Lin Feng killed Zhao Kun at the outer-court well."
    events = [e.title for e in after.pending_events.values()]
    assert not [t for t in events if "it worked" in t or "cut Zhao" in t]
    (grudge,) = after.characters["wei"].attitude_toward("lin").grudges
    assert grudge.reason == rumor.text


def test_nameless_victims_are_counted_and_a_burned_place_is_named():
    state = cultivation_world()
    massacre = Deed(
        id="m1",
        actor_id="lin",
        kind="massacre",
        text="cut down every villager (it worked)",
        victim_ids=["villager-1", "villager-2", "villager-3"],
        place_id="well",
        severity=5,
        turn=1,
        world_s=0,
    )
    state.places["granary"] = Place(id="granary", name="the granary", kind="granary")
    fire = massacre.model_copy(
        update={
            "kind": "burn",
            "target_ids": ["granary"],
            "victim_ids": ["villager-1"],
            "place_id": None,
        }
    )

    assert account(state, massacre) == "Lin Feng massacred three people at the outer-court well."
    assert account(state, fire) == "Lin Feng burned the granary."


def test_an_attempt_a_hunt_and_a_find_are_told_plainly():
    state = cultivation_world()
    attempt = Deed(
        id="d1",
        actor_id="lin",
        kind="kill",
        text="stab Zhao (it failed)",
        turn=1,
        world_s=0,
        place_id="well",
        target_ids=["zhao"],
        severity=3,
    )
    many = [f"v{n}" for n in range(6)]
    for n, victim in enumerate(many):
        state.characters[victim] = Character(
            id=victim,
            name=f"Villager {n}",
            status=CharacterStatus.DEAD,
            death_certainty=DeathCertainty.CONFIRMED,
        )
    dead = attempt.model_copy(update={"id": "d2", "kind": "massacre", "victim_ids": many})

    assert account(state, attempt) == "Lin Feng tried to kill Zhao Kun at the outer-court well."
    assert account(state, attempt, doer="someone").startswith("Someone tried to kill")
    assert found(state, dead) == (
        "Villager 0, Villager 1 and four others were found dead at the outer-court well"
    )


# --- A faction answers an attempt on its own by its own (W5, W11) -------------------------------


def test_an_attempted_murder_inside_the_victims_own_faction_is_answered():
    state = cultivation_world()
    state.characters["wei"] = Character(
        id="wei",
        name="Wei",
        location_id="well",
        memberships=[Membership(faction_id="outer-court", rank="outer disciple")],
    )
    tried = ProposedDeed(kind="kill", text="stab Zhao (it failed)", target_ids=["zhao"], severity=3)

    after = play(state, deed_step(tried)).state
    after, fired = idle(after, after.world_s + 6 * HOUR)

    assert "azure-cloud" in the_deed(after).known_by_factions
    arrests = [e for e in fired if e.kind == Kind.ANSWER and e.payload["answer"] == "arrest"]
    assert [e.payload["faction_id"] for e in arrests] == ["azure-cloud"]


def test_a_scuffle_between_members_is_still_left_to_them():
    state = cultivation_world()
    state.characters["wei"] = Character(
        id="wei",
        name="Wei",
        location_id="well",
        memberships=[Membership(faction_id="outer-court", rank="outer disciple")],
    )
    shove = ProposedDeed(kind="assault", text="shove Zhao", victim_ids=["zhao"], severity=2)

    after = play(state, deed_step(shove)).state
    after, fired = idle(after, after.world_s + 10 * MINUTE)

    assert severity_of(after) == 2
    assert not [e for e in fired if e.kind == Kind.ANSWER]


def severity_of(state: WorldState) -> int:
    return the_deed(state).severity


def test_a_hunt_keeps_below_how_notable_its_beast_was():
    state = ashwood()
    assert assess_severity(state, "kill", 4, ["stray"]) == 1
    assert assess_severity(state, "massacre", 5, ["stray", "alpha", "wolf-2", "wolf-3"]) == 1
    assert assess_severity(state, "kill", 1, ["herbalist"]) == 3  # a person keeps the floors
