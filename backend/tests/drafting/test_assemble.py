"""The code that turns the drafter's proposal into the opening world state (G1, G2, G7, G8,
G18, G22, C6, W15). The model proposes; these rules decide."""

import pytest

from engine import bonds
from engine.base import HOUR
from engine.context import Language
from engine.invariants import check_state
from engine.resolve.powers import growth
from engine.state import (
    Activity,
    BondStage,
    BondStep,
    Faith,
    GiftStrength,
    HitMode,
    PhysicsMode,
    Prevalence,
    RuleTopic,
    TalentStrength,
    Unions,
)
from graph.drafting import samples
from graph.drafting.assemble import (
    ACTIVE_FACTIONS,
    ACTIVE_NPCS,
    GROUNDED_RULE_TEXT,
    GROUNDED_RULE_TEXTS,
    HUMAN_PEAK,
    PLAYER_FALLBACK_NAME,
    STOP_LASTS_S,
    STOP_RECHARGE_S,
    DraftOptions,
    assemble,
    drafted_clocks,
    slug,
)
from graph.drafting.catalog import starter
from graph.drafting.schema import (
    PLAYER_ID,
    AttitudeP,
    AttributesP,
    CharacterProposal,
    ExtraordinaryP,
    FactionP,
    LadderPositionP,
    NpcP,
    PowerP,
    RuleP,
    RungP,
    TalentP,
    TimeP,
    WorldProposal,
)


def _world(**changes) -> WorldProposal:
    return samples.cultivation_world().model_copy(update=changes)


def _character(**changes) -> CharacterProposal:
    return samples.cultivation_character().model_copy(update=changes)


def _time_stop(**changes) -> PowerP:
    power = samples.cultivation_character().powers[0]
    return power.model_copy(update=changes)


@pytest.mark.parametrize("proposal", [samples.naples, samples.cultivation])
def test_the_samples_assemble_into_states_that_pass_every_invariant(proposal):
    draft = proposal()

    state = assemble(draft.world, draft.character)

    assert check_state(state) == []
    assert state.player_id == PLAYER_ID
    assert state.turn == 0 and state.world_s == 0
    assert state.scene.place_id in state.places


def test_drafted_places_say_whether_they_are_under_the_sky():
    """R8: a drafted place keeps its setting, so the first scene in a buried temple is told
    underground. One the drafter leaves out stays untold, and a value it gets wrong costs only
    itself (G1)."""
    from engine.state import PlaceSetting
    from graph.drafting import lenient
    from graph.drafting.schema import PlaceP

    draft = samples.naples()
    state = assemble(draft.world, draft.character)
    assert state.places["bar"].setting is PlaceSetting.INDOORS
    assert state.places["naples"].setting is None

    context = lenient.model_output()
    crypt = PlaceP.model_validate(
        {"id": "crypt", "name": "the crypt", "setting": "Underground"}, context=context
    )
    odd = PlaceP.model_validate(
        {"id": "deck", "name": "the deck", "setting": "on a ship"}, context=context
    )
    assert crypt.setting is PlaceSetting.UNDERGROUND
    assert odd.setting is None


# Ids.


def test_slugs_are_short_lowercase_ids():
    assert slug("The Outer Court!") == "the-outer-court"
    assert slug("  Café  Nero ") == "cafe-nero"
    assert slug("***") == ""


def test_duplicate_ids_are_made_unique_and_references_resolve_by_name():
    world = _world(
        factions=[
            FactionP(id="sect", name="the Azure Cloud Sect", kind="sect"),
            FactionP(id="sect", name="the Crimson Hall", kind="sect"),
        ],
        npcs=[
            NpcP(
                id="zhao",
                name="Zhao Kun",
                memberships=[{"faction_id": "the Crimson Hall", "rank": "disciple"}],
            ),
            NpcP(id="zhao", name="Zhao Ling"),
        ],
    )

    state = assemble(world, _character(memberships=[]))

    assert len(state.factions) == 2
    assert len({c.id for c in state.npcs()}) == 2
    zhao_kun = next(c for c in state.npcs() if c.name == "Zhao Kun")
    crimson = next(f for f in state.factions.values() if f.name == "the Crimson Hall")
    assert [m.faction_id for m in zhao_kun.memberships] == [crimson.id]


