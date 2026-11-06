"""The code that turns the drafter's proposal into the opening world state (G1, G2, G7, G8,
G18, G22, C6, W15). The model proposes; these rules decide."""

import pytest

from engine.context import Language
from engine.invariants import check_state
from engine.state import (
    Activity,
    GiftStrength,
    HitMode,
    PhysicsMode,
    Prevalence,
    RuleTopic,
)
from graph.drafting import samples
from graph.drafting.assemble import (
    ACTIVE_FACTIONS,
    ACTIVE_NPCS,
    GROUNDED_RULE_TEXT,
    GROUNDED_RULE_TEXT_ES,
    HUMAN_PEAK,
    PLAYER_FALLBACK_NAME,
    STOP_LASTS_S,
    STOP_RECHARGE_S,
    DraftOptions,
    assemble,
    slug,
)
from graph.drafting.catalog import starter
from graph.drafting.schema import (
    PLAYER_ID,
    AttributesP,
    CharacterProposal,
    ExtraordinaryP,
    FactionP,
    LadderPositionP,
    NpcP,
    PowerP,
    RuleP,
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
    ] == [GROUNDED_RULE_TEXT_ES]
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


def test_a_rung_is_found_by_its_name_inside_longer_words():
    state = assemble(
        _world(),
        _character(
            ladders=[LadderPositionP(ladder_id="cultivation realms", rung="peak Nascent Soul")]
        ),
    )

    assert state.player.sheet.ladders[0].rung == 3


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
