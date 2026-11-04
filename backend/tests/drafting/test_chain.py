"""Drafting, revising and editing a draft through the model layer, on the fake model (G1, G2,
G7, G22). One model call for a draft, one per revision, none for edits code can make alone."""

import asyncio
from dataclasses import replace

import pytest

from engine.state import GiftStrength, PhysicsMode
from graph.drafting import chain, samples
from graph.drafting.prompts import current_rules
from graph.drafting.schema import (
    DraftProposal,
    ExtraordinaryP,
    NpcP,
    PeopleP,
    PlaceP,
    RemovalP,
    RuleP,
    WorldChange,
)
from graph.drafting.view import character_lines, gift_strength, public_rules, world_lines
from graph.llm import (
    Block,
    Fail,
    FakeBackend,
    LLMBlocked,
    LLMUnavailable,
    ModelClient,
    ModelConfig,
    Node,
    Reply,
    TurnTelemetry,
)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fake() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def llm(fake) -> ModelClient:
    return ModelClient(
        fake, ModelConfig(), rating="teen", recorder=TurnTelemetry(), retry_delay_s=0
    )


def _prompt_text(request) -> str:
    return request.prompt.system + "\n" + "\n".join(m.text for m in request.prompt.messages)


def _naples_draft(**changes) -> chain.Draft:
    return chain.Draft(
        premise=samples.NAPLES_PREMISE,
        proposal=samples.naples(),
        premise_id="naples-vendetta",
        **changes,
    )


def _cultivation_draft(**changes) -> chain.Draft:
    return chain.Draft(
        premise=samples.CULTIVATION_PREMISE,
        proposal=samples.cultivation(),
        premise_id="three-heartbeats",
        **changes,
    )


# Create.


def test_a_draft_is_one_model_call_with_the_premise_and_its_genre(fake, llm):
    proposal = samples.naples()
    proposal.world.dropped_rule_ids = ["omerta"]
    fake.script(Node.DRAFTER, Reply(json=proposal))

    draft = run(
        chain.create(llm, samples.NAPLES_PREMISE, rating="mature", premise_id="naples-vendetta")
    )

    [request] = fake.calls(Node.DRAFTER)
    text = _prompt_text(request)
    assert samples.NAPLES_PREMISE in text
    assert "no-supernatural: Grounded: no magic and nothing supernatural" in text
    assert "Rating: Mature 17+" in text
    assert request.json_schema["title"] == "DraftProposal"
    assert draft.rating == "mature" and draft.premise_id == "naples-vendetta"
    assert draft.proposal.world.dropped_rule_ids == []  # only a revision drops rules
    assert draft.state().bible.grounded


def test_the_players_gift_pick_goes_into_the_prompt(fake, llm):
    fake.script(Node.DRAFTER, Reply(json=samples.cultivation()))

    draft = run(
        chain.create(
            llm,
            samples.CULTIVATION_PREMISE,
            rating="teen",
            gift=GiftStrength.SMALL,
            physics=PhysicsMode.STRICT,
        )
    )

    assert "special gift is small" in _prompt_text(fake.requests[0])
    state = draft.state()
    assert gift_strength(state) is GiftStrength.SMALL
    assert state.bible.physics is PhysicsMode.STRICT


def test_model_failures_reach_the_caller(fake, llm):
    fake.script(Node.DRAFTER, Block(stage="prompt"))
    with pytest.raises(LLMBlocked):
        run(chain.create(llm, samples.NAPLES_PREMISE, rating="teen"))

    fake.script(Node.DRAFTER, Fail(), Fail())
    with pytest.raises(LLMUnavailable):
        run(chain.create(llm, samples.NAPLES_PREMISE, rating="teen"))


# Revise.