def test_references_to_nothing_are_dropped():
    world = _world(
        npcs=[
            NpcP(
                id="zhao",
                name="Zhao Kun",
                location_id="nowhere",
                memberships=[{"faction_id": "no-such-sect"}],
            )
        ]
    )

    state = assemble(world, _character(location_id="nowhere"))

    zhao = state.characters["zhao"]
    assert zhao.memberships == []
    assert zhao.location_id in state.places
    assert state.player.location_id in state.places


def test_the_player_is_always_player_and_always_has_a_real_name():
    character = _character(name="the stranger")

    state = assemble(_world(), character)

    assert state.player.id == PLAYER_ID
    assert state.player.name == PLAYER_FALLBACK_NAME


def test_placeholder_npcs_are_left_out():
    world = _world(npcs=[NpcP(id="x", name="the stranger"), NpcP(id="zhao", name="Zhao Kun")])

    state = assemble(world, _character())

    assert [c.name for c in state.npcs()] == ["Zhao Kun"]


# G7.


def test_every_kind_gets_an_existence_rule_fixed_by_default():
    world = _world(
        rules=[],
        extraordinary=[ExtraordinaryP(id="aura", kind="aura", prevalence="common")],
    )

    state = assemble(world, _character(powers=[]))

    [rule] = state.bible.rules
    assert rule.fixed and rule.topic is RuleTopic.EXISTENCE
    assert state.bible.extraordinary[0].rule_ids == [rule.id]


def test_a_world_with_no_kinds_is_grounded_with_a_fixed_rule():
    world = samples.naples_world().model_copy(update={"extraordinary": [], "rules": []})

    state = assemble(world, samples.naples_character())

    assert state.bible.grounded
    assert [(r.text, r.fixed) for r in state.bible.rules] == [(GROUNDED_RULE_TEXT, True)]


def test_the_rules_code_writes_come_in_the_draft_s_language():
    # S10: a Spanish draft gets its code-written rules in Spanish.
    spanish = DraftOptions(language=Language.ES)
    grounded = samples.naples_world().model_copy(update={"extraordinary": [], "rules": []})
    aura = _world(
        rules=[], extraordinary=[ExtraordinaryP(id="aura", kind="aura", prevalence="common")]
    )

    assert [
        r.text for r in assemble(grounded, samples.naples_character(), spanish).bible.rules
    ] == [GROUNDED_RULE_TEXTS[Language.ES]]
    [rule] = assemble(aura, _character(powers=[]), spanish).bible.rules
    assert rule.text == "Aura: existe, y está en todas partes."


def test_a_released_template_rule_no_longer_holds():
    template = starter("three-heartbeats").template
    # A proposal with no time powers of its own.
    world = _world(
        extraordinary=[e for e in _world().extraordinary if e.id != "time-powers"],
        rules=[r for r in _world().rules if r.id != "time-powers-exist"],
    )

    kept = assemble(world, _character(powers=[]), DraftOptions(template=template))
    released = assemble(
        world,
        _character(powers=[]),
        DraftOptions(template=template, released_rules=frozenset({"time-powers-exist"})),
    )

    assert "time-powers" in {k.id for k in kept.bible.extraordinary}
    assert "time-powers-exist" in {r.id for r in kept.bible.rules}
    assert "time-powers" not in {k.id for k in released.bible.extraordinary}
    assert "time-powers-exist" not in {r.id for r in released.bible.rules}


def test_a_template_rule_wins_over_the_models_rule_with_the_same_id():
    template = starter("outer-disciple").template
    world = _world(rules=[RuleP(id="qi-exists", text="Qi is a myth.", fixed=False)])

    state = assemble(world, _character(), DraftOptions(template=template))

    rule = next(r for r in state.bible.rules if r.id == "qi-exists")
    assert (rule.text, rule.fixed) == (template.rules[0].text, True)
    assert sum(r.id == "qi-exists" for r in state.bible.rules) == 1


