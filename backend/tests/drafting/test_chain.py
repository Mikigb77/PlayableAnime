"""Drafting, revising and editing a draft through the model layer, on the fake model (G1, G2,
G7, G22). One model call for a draft, one per revision, none for edits code can make alone."""

import asyncio
from dataclasses import replace

import pytest

from engine.state import GiftStrength, PhysicsMode
from graph.drafting import chain, samples
from graph.drafting.schema import DraftProposal, ExtraordinaryP, RuleP, WorldProposal
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


def test_a_world_revision_replaces_the_world_and_keeps_the_character(fake, llm):
    world = samples.naples_world()
    world.title = "Blood on the Bay"
    fake.script(Node.DRAFTER, Reply(json=world))
    draft = _naples_draft()

    revised = run(chain.revise(llm, draft, "world", "Call it Blood on the Bay."))

    [request] = fake.calls(Node.DRAFTER)
    assert request.json_schema["title"] == "WorldProposal"
    text = _prompt_text(request)
    assert "Call it Blood on the Bay." in text
    assert '"answer"' in text  # the model sees the whole draft, hidden parts included
    assert revised.proposal.world.title == "Blood on the Bay"
    assert revised.proposal.character == draft.proposal.character


def test_a_revision_keeps_the_fixed_rules_the_model_forgot(fake, llm):
    world = samples.naples_world()
    world.rules = [RuleP(id="omerta", text="Nobody talks to the police.", fixed=False)]
    fake.script(Node.DRAFTER, Reply(json=world))

    revised = run(chain.revise(llm, _naples_draft(), "world", "Make it rain more."))

    rules = {r.id: r for r in revised.state().bible.rules}
    assert {"no-supernatural", "human-limits", "omerta"} <= set(rules)
    assert rules["no-supernatural"].fixed
    assert revised.released_rules == frozenset()


def test_a_revision_can_drop_a_genre_rule_when_the_player_asks(fake, llm):
    world = samples.naples_world().model_copy(
        update={
            "extraordinary": [
                ExtraordinaryP(id="vampires", kind="vampires", prevalence="hidden"),
            ],
            "rules": [
                RuleP(
                    id="vampires-hidden",
                    text="Vampires hide among the living.",
                    fixed=True,
                    topic="existence",
                    about=["vampires"],
                )
            ],
            "dropped_rule_ids": ["no-supernatural", "human-limits"],
        }
    )
    fake.script(Node.DRAFTER, Reply(json=world))

    revised = run(chain.revise(llm, _naples_draft(), "world", "Add hidden vampires."))

    state = revised.state()
    assert revised.released_rules == {"no-supernatural", "human-limits"}
    assert not state.bible.grounded
    assert {r.id for r in state.bible.rules} == {"vampires-hidden"}
    assert revised.proposal.world.dropped_rule_ids == []


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
    world = samples.naples_world()
    world.era = "Naples, 1975: the heat of summer"
    fake.script(Node.DRAFTER, Reply(json=world))

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
    world = samples.naples_world()
    world.rules = [RuleP(id="omerta", text="The model's own wording.", fixed=True)]
    fake.script(Node.DRAFTER, Reply(json=world))
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


def test_keep_fixed_rules_adds_back_what_was_not_dropped():
    previous = [
        RuleP(id="a", text="A.", fixed=True),
        RuleP(id="b", text="B.", fixed=True),
        RuleP(id="c", text="C.", fixed=False),
    ]
    world = WorldProposal(title="", genre="", tone="", era="", dropped_rule_ids=["b"])

    kept = chain.keep_fixed_rules(previous, world)

    assert [r.id for r in kept.rules] == ["a"]


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
    world = samples.naples_world()
    world.dropped_rule_ids = ["no-supernatural", "human-limits"]
    fake.script(Node.DRAFTER, Reply(json=world))
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