def test_a_world_revision_asks_for_only_the_change_and_keeps_everything_else(fake, llm):
    fake.script(Node.DRAFTER, Reply(json=WorldChange(title="Blood on the Bay")))
    draft = _naples_draft()

    revised = run(chain.revise(llm, draft, "world", "Call it Blood on the Bay."))

    [request] = fake.calls(Node.DRAFTER)
    assert request.json_schema["title"] == "WorldChange"
    text = _prompt_text(request)
    assert "Call it Blood on the Bay." in text
    assert "Reply with only what the change touches" in text
    assert '"answer"' in text  # the model sees the whole draft, hidden parts included
    assert '"known_to_player": true' not in text  # but not the fields left at their defaults
    assert revised.state().bible.title == "Blood on the Bay"
    before, after = draft.state(), revised.state()
    assert after.model_copy(update={"bible": before.bible}) == before
    assert after.bible.model_copy(update={"title": before.bible.title}) == before.bible
    assert revised.proposal.character == draft.proposal.character


def test_races_asked_for_in_plain_words_join_the_world(fake, llm):
    """The change Miki asked for on 2026-11-04, which failed when the model had to write the
    whole world back."""
    fake.script(
        Node.DRAFTER,
        Reply(
            json=WorldChange(
                peoples=[
                    PeopleP(id="vampires", name="Vampires", lifespan_years=None),
                    PeopleP(id="orcs", name="Orcs", lifespan_years=60),
                    PeopleP(id="demons", name="Demons"),
                ]
            )
        ),
    )
    draft = _cultivation_draft()

    revised = run(chain.revise(llm, draft, "world", "Add vampires, orcs and demons as races."))

    peoples = [p.name for p in revised.state().bible.peoples]
    assert peoples[-3:] == ["Vampires", "Orcs", "Demons"]
    assert peoples[:-3] == [p.name for p in draft.state().bible.peoples]
    assert "Peoples: " in " ".join(world_lines(revised.state()))
    assert public_rules(revised.state()) == public_rules(draft.state())


def test_a_revision_changes_only_the_rules_it_gives(fake, llm):
    rule = RuleP(id="omerta", text="Nobody talks to the police.", fixed=False)
    fake.script(Node.DRAFTER, Reply(json=WorldChange(rules=[rule])))

    revised = run(chain.revise(llm, _naples_draft(), "world", "Make it rain more."))

    rules = {r.id: r for r in revised.state().bible.rules}
    assert {"no-supernatural", "human-limits", "omerta"} <= set(rules)
    assert rules["no-supernatural"].fixed
    assert rules["omerta"].text == "Nobody talks to the police."
    assert revised.released_rules == frozenset()


def test_a_revision_can_drop_a_genre_rule_when_the_player_asks(fake, llm):
    change = WorldChange(
        extraordinary=[ExtraordinaryP(id="vampires", kind="vampires", prevalence="hidden")],
        rules=[
            RuleP(
                id="vampires-hidden",
                text="Vampires hide among the living.",
                fixed=True,
                topic="existence",
                about=["vampires"],
            )
        ],
        removed=[RemovalP(section="extraordinary", id="supernatural")],
        dropped_rule_ids=["no-supernatural", "human-limits"],
    )
    fake.script(Node.DRAFTER, Reply(json=change))

    revised = run(chain.revise(llm, _naples_draft(), "world", "Add hidden vampires."))

    state = revised.state()
    assert revised.released_rules == {"no-supernatural", "human-limits"}
    assert not state.bible.grounded
    assert {r.id for r in state.bible.rules} == {"omerta", "vampires-hidden"}
    assert {k.id for k in state.bible.extraordinary} == {"vampires"}
    assert revised.proposal.world.dropped_rule_ids == []


def test_removing_a_kind_takes_the_rules_about_it_along(fake, llm):
    """A world that loses its 'nothing supernatural' kind loses the rule saying so, even when
    the model forgets to drop it, and a starter's rule among them is released (G7)."""
    change = WorldChange(
        extraordinary=[ExtraordinaryP(id="vampires", kind="vampires", prevalence="hidden")],
        removed=[RemovalP(section="extraordinary", id="supernatural")],
    )
    fake.script(Node.DRAFTER, Reply(json=change))

    revised = run(chain.revise(llm, _naples_draft(), "world", "Add hidden vampires."))

    assert revised.released_rules == {"no-supernatural"}
    state = revised.state()
    assert not state.bible.grounded
    assert "no-supernatural" not in {r.id for r in state.bible.rules}