def test_releasing_the_grounded_rule_lets_the_world_have_powers():
    template = starter("naples-vendetta").template
    released = frozenset({"no-supernatural", "human-limits"})

    state = assemble(
        _world(), _character(), DraftOptions(template=template, released_rules=released)
    )

    assert not state.bible.grounded
    assert state.player.sheet.powers


# G8.


def test_a_grounded_world_has_no_powers_and_nobody_past_human_limits():
    world = samples.naples_world().model_copy(
        update={
            "npcs": [
                NpcP(
                    id="carmine",
                    name="Carmine Russo",
                    attributes=AttributesP(strength=9),
                    powers=[PowerP(id="p", name="evil eye", kind_id="supernatural")],
                )
            ]
        }
    )
    character = samples.naples_character().model_copy(
        update={
            "attributes": AttributesP(speed=10, nerve=8),
            "powers": [_time_stop(kind_id="supernatural")],
        }
    )

    state = assemble(world, character)

    for person in state.characters.values():
        assert person.sheet.powers == []
        assert max(person.sheet.attributes.model_dump().values()) == HUMAN_PEAK


def test_a_power_from_a_kind_the_world_lacks_is_dropped():
    character = _character(
        powers=[
            _time_stop(),
            PowerP(id="fire", name="fireball", kind_id="magic"),
            PowerP(id="aura", name="aura blade", kind_id=""),
        ]
    )

    state = assemble(_world(), character)

    assert [p.name for p in state.player.sheet.powers] == ["time stop"]


def test_a_power_from_a_kind_that_doesnt_exist_is_dropped():
    world = _world(
        extraordinary=[
            ExtraordinaryP(id="qi", kind="qi cultivation", prevalence="common"),
            ExtraordinaryP(id="time-powers", kind="powers over time", prevalence="none"),
        ]
    )

    state = assemble(world, _character())

    assert state.player.sheet.powers == []


def test_beyond_human_attributes_where_the_world_allows_them():
    state = assemble(_world(), _character(attributes=AttributesP(strength=8, wits=14)))

    attributes = state.player.sheet.attributes
    assert (attributes.strength, attributes.wits) == (8, 10)


def test_physics_is_the_players_pick():
    state = assemble(_world(), _character(), DraftOptions(physics=PhysicsMode.STRICT))

    assert state.bible.physics is PhysicsMode.STRICT


# G18.


def test_ladder_rungs_are_tiers_two_apart_and_a_rung_sets_its_axis():
    state = assemble(
        _world(),
        _character(ladders=[LadderPositionP(ladder_id="realms", rung="Core Formation")]),
    )

    [ladder] = state.bible.ladders
    assert [r.tier for r in ladder.rungs] == [2, 4, 6, 8, 10]
    assert state.player.sheet.ladders[0].rung == 2
    assert state.player.sheet.axes.might == 6
    zhao = state.characters["zhao"]
    assert zhao.sheet.axes.might == 4  # Foundation Establishment


def test_a_ladder_says_how_many_of_its_rungs_everyone_has_heard_of():
    # G18, C6: as many as the model says, the first at least and never more than there are.
    def known_to_all(said, *more):
        world = samples.cultivation_world()
        world.ladders[0].known_to_all = said
        world.ladders[0].rungs += [RungP(name=name) for name in more]
        return assemble(world, _character()).bible.ladders[0].known_to_all

    assert [known_to_all(said) for said in (4, 3, 0, -2, 99)] == [4, 3, 1, 1, 5]
    # Where the model doesn't say, the ones the summary would name (G1).
    assert known_to_all(None) == 5
    assert known_to_all(None, "Void Refinement", "Immortal Ascension") == 5
    short = samples.cultivation_world()
    short.ladders[0].known_to_all = None
    short.ladders[0].rungs = short.ladders[0].rungs[:3]
    assert assemble(short, _character()).bible.ladders[0].known_to_all == 3


def test_a_rung_is_found_by_its_name_inside_longer_words():
    state = assemble(
        _world(),
        _character(
            ladders=[LadderPositionP(ladder_id="cultivation realms", rung="peak Nascent Soul")]
        ),
    )

    assert state.player.sheet.ladders[0].rung == 3


@pytest.mark.parametrize(
    ("said", "stage", "hours"),
    [
        ("late", "late", 400 / 3),
        ("Peak", "peak", 200),
        ("mid stage", "middle", 200 / 3),
        ("early", "early", 0),
        ("", "", 0),
        # A world's own counting names none of the four, so the rank starts empty.
        ("third stage", "", 0),
    ],
)
def test_the_stage_a_draft_starts_them_at_is_where_their_rank_starts(said, stage, hours):
    # G19: one of four stages, which the rank never reads below.
    position = LadderPositionP(ladder_id="realms", rung="Foundation Establishment", stage=said)
    state = assemble(_world(), _character(ladders=[position]))

    assert state.player.sheet.ladders[0].stage == stage
    rank = growth.rank_of(state.player, state.bible.ladders[0])
    assert rank.rung.name == "Core Formation"
    assert rank.effort_s == pytest.approx(hours * HOUR)


def test_an_unknown_rung_or_ladder_gives_no_position():
    state = assemble(
        _world(),
        _character(
            ladders=[
                LadderPositionP(ladder_id="realms", rung="Immortal Emperor"),
                LadderPositionP(ladder_id="levels", rung="3"),
            ]
        ),
    )

    assert state.player.sheet.ladders == []


# G22.


def test_the_players_gift_strength_wins_over_the_premise_and_the_model():
    template = starter("three-heartbeats").template  # overpowered

    by_premise = assemble(_world(), _character(), DraftOptions(template=template))
    by_player = assemble(
        _world(), _character(), DraftOptions(template=template, gift=GiftStrength.SMALL)
    )
    by_model = assemble(_world(), _character(powers=[_time_stop(strength="rare")]))

    assert by_premise.player.sheet.powers[0].strength is GiftStrength.OVERPOWERED
    assert by_player.player.sheet.powers[0].strength is GiftStrength.SMALL
    assert by_model.player.sheet.powers[0].strength is GiftStrength.RARE


def test_a_gift_with_no_strength_is_rare():
    state = assemble(_world(), _character(powers=[_time_stop(strength=None)]))

    assert state.player.sheet.powers[0].strength is GiftStrength.RARE


def test_no_gift_removes_the_gift_and_keeps_ordinary_powers():
    ordinary = PowerP(id="sense", name="qi sense", kind_id="qi")
    character = _character(powers=[_time_stop(), ordinary])

    state = assemble(_world(), character, DraftOptions(gift=GiftStrength.NONE))

    assert [p.name for p in state.player.sheet.powers] == ["qi sense"]


def test_time_stop_lasts_three_heartbeats_and_hits_by_strength():
    overpowered = assemble(_world(), _character())
    modest = assemble(_world(), _character(), DraftOptions(gift=GiftStrength.RARE))
    custom = assemble(
        _world(),
        _character(
            powers=[_time_stop(time=TimeP(effect="stop", lasts_seconds=10, recharge_seconds=60))]
        ),
    )

    stop = overpowered.player.sheet.powers[0].time
    assert (stop.lasts_s, stop.recharge_s) == (STOP_LASTS_S, STOP_RECHARGE_S)
    assert stop.hit_mode is HitMode.RELATIVE_SPEED
    assert modest.player.sheet.powers[0].time.hit_mode is HitMode.NORMAL_FORCE
    assert (
        custom.player.sheet.powers[0].time.lasts_s,
        custom.player.sheet.powers[0].time.recharge_s,
    ) == (10, 60)


def test_a_rate_is_kept_only_for_haste_and_slow():
    state = assemble(
        _world(),
        _character(powers=[_time_stop(time=TimeP(effect="stop", rate=4.0))]),
    )

    assert state.player.sheet.powers[0].time.rate is None


# C6.


def test_the_player_knows_only_what_the_premise_says():
    state = assemble(samples.naples_world(), samples.naples_character())

    carmine = state.characters["carmine"]
    assert PLAYER_ID in carmine.known_by
    assert carmine.secrets and carmine.agenda is not None
    [mystery] = state.bible.mysteries
    assert mystery.answer and mystery.clues
    known = [f for f in state.facts.values() if PLAYER_ID in f.known_by]
    assert [f.text for f in known] == ["My father was shot dead outside his own club a week ago."]