def test_a_character_revision_replaces_only_the_character(fake, llm):
    character = samples.naples_character()
    character.name = "Gennaro Esposito"
    fake.script(Node.DRAFTER, Reply(json=character))
    draft = _naples_draft()

    revised = run(chain.revise(llm, draft, "character", "Rename me Gennaro."))

    assert fake.calls(Node.DRAFTER)[0].json_schema["title"] == "CharacterProposal"
    assert revised.state().player.name == "Gennaro Esposito"
    assert revised.proposal.world == draft.proposal.world


# Edit.


def test_physics_and_gift_none_are_edits_code_makes_alone(fake, llm):
    draft = _cultivation_draft()

    plan = chain.plan_edit(draft, chain.Edits(physics=PhysicsMode.STRICT, gift=GiftStrength.NONE))
    edited = run(chain.finish_edit(llm, plan))

    assert not plan.needs_model
    assert fake.requests == []
    state = edited.state()
    assert state.bible.physics is PhysicsMode.STRICT
    assert gift_strength(state) is GiftStrength.NONE
    assert state.player.sheet.powers == []


def test_unchanged_lines_need_no_model_call():
    draft = _naples_draft()
    state = draft.state()

    plan = chain.plan_edit(
        draft,
        chain.Edits(world_lines=world_lines(state), character_lines=character_lines(state)),
    )

    assert not plan.needs_model


def test_rewritten_lines_ask_the_model_to_match_them(fake, llm):
    draft = _naples_draft()
    fake.script(Node.DRAFTER, Reply(json=WorldChange(era="Naples, 1975: the heat of summer")))

    lines = world_lines(draft.state())
    lines[1] = "Naples, 1975: the heat of summer."
    edited = run(chain.edit(llm, draft, chain.Edits(world_lines=lines)))

    [request] = fake.calls(Node.DRAFTER)
    text = _prompt_text(request)
    assert "The player rewrote the world summary" in text
    assert "- Naples, 1975: the heat of summer." in text
    assert edited.state().bible.era == "Naples, 1975: the heat of summer"


def test_a_stronger_gift_asks_the_model_for_a_new_gift(fake, llm):
    draft = _cultivation_draft(gift=GiftStrength.SMALL)
    fake.script(Node.DRAFTER, Reply(json=samples.cultivation_character()))

    edited = run(chain.edit(llm, draft, chain.Edits(gift=GiftStrength.OVERPOWERED)))

    [request] = fake.calls(Node.DRAFTER)
    assert "picked 'overpowered'" in _prompt_text(request)
    assert gift_strength(edited.state()) is GiftStrength.OVERPOWERED


def test_rules_set_by_the_player_stay_word_for_word(fake, llm):
    draft = _naples_draft()
    rule = RuleP(id="omerta", text="The model's own wording.", fixed=True)
    fake.script(Node.DRAFTER, Reply(json=WorldChange(rules=[rule])))
    edits = chain.Edits(
        rules=[
            chain.RuleEdit(
                id="no-supernatural",
                text="Grounded: no magic and nothing supernatural, and that won't change.",
                fixed=True,
            ),
            chain.RuleEdit(id="omerta", text="Nobody talks, ever.", fixed=True),
            chain.RuleEdit(text="Every street has a saint.", fixed=False),
        ]
    )

    edited = run(chain.edit(llm, draft, edits))

    assert len(fake.calls(Node.DRAFTER)) == 1
    rules = [(r.id, r.text, r.fixed) for r in public_rules(edited.state())]
    assert rules == [
        (
            "no-supernatural",
            "Grounded: no magic and nothing supernatural, and that won't change.",
            True,
        ),
        ("omerta", "Nobody talks, ever.", True),
        ("every-street-has-a-saint", "Every street has a saint.", False),
    ]
    # The player removed the genre's human-limits rule, so it no longer holds (G7).
    assert edited.released_rules == {"human-limits"}