def test_a_bodys_forgotten_past_is_a_secret_the_player_doesnt_know():
    state = assemble(_world(), _character())

    [fact] = [f for f in state.facts.values() if "twenty spirit stones" in f.text]
    assert fact.known_by == []


def test_people_the_player_hasnt_heard_of_stay_unknown():
    world = _world(
        npcs=[*_world().npcs, NpcP(id="ghost", name="Old Ghost Wu", player_knows="unknown")]
    )

    state = assemble(world, _character())

    assert PLAYER_ID not in state.characters["ghost"].known_by


def test_drafted_families_link_parents_and_children_by_id_or_name():
    """N6: two parents at most, never themselves, never someone who descends from them, and the
    player character's child names them by the player's name."""
    zhao, mo = _world().npcs
    world = _world(
        npcs=[
            zhao.model_copy(update={"parent_ids": ["pc"]}),  # Lin Feng names Zhao as his parent
            mo,
            NpcP(id="mei", name="Lin Mei", age=40, parent_ids=["elder-mo", "mei", "nobody"]),
            NpcP(id="little-bao", name="Little Bao", age=4, parent_ids=["Lin Feng", "mei"]),
            NpcP(id="wu", name="Wu Han", age=30, parent_ids=["little-bao", "zhao", "mei"]),
        ]
    )

    state = assemble(world, _character(parent_ids=["zhao"]))

    assert state.player.parent_ids == ["zhao"]
    assert state.characters["zhao"].parent_ids == []  # he can't also be Lin Feng's child
    assert state.characters["mei"].parent_ids == ["elder-mo"]
    assert state.characters["little-bao"].parent_ids == [PLAYER_ID, "mei"]
    assert state.characters["wu"].parent_ids == ["little-bao", "zhao"]
    assert check_state(state) == []


# W17.


def _grown(**changes) -> CharacterProposal:
    """Lin Feng at twenty-four: the sample has him at sixteen, too young for a romance (F3)."""
    look = "24, lean, black hair tied back, steady eyes."
    return _character(age=24, appearance=look, **changes)


def test_a_romance_the_premise_sets_up_is_on_record_as_the_story_opens():
    """A wife is a wife from the first scene: the bond, and how drawn she is to them. Someone
    the draft bound to them and gave no heart is as drawn as they are fond."""
    zhao, mo = _world().npcs
    world = _world(
        npcs=[
            zhao,
            mo,
            NpcP(
                id="mei",
                name="Su Mei",
                age=23,
                bond_with_player="married",
                attitude_to_player=AttitudeP(affinity=70, trust=80),
            ),
            NpcP(
                id="lan",
                name="Lan Yue",
                age=21,
                bond_with_player="promised",
                attitude_to_player=AttitudeP(affinity=10, attraction=5),  # an arranged match
            ),
            NpcP(id="hua", name="Hua", age=30, attitude_to_player=AttitudeP(attraction=60)),
        ]
    )

    state = assemble(world, _grown())

    wife = bonds.live(state, PLAYER_ID, "mei")
    assert (wife.id, wife.a_id, wife.b_id, wife.stage) == ("bond-1", PLAYER_ID, "mei", "married")
    assert wife.steps == [BondStep(stage=BondStage.MARRIED, how="As the story opens.")]
    assert state.characters["mei"].attitude_toward(PLAYER_ID).attraction == 70
    assert bonds.live(state, PLAYER_ID, "lan").stage is BondStage.PROMISED
    assert state.characters["lan"].attitude_toward(PLAYER_ID).attraction == 5
    # Someone who only loves them from afar has a heart on record and no bond.
    assert bonds.live(state, PLAYER_ID, "hua") is None
    assert state.characters["hua"].attitude_toward(PLAYER_ID).attraction == 60
    assert state.new_id("bond") == "bond-3"
    assert check_state(state) == []


def test_a_drafted_romance_is_between_recorded_adults_who_arent_family():
    zhao, mo = _world().npcs
    npcs = [
        zhao,
        mo,
        NpcP(id="mei", name="Su Mei", age=23, bond_with_player="together"),
        NpcP(id="pia", name="Pia", age=16, bond_with_player="together"),
        NpcP(id="bao", name="Bao", age=40, bond_with_player="married", parent_ids=["pc"]),
    ]
    # F3: a player character of sixteen is in no romance, whatever the draft says.
    assert assemble(_world(npcs=npcs), _character()).bonds == {}
    state = assemble(_world(npcs=npcs), _grown())
    assert [bond.b_id for bond in state.bonds.values()] == ["mei"]


def test_couples_among_the_cast_are_on_record_so_a_rival_exists():
    """W17: a husband the draft names is a husband from the first scene, so courting his wife
    wrongs someone who is on record. One bond for each pair, between recorded adults who
    aren't family, and nobody is drawn to the player character by it."""
    zhao, mo = _world().npcs
    world = _world(
        npcs=[
            zhao,
            mo,
            NpcP(id="mei", name="Su Mei", age=23, partner_id="han", partner_bond="married"),
            NpcP(id="han", name="Han Bo", age=30, partner_id="Su Mei"),  # the same two, once
            NpcP(id="lan", name="Lan Yue", age=21, partner_id="zhao"),  # a couple, no vows said
            NpcP(id="pia", name="Pia", age=16, partner_id="elder-mo"),  # F3
            NpcP(id="qin", name="Qin", age=40, partner_id="qin"),
            NpcP(id="rou", name="Rou", age=33, partner_id="nobody"),
            NpcP(id="son", name="Han Yi", age=19, parent_ids=["han"], partner_id="han"),
        ]
    )

    state = assemble(world, _grown())

    assert [(b.id, b.a_id, b.b_id, b.stage.value) for b in state.bonds.values()] == [
        ("bond-1", "mei", "han", "married"),
        ("bond-2", "lan", "zhao", "together"),
    ]
    assert all(b.steps[0].how == "As the story opens." for b in state.bonds.values())
    assert bonds.partners(state, "han") == ["mei"]
    assert bonds.wronged(state, PLAYER_ID, "mei") == ["han"]
    assert bonds.wronged(state, PLAYER_ID, "rou") == []
    assert state.characters["mei"].attitude_toward(PLAYER_ID).attraction == 0
    assert state.new_id("bond") == "bond-3"
    assert check_state(state) == []


def test_a_partner_who_is_the_player_character_is_their_romance():
    """The draft may write the player character's own wife as a partner by their id, which the
    prompt gives, or by their name. It is the same romance, written once, and the field that
    is theirs wins."""
    zhao, mo = _world().npcs
    world = _world(
        npcs=[
            zhao,
            mo,
            NpcP(
                id="mei",
                name="Su Mei",
                age=23,
                partner_id=PLAYER_ID,
                partner_bond="married",
                attitude_to_player=AttitudeP(affinity=60),
            ),
            NpcP(
                id="lan",
                name="Lan Yue",
                age=21,
                bond_with_player="courting",
                partner_id="Lin Feng",
                partner_bond="married",
            ),
        ]
    )

    state = assemble(world, _grown())

    assert [(b.a_id, b.b_id, b.stage.value) for b in state.bonds.values()] == [
        (PLAYER_ID, "mei", "married"),
        (PLAYER_ID, "lan", "courting"),
    ]
    assert state.characters["mei"].attitude_toward(PLAYER_ID).attraction == 60
    assert check_state(state) == []


def test_how_couples_hold_and_a_persons_own_faith_come_from_the_draft():
    """W17: the custom of the world says how faithful its people are, a key character is
    what the premise says of them, and a couple the draft makes have a heart for each other,
    so a partner stands in a suitor's way by how much of it there is."""
    zhao, mo = _world().npcs
    npcs = [
        zhao.model_copy(update={"age": 40, "partner_id": "mei", "partner_bond": "married"}),
        mo,
        NpcP(id="mei", name="Su Mei", age=23, faith="steadfast"),
        NpcP(id="lan", name="Lan Yue", age=21),
    ]

    held = assemble(_world(npcs=npcs), _grown())
    strict = assemble(_world(npcs=npcs, unions="for_life"), _grown())

    assert held.bible.unions is Unions.HELD and strict.bible.unions is Unions.FOR_LIFE
    assert held.characters["mei"].faith is Faith.STEADFAST
    assert held.characters["lan"].faith is None  # theirs by who they are (`bonds.faith`)
    for one, other in ((zhao.id, "mei"), ("mei", zhao.id)):
        heart = held.characters[one].attitude_toward(other).attraction
        assert heart == bonds.settled_heart(one, other)
        assert bonds.SETTLED <= heart <= bonds.SETTLED_TOP
    assert bonds.kept(held, "mei", PLAYER_ID) == zhao.id
    assert bonds.for_life(strict, "mei", zhao.id) and not bonds.for_life(held, "mei", zhao.id)
    assert check_state(held) == []