def test_opening_up_a_genre_rule_releases_it_with_no_model_call(fake, llm):
    draft = _naples_draft()
    rules = [
        chain.RuleEdit(id=r.id, text=r.text, fixed=r.id != "human-limits")
        for r in public_rules(draft.state())
    ]

    plan = chain.plan_edit(draft, chain.Edits(rules=rules))

    assert not plan.needs_model
    assert plan.draft.released_rules == {"human-limits"}
    rule = next(r for r in plan.draft.state().bible.rules if r.id == "human-limits")
    assert not rule.fixed


# Merging a change (G1).


def _merge(change: WorldChange, draft: chain.Draft | None = None):
    draft = draft or _naples_draft()
    return chain.apply_change(draft.proposal.world, current_rules(draft.state()), change)


def test_an_empty_change_leaves_the_world_exactly_as_it_was():
    draft = _naples_draft()

    world, let_go = _merge(WorldChange(), draft)

    again = replace(draft, proposal=DraftProposal(world=world, character=draft.proposal.character))
    assert again.state() == draft.state()
    assert let_go == frozenset()


def test_a_change_replaces_records_by_id_adds_new_ones_and_removes_what_it_lists():
    draft = _naples_draft()
    places = draft.proposal.world.places
    bar = places[1].model_copy(update={"mood": "empty, after the raid"})
    change = WorldChange(
        places=[bar, PlaceP(id="docks", name="the docks", kind="wilds")],
        removed=[RemovalP(section="places", id=places[2].id)],
    )

    world, _ = _merge(change, draft)

    assert [p.id for p in world.places] == [places[0].id, bar.id, *[p.id for p in places[3:]]] + [
        "docks"
    ]
    assert world.places[1].mood == "empty, after the raid"
    assert world.npcs == draft.proposal.world.npcs


def test_a_removal_that_names_its_list_a_little_off_still_removes_the_record():
    draft = _naples_draft()
    place = draft.proposal.world.places[-1].id
    npc = draft.proposal.world.npcs[-1].id

    world, _ = _merge(
        WorldChange(
            removed=[
                RemovalP(section="Place", id=place),  # the singular
                RemovalP(section="characters", id=npc),  # no such list: wherever the id is
            ]
        ),
        draft,
    )

    assert place not in {p.id for p in world.places}
    assert npc not in {n.id for n in world.npcs}
    assert world.factions == draft.proposal.world.factions


def test_a_record_matched_by_its_name_keeps_its_id_so_references_hold():
    draft = _naples_draft()
    npc = draft.proposal.world.npcs[0]
    renamed = NpcP(id="someone-new", name=npc.name, description="Older now, and tired.")

    world, _ = _merge(WorldChange(npcs=[renamed]), draft)

    assert [n.id for n in world.npcs] == [n.id for n in draft.proposal.world.npcs]
    assert world.npcs[0].description == "Older now, and tired."


def test_a_rewritten_fixed_rule_stays_in_place_and_lets_the_old_one_go():
    draft = _naples_draft()
    rule = RuleP(id="human-limits", text="Nobody can outrun a bullet.", fixed=True)

    world, let_go = _merge(WorldChange(rules=[rule], dropped_rule_ids=["human-limits"]), draft)

    assert [r.id for r in world.rules] == [r.id for r in current_rules(draft.state())]
    assert next(r for r in world.rules if r.id == "human-limits").text == rule.text
    assert let_go == {"human-limits"}


def test_texts_and_parts_change_only_when_the_change_gives_them():
    draft = _naples_draft()
    before = draft.proposal.world

    world, _ = _merge(WorldChange(era="Naples, 1980", norms=["Debts are paid in blood."]), draft)

    assert (world.era, world.norms) == ("Naples, 1980", ["Debts are paid in blood."])
    assert (world.title, world.summary, world.nature) == (
        before.title,
        before.summary,
        before.nature,
    )
    assert (world.calendar, world.opening) == (before.calendar, before.opening)