def test_someone_who_would_never_take_a_partner_is_so_from_the_draft():
    """W6: over the years the world may give anyone single a partner, so the draft says who
    never would take one, and everyone else is free to."""
    zhao, mo = _world().npcs
    npcs = [zhao, mo.model_copy(update={"solitary": True})]

    state = assemble(_world(npcs=npcs), _grown())

    assert state.characters[mo.id].solitary is True
    assert state.characters[zhao.id].solitary is False
    assert NpcP(id="lan", name="Lan Yue").solitary is False  # nobody is, unless the draft says
    assert check_state(state) == []


def test_several_partners_is_the_custom_only_where_the_draft_says_so():
    zhao, mo = _world().npcs
    npcs = [
        zhao,
        mo,
        NpcP(id="mei", name="Su Mei", age=23, bond_with_player="married"),
        NpcP(id="lan", name="Lan Yue", age=21, bond_with_player="married"),
        NpcP(id="hua", name="Hua", age=30),
    ]

    held = assemble(_world(npcs=npcs), _grown())
    custom = assemble(_world(npcs=npcs, several_partners=True), _grown())

    # Two wives from the story's first day have no claim on each other, and a third romance
    # wrongs both, unless the world's custom is that it wrongs nobody.
    assert held.bible.several_partners is False and custom.bible.several_partners is True
    assert bonds.wronged(held, PLAYER_ID, "mei") == []
    assert bonds.wronged(held, PLAYER_ID, "hua") == ["mei", "lan"]
    assert bonds.wronged(custom, PLAYER_ID, "hua") == []


def test_a_reference_to_the_player_character_by_their_id_holds():
    """The prompt gives the player character's id, so a child who names them by it is theirs.
    Before 2026-11-13 only their name resolved, and the id the prompt asks for was dropped."""
    zhao, mo = _world().npcs
    child = NpcP(id="little-bao", name="Little Bao", age=4, parent_ids=[PLAYER_ID])

    state = assemble(_world(npcs=[zhao, mo, child]), _grown())

    assert state.characters["little-bao"].parent_ids == [PLAYER_ID]
    assert check_state(state) == []


# W15.


def test_at_most_eight_key_characters_and_four_factions_start_active():
    world = _world(
        factions=[FactionP(id=f"f{i}", name=f"Faction {i}", kind="sect") for i in range(7)],
        npcs=[NpcP(id=f"n{i}", name=f"Disciple Number {i}") for i in range(11)],
    )

    state = assemble(world, _character(memberships=[]))

    active_npcs = [c for c in state.npcs() if c.activity is Activity.ACTIVE]
    active_factions = [f for f in state.factions.values() if f.activity is Activity.ACTIVE]
    assert len(active_npcs) == ACTIVE_NPCS
    assert len(active_factions) == ACTIVE_FACTIONS
    assert check_state(state) == []


def test_a_goal_is_an_aim_never_the_premise_handed_back():
    # G2: a drafter asked for the player's own words can copy all of them.
    premise = "I'm a squire about to take the knight exam in 3 days, and I never summoned aura."
    character = samples.cultivation_character()
    character.goals = [f"  {premise.upper()} ", "Pass the knight exam.", premise[:-1]]

    state = assemble(samples.cultivation_world(), character, DraftOptions(premise=premise))

    assert [goal.text for goal in state.goals.values()] == ["Pass the knight exam."]
    # A premise that is one aim in whole is still that aim in the drafter's shorter words.
    character.goals = ["Become the pirate king."]
    options = DraftOptions(premise="I want to become the pirate king.")
    state = assemble(samples.cultivation_world(), character, options)
    assert [goal.text for goal in state.goals.values()] == ["Become the pirate king."]


def test_the_clocks_a_proposal_gives_are_the_states_in_its_order():
    world = samples.cultivation_world()
    tournament = world.clocks[0]
    world.clocks = [
        tournament.model_copy(update={"id": "empty", "steps": [" "]}),
        tournament.model_copy(update={"id": "The Tournament!", "name": "The tournament"}),
        tournament,
    ]

    kept = drafted_clocks(world)
    state = assemble(world, samples.cultivation_character(), DraftOptions(premise="A story."))

    # A clock with no steps is none, and each of the others is the state's clock in its place.
    assert [clock.id for clock in kept] == ["The Tournament!", "tournament"]
    assert list(state.clocks) == ["the-tournament", "tournament"]


def test_clocks_step_in_world_time_with_no_turns():
    state = assemble(samples.naples_world(), samples.naples_character())

    clock = state.clocks["council"]
    assert clock.interval_s == 60 * 3600
    assert clock.next_step_s == clock.interval_s
    assert clock.remaining == 4


def test_extraordinary_prevalence_none_means_grounded():
    world = _world(
        extraordinary=[ExtraordinaryP(id="qi", kind="qi cultivation", prevalence="none")],
        rules=[],
    )

    state = assemble(world, _character())

    assert state.bible.grounded
    assert all(k.prevalence is Prevalence.NONE for k in state.bible.extraordinary)


# --- talent (A4) ------------------------------------------------------------------------------


def _talents(*proposed: TalentP):
    state = assemble(
        _world(),
        _character(talents=list(proposed)),
        DraftOptions(premise=samples.CULTIVATION_PREMISE),
    )
    assert check_state(state) == []
    return state.player.sheet.talents


def test_the_talents_the_player_described_go_on_the_sheet_with_ids_of_their_own():
    sword = TalentP(
        name="  The sword ",
        covers="Anything fought with a blade.",
        strength="one_of_a_kind",
        reason="Born under the Sword Star.",
    )
    fighting = TalentP(name="Hopeless at haggling", strength="slow")

    first, second = _talents(sword, fighting)

    assert (first.id, first.name, first.strength) == (
        "the-sword",
        "The sword",
        TalentStrength.ONE_OF_A_KIND,
    )
    assert (first.covers, first.reason, first.general) == (
        "Anything fought with a blade.",
        "Born under the Sword Star.",
        False,
    )
    assert (second.id, second.strength) == ("hopeless-at-haggling", TalentStrength.SLOW)


def test_a_character_with_no_talent_in_the_premise_has_none():
    assert _talents() == []


def test_one_of_a_kind_at_everything_is_drafted_as_a_general_genius():
    (everything,) = _talents(
        TalentP(name="Prodigy", covers="everything", strength="one_of_a_kind", general=True)
    )

    assert (everything.strength, everything.general) == (TalentStrength.GENIUS, True)


def test_past_three_one_of_a_kind_talents_the_rest_are_drafted_as_genius():
    names = ["The sword", "Extreme perception", "Command of the body", "Fire", "Poison"]

    drafted = _talents(*(TalentP(name=name, strength="one_of_a_kind") for name in names))

    one_of_a_kind, genius = TalentStrength.ONE_OF_A_KIND, TalentStrength.GENIUS
    assert [t.strength for t in drafted] == [one_of_a_kind] * 3 + [genius] * 2


def test_a_talent_is_listed_once_and_a_runaway_list_is_cut():
    twice = _talents(TalentP(name="The sword"), TalentP(name="the sword", strength="genius"))
    many = _talents(*(TalentP(name=f"Talent {n}") for n in range(20)))

    assert [(t.id, t.strength) for t in twice] == [("the-sword", TalentStrength.KNACK)]
    assert len(many) == 6


def test_only_the_player_character_is_drafted_with_talents():
    state = assemble(
        _world(),
        _character(talents=[TalentP(name="The sword")]),
        DraftOptions(premise=samples.CULTIVATION_PREMISE),
    )

    assert all(not npc.sheet.talents for npc in state.npcs())