def test_a_draft_round_trips_through_json():
    draft = _cultivation_draft()

    again = DraftProposal.model_validate(draft.proposal.model_dump(mode="json"))

    assert again == draft.proposal


# What the review of the first version found.


def test_rules_set_before_drafting_join_the_drafted_ones_in_one_call(fake, llm):
    fake.script(Node.DRAFTER, Reply(json=samples.naples()))

    draft = run(
        chain.create(
            llm,
            samples.NAPLES_PREMISE,
            rating="teen",
            premise_id="naples-vendetta",
            rules=[
                chain.RuleEdit(text="Every street has a saint.", fixed=False),
                chain.RuleEdit(id="omerta", text="Nobody talks, ever.", fixed=True),
            ],
        )
    )

    assert len(fake.requests) == 1
    assert "- Every street has a saint." in _prompt_text(fake.requests[0])
    rules = {r.id: (r.text, r.fixed) for r in draft.state().bible.rules}
    assert rules["omerta"] == ("Nobody talks, ever.", True)
    assert rules["every-street-has-a-saint"] == ("Every street has a saint.", False)
    assert {"no-supernatural", "human-limits"} <= set(rules)
    assert draft.released_rules == frozenset()


def test_the_model_cant_release_a_starter_rule_the_player_kept(fake, llm):
    draft = _naples_draft()
    change = WorldChange(dropped_rule_ids=["no-supernatural", "human-limits"])
    fake.script(Node.DRAFTER, Reply(json=change))
    rules = [
        chain.RuleEdit(id=r.id, text=r.text, fixed=r.fixed) for r in public_rules(draft.state())
    ]
    rules.append(chain.RuleEdit(text="Every street has a saint.", fixed=False))

    edited = run(chain.edit(llm, draft, chain.Edits(rules=rules)))

    assert edited.released_rules == frozenset()
    assert edited.state().bible.grounded


def test_restoring_a_starter_rule_word_for_word_holds_it_again():
    draft = _naples_draft()
    rules = public_rules(draft.state())
    without = [chain.RuleEdit(id=r.id, text=r.text, fixed=r.fixed) for r in rules[1:]]
    released = chain.plan_edit(draft, chain.Edits(rules=without)).draft
    assert "no-supernatural" in released.released_rules

    restored = chain.plan_edit(
        released,
        chain.Edits(rules=[chain.RuleEdit(id=r.id, text=r.text, fixed=r.fixed) for r in rules]),
    ).draft

    assert restored.released_rules == frozenset()


def test_a_rule_the_guard_hides_survives_an_edit_of_the_shown_ones():
    world = samples.naples_world()
    world.rules.append(RuleP(id="leak", text=world.mysteries[0].answer, fixed=False))
    draft = chain.Draft(
        premise=samples.NAPLES_PREMISE,
        proposal=DraftProposal(world=world, character=samples.naples_character()),
    )
    shown = [
        chain.RuleEdit(id=r.id, text=r.text, fixed=r.fixed) for r in public_rules(draft.state())
    ]

    plan = chain.plan_edit(draft, chain.Edits(rules=shown))

    assert not plan.needs_model
    assert "leak" in {r.id for r in plan.draft.state().bible.rules}


def test_lowering_the_rating_redrafts_both_halves_and_raising_it_doesnt():
    draft = _naples_draft(rating="mature")

    lowered = chain.plan_edit(draft, chain.Edits(rating="teen"))
    raised = chain.plan_edit(_naples_draft(rating="teen"), chain.Edits(rating="mature"))

    assert lowered.draft.rating == "teen"
    assert len(lowered.world_asks) == len(lowered.character_asks) == 1
    assert "Rating: Teen" in lowered.world_asks[0]
    assert raised.draft.rating == "mature" and not raised.needs_model


def test_a_draft_builds_its_state_once():
    draft = _naples_draft()

    assert draft.state() is draft.state()
    assert replace(draft, physics=PhysicsMode.STRICT).state() is not draft.state()
