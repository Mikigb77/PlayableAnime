"""Drafting, revising and editing a draft through the model layer, on the fake model (G1, G2,
G7, G22). One model call for a draft, one per revision, none for edits code can make alone."""

import asyncio
from dataclasses import replace

import pytest

from engine.context import Language
from engine.state import GiftStrength, PhysicsMode, Unions
from engine.visibility import memory_view
from graph.drafting import chain, samples
from graph.drafting.catalog import starter
from graph.drafting.direct import Fields
from graph.drafting.prompts import SYSTEM, WORLD_CHANGE, current_rules
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


def test_a_fixed_rule_outlasts_a_change_that_forgets_to_drop_it(fake, llm):
    """G7: a starter's fixed rule goes only when the change names it, so a model that removes
    the 'nothing supernatural' kind and keeps quiet about the rule leaves the world grounded."""
    change = WorldChange(
        extraordinary=[ExtraordinaryP(id="vampires", kind="vampires", prevalence="hidden")],
        removed=[RemovalP(section="extraordinary", id="supernatural")],
    )
    fake.script(Node.DRAFTER, Reply(json=change))

    revised = run(chain.revise(llm, _naples_draft(), "world", "Add hidden vampires."))

    assert revised.released_rules == frozenset()
    state = revised.state()
    assert state.bible.grounded
    assert "no-supernatural" in {r.id for r in state.bible.rules}


def test_a_character_revision_replaces_only_the_character(fake, llm):
    character = samples.naples_character()
    character.name = "Gennaro Esposito"
    fake.script(Node.DRAFTER, Reply(json=character))
    draft = _naples_draft()

    revised = run(chain.revise(llm, draft, "character", "Rename me Gennaro."))

    assert fake.calls(Node.DRAFTER)[0].json_schema["title"] == "CharacterProposal"
    assert revised.state().player.name == "Gennaro Esposito"
    assert revised.proposal.world == draft.proposal.world


def test_a_change_asked_at_a_part_of_the_summary_says_which(fake, llm):
    # "Better at this" says what "this" is: the line the player asked it at, as they read it.
    fake.script(Node.DRAFTER, Reply(json=samples.naples_character()))
    draft = _naples_draft()
    skills = "Skilled: pistol. Fair: knife, driving."

    run(chain.revise(llm, draft, "character", "Better at this.", about=skills))

    asked = _prompt_text(fake.calls(Node.DRAFTER)[0])
    about = f"They ask it about this part of the summary they read:\n{skills}"
    assert f"Better at this.\n\n{about}" in asked
    # With no part, the request stands alone.
    fake.script(Node.DRAFTER, Reply(json=samples.naples_character()))
    run(chain.revise(llm, draft, "character", "Older."))
    assert "They ask it about" not in _prompt_text(fake.calls(Node.DRAFTER)[1])


def test_a_revision_keeps_the_names_the_draft_holds_now(fake, llm):
    # A name the player changed since the premise is the one in the draft, and the drafter is
    # told the draft's is the one to keep.
    fake.script(Node.DRAFTER, Reply(json=WorldChange()))
    plan = chain.plan_edit(_naples_draft(), chain.Edits(fields=Fields(name="Marco Esposito")))

    run(chain.revise(llm, plan.draft, "world", "More rain."))

    asked = _prompt_text(fake.calls(Node.DRAFTER)[0])
    assert '"name": "Marco Esposito"' in asked
    assert "the draft's is the one to keep" in asked


# Edit.


def test_the_plain_fields_are_edits_code_makes_alone(fake, llm):
    # G1, G2 (Miki, 2026-11-10): a name, an age, a look, a title: no model, at once.
    draft = _naples_draft()
    fields = Fields(
        name="Marco Esposito",
        age=31,
        looks="Tall, a broken nose, a camel coat.",
        manner="Laughs first, counts later.",
        title="The Long Summer",
        tone="Dry and tender",
    )

    plan = chain.plan_edit(draft, chain.Edits(fields=fields))
    edited = run(chain.finish_edit(llm, plan))

    assert not plan.needs_model
    assert fake.requests == []
    state = edited.state()
    assert (state.player.name, state.player.age) == ("Marco Esposito", 31)
    assert state.player.appearance == "Tall, a broken nose, a camel coat."
    assert state.player.description == "Laughs first, counts later."
    assert (state.bible.title, state.bible.tone) == ("The Long Summer", "Dry and tender")
    assert character_lines(state)[0] == "Marco Esposito, 31."
    # Everyone else is who they were.
    assert [c.name for c in state.npcs()] == [c.name for c in draft.state().npcs()]


def test_a_new_name_keeps_what_the_player_named_under_it(fake, llm):
    # G1: a goal that says the old name is the same goal under the new one.
    character = samples.cultivation().character
    named = character.model_copy(update={"goals": ["Show the elders what Lin Feng is worth"]})
    fake.script(Node.DRAFTER, Reply(json=named))
    asked = "My goal is to show the elders what Lin Feng is worth."
    draft = run(chain.revise(llm, _cultivation_draft(), "character", asked))
    assert draft.told == {"goal:show the elders what lin feng is worth"}

    edited = chain.plan_edit(draft, chain.Edits(fields=Fields(name="Zhang Wei"))).draft

    assert edited.told == {"goal:show the elders what zhang wei is worth"}
    lines = character_lines(edited.state(), edited.language, edited.said)
    assert "Goal: Show the elders what Zhang Wei is worth." in lines


def test_plain_fields_and_a_rewritten_line_go_together(fake, llm):
    # The line is compared with the summary as the plain fields left it, so the name alone
    # asks the model for nothing.
    draft = _naples_draft()
    renamed = chain.plan_edit(draft, chain.Edits(fields=Fields(name="Marco Esposito"))).draft
    lines = character_lines(renamed.state(), renamed.language, renamed.said)

    plan = chain.plan_edit(
        draft, chain.Edits(fields=Fields(name="Marco Esposito"), character_lines=lines)
    )

    assert not plan.needs_model
    assert plan.draft.state().player.name == "Marco Esposito"

    # Nor do the lines as the player read them before the name changed: an app that sends the
    # whole screen back with a new name asks the model for nothing.
    read = character_lines(draft.state(), draft.language, draft.said)
    assert read != lines
    plan = chain.plan_edit(
        draft, chain.Edits(fields=Fields(name="Marco Esposito"), character_lines=read)
    )

    assert not plan.needs_model
    assert plan.draft.state().player.name == "Marco Esposito"


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

    shown = (state, draft.language, draft.said)
    plan = chain.plan_edit(
        draft,
        chain.Edits(world_lines=world_lines(*shown), character_lines=character_lines(*shown)),
    )

    assert not plan.needs_model
    assert plan.written == ()


def test_rewritten_lines_ask_the_model_to_match_them(fake, llm):
    draft = _naples_draft()
    fake.script(Node.DRAFTER, Reply(json=WorldChange(era="Naples, 1975: the heat of summer")))

    lines = world_lines(draft.state(), draft.language, draft.said)
    lines[1] = "Naples, 1975: the heat of summer."
    edited = run(chain.edit(llm, draft, chain.Edits(world_lines=lines)))

    [request] = fake.calls(Node.DRAFTER)
    text = _prompt_text(request)
    assert "The player rewrote the world summary" in text
    assert "- Naples, 1975: the heat of summer." in text
    assert edited.state().bible.era == "Naples, 1975: the heat of summer"


def test_what_the_player_asks_for_is_theirs_to_see(fake, llm):
    # G1: the tournament is the story's surprise until the player's own words name it.
    draft = _cultivation_draft()
    hidden = world_lines(draft.state(), draft.language, draft.said)
    assert not any("tournament" in line for line in hidden)
    fake.script(Node.DRAFTER, Reply(json=WorldChange()))

    revised = run(chain.revise(llm, draft, "world", "The ranking tournament is in two days."))

    # The draft keeps what they named, the deadline, never their words. The goal the drafter
    # made of it is still the story's: a time set for the tournament says no aim.
    named = {"clock:tournament"}
    assert revised.told == named
    shown = world_lines(revised.state(), revised.language, revised.said)
    assert "The ranking tournament: in 2 days." in shown
    # It stays through a later change that names nothing.
    fake.script(Node.DRAFTER, Reply(json=WorldChange()))
    again = run(chain.revise(llm, revised, "world", "More rain."))
    assert again.told == named


def test_a_goal_is_theirs_once_their_words_say_it_as_an_aim(fake, llm):
    # G1, G2 (Miki, 2026-11-10): the first goal is the story's surprise unless the player's
    # words give it. Words that only tell of the tournament give no goal about it.
    draft = _cultivation_draft()

    def goals(words: str = "", **how) -> list[str]:
        asked = draft
        if words:
            fake.script(Node.DRAFTER, Reply(json=draft.proposal.character))
            asked = run(chain.revise(llm, draft, "character", words, **how))
        lines = character_lines(asked.state(), asked.language, asked.said)
        return [line for line in lines if line.startswith("Goal:")]

    survive = ["Goal: Survive the ranking tournament."]
    assert goals() == []
    assert goals("The ranking tournament is brutal, and few survive it.") == []
    assert goals("I have to survive the ranking tournament.") == survive
    assert goals("I entered the sect to survive the ranking tournament.") == survive
    # Asked at the goal's own row, the words are about what the character is after.
    assert goals("Survive the ranking tournament, whatever it takes.") == []
    assert goals("Survive the ranking tournament, whatever it takes.", aim=True) == survive


def test_a_story_opens_on_the_drafts_state_with_what_was_read_and_what_was_not():
    # G1, G18, C6: the rung the draft's rules named is heard of, and the rival, the elder, the
    # goal and the tournament, which the bare premise never named, are held back from Memory.
    draft = _cultivation_draft()

    opened = chain.opening(draft)

    assert ("realms", 4) in [(h.ladder_id, h.rung) for h in opened.player.sheet.rungs_heard]
    assert opened.untold == ["goal:goal-1", "person:elder-mo", "person:zhao", "thread:tournament"]
    assert (memory_view(opened).people, memory_view(opened).goals) == ([], [])
    # The draft's own state is the one its screen reads, and is never changed.
    assert (draft.state().untold, draft.state().player.sheet.rungs_heard) == ([], [])
    assert [p.name for p in memory_view(draft.state()).people] == ["Elder Mo", "Zhao Kun"]

    # What a change of theirs named is theirs to see from the first moment.
    asked = _cultivation_draft(told=frozenset({"person:zhao", "clock:tournament"}))
    assert chain.opening(asked).untold == ["goal:goal-1", "person:elder-mo"]
    # A draft whose every opener their words named holds nothing back.
    spoken = "I must survive the ranking tournament. Zhao Kun and Elder Mo are watching me."
    assert chain.opening(replace(draft, premise=spoken)).untold == []


def test_a_deadline_comes_when_the_premise_says_whatever_the_steps_add_up_to(fake, llm):
    # E2, G1: the drafter wrote three steps of 16 hours, two days in all, for a tournament the
    # premise sets in five days.
    premise = samples.CULTIVATION_PREMISE + " The ranking tournament is in five days."
    fake.script(Node.DRAFTER, Reply(json=samples.cultivation()))

    draft = run(chain.create(llm, premise, rating="teen"))

    # The same three steps, spread over the time the player gave, on the draft's own record.
    [clock] = draft.proposal.world.clocks
    assert len(clock.steps) == 3 and clock.step_every_hours == 40
    tournament = draft.state().clocks["tournament"]
    assert tournament.interval_s * tournament.remaining == 5 * 24 * 3600
    shown = world_lines(draft.state(), draft.language, draft.said)
    assert "The ranking tournament: in 5 days." in shown
    # A premise that sets it no time leaves the drafter's steps as they are.
    fake.script(Node.DRAFTER, Reply(json=samples.cultivation()))
    plain = run(chain.create(llm, samples.CULTIVATION_PREMISE, rating="teen"))
    assert plain.proposal.world.clocks[0].step_every_hours == 16


def test_a_deadline_the_player_moves_stays_where_they_moved_it(fake, llm):
    premise = samples.CULTIVATION_PREMISE + " The ranking tournament is in five days."
    fake.script(Node.DRAFTER, Reply(json=samples.cultivation()))
    draft = run(chain.create(llm, premise, rating="teen"))

    # A change that gives it a new time: the drafter answers with nothing, and code sets it.
    fake.script(Node.DRAFTER, Reply(json=WorldChange()))
    moved = run(chain.revise(llm, draft, "world", "Make the tournament in a week."))
    assert "The ranking tournament: in 7 days." in world_lines(
        moved.state(), moved.language, moved.said
    )
    # A later change says nothing of it, and the premise's five days don't come back.
    fake.script(Node.DRAFTER, Reply(json=WorldChange()))
    later = run(chain.revise(llm, moved, "world", "More rain."))
    assert later.proposal.world.clocks == moved.proposal.world.clocks
    # A time asked for at the character's box is the player's word all the same.
    fake.script(Node.DRAFTER, Reply(json=samples.cultivation().character))
    sooner = run(chain.revise(llm, later, "character", "I fight in the tournament in 3 days."))
    assert "The ranking tournament: in 3 days." in world_lines(
        sooner.state(), sooner.language, sooner.said
    )


def test_a_goal_the_player_asked_for_keeps_its_place_when_a_change_rewords_it(fake, llm):
    draft = _cultivation_draft()
    assert not any(
        line.startswith("Goal:")
        for line in character_lines(draft.state(), draft.language, draft.said)
    )
    character = samples.cultivation().character
    fake.script(Node.DRAFTER, Reply(json=character.model_copy(update={"goals": ["Avenge Mei"]})))
    revised = run(chain.revise(llm, draft, "character", "My goal is to avenge Mei."))
    assert revised.told == {"goal:avenge mei"}

    # The next change says the same goal in other words: it is still the one they asked for.
    reworded = character.model_copy(update={"goals": ["Avenge Mei's death"], "age": 17})
    fake.script(Node.DRAFTER, Reply(json=reworded))
    older = run(chain.revise(llm, revised, "character", "Make him 17."))
    assert older.told == {"goal:avenge mei's death"}
    lines = character_lines(older.state(), older.language, older.said)
    assert "Goal: Avenge Mei's death." in lines

    # And a change that takes the goal away takes its key with it.
    fake.script(Node.DRAFTER, Reply(json=character.model_copy(update={"goals": []})))
    gone = run(chain.revise(llm, older, "character", "He has no goal yet."))
    assert gone.told == frozenset()


def test_a_line_the_player_wrote_is_theirs_and_the_drafters_words_in_it_are_not(fake, llm):
    draft = _naples_draft()
    lines = world_lines(draft.state(), draft.language, draft.said)
    family = "The Esposito family: Three crews and a council that picks the boss."
    assert family in lines and "The council picks the next boss: in 10 days." not in lines

    # A word changed in a drafted line: only that word is the player's, so the council's vote
    # stays the story's surprise.
    changed = [line.replace("Three crews", "Four crews") for line in lines]
    plan = chain.plan_edit(draft, chain.Edits(world_lines=changed))
    assert plan.written == ("Four",)
    fake.script(Node.DRAFTER, Reply(json=WorldChange()))
    edited = run(chain.finish_edit(llm, plan))
    assert edited.told == frozenset()
    # A line of their own is theirs whole, and what it names shows from then on.
    added = [*lines, "The council picks the next boss in ten days."]
    plan = chain.plan_edit(draft, chain.Edits(world_lines=added))
    assert plan.written == ("The council picks the next boss in ten days",)
    fake.script(Node.DRAFTER, Reply(json=WorldChange()))
    edited = run(chain.finish_edit(llm, plan))
    assert edited.told == {"clock:council"}
    shown = world_lines(edited.state(), edited.language, edited.said)
    assert "The council picks the next boss: in 10 days." in shown
    # The model is told what the summary leaves out, so it keeps what the lines don't mention.
    assert "that neither list mentions stays as it is" in _prompt_text(fake.calls(Node.DRAFTER)[-1])


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


# A starter's own words in the story's language (S10).


def test_a_starters_template_is_drafted_in_the_storys_language(fake, llm):
    """S10: the drafter is given the starter's fixed rules in the language it writes in, and
    code holds the draft to them in that language, so a Spanish world has no English rule."""
    fake.script(Node.DRAFTER, Reply(json=samples.cultivation()))

    draft = run(
        chain.create(
            llm,
            samples.CULTIVATION_PREMISE,
            rating="teen",
            premise_id="three-heartbeats",
            language=Language.ES,
        )
    )

    [request] = fake.calls(Node.DRAFTER)
    text = _prompt_text(request)
    qi = "El cultivo del qi es real, y los fuertes ascienden por los reinos."
    time = "Unos pocos pueden doblegar el tiempo, y casi nadie lo sabe."
    assert f"qi-exists: {qi}" in text and f"time-powers-exist: {time}" in text
    assert "Qi cultivation is real" not in text
    assert "Condensación de Qi, Establecimiento de la Base, Formación del Núcleo" in text
    rules = {r.id: r.text for r in draft.state().bible.rules}
    assert (rules["qi-exists"], rules["time-powers-exist"]) == (qi, time)
    assert draft.released_rules == frozenset()
    # The same starter in English is as it was.
    english = _cultivation_draft()
    assert english.template is starter("three-heartbeats").template
    assert "Qi cultivation is real, and the strong climb the realms." in {
        r.text for r in english.state().bible.rules
    }


def test_a_starters_rule_held_in_english_is_still_held_in_a_spanish_draft():
    """A draft made before the template spoke its language shows the starter's rules in
    English. Sending them back as they are must not let them go (G7)."""
    draft = _naples_draft(language=Language.ES)
    shown = public_rules(draft.state())
    spanish = {r.id: r.text for r in shown}
    assert spanish["human-limits"] == "Nadie puede hacer más de lo que podría una persona real."
    english = {r.id: r.text for r in starter("naples-vendetta").template.rules}
    as_before = [
        chain.RuleEdit(id=r.id, text=english.get(r.id, r.text), fixed=r.fixed) for r in shown
    ]

    held = chain.plan_edit(draft, chain.Edits(rules=as_before)).draft

    assert held.released_rules == frozenset()
    assert held.state().bible.grounded
    # Its own words are another matter: a rewritten rule is the player's, and is let go.
    rewritten = [
        chain.RuleEdit(
            id=r.id,
            text="Casi nadie puede hacer más." if r.id == "human-limits" else r.text,
            fixed=r.fixed,
        )
        for r in shown
    ]
    assert chain.plan_edit(draft, chain.Edits(rules=rewritten)).draft.released_rules == {
        "human-limits"
    }


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


def test_a_change_sets_the_custom_of_several_partners_only_when_it_says_so():
    """W17: a change that says nothing of it leaves the custom as it was, whichever way."""
    draft = _naples_draft()
    assert draft.proposal.world.several_partners is False

    custom, _ = _merge(WorldChange(several_partners=True), draft)
    assert custom.several_partners is True
    kept, _ = chain.apply_change(custom, current_rules(draft.state()), WorldChange(tone="noir"))
    assert kept.several_partners is True and kept.tone == "noir"
    back, _ = chain.apply_change(
        kept, current_rules(draft.state()), WorldChange(several_partners=False)
    )
    assert back.several_partners is False


def test_a_change_sets_how_couples_hold_only_when_it_says_so():
    """W17: a change that says nothing of the custom leaves it as it was."""
    draft = _naples_draft()
    assert draft.proposal.world.unions is Unions.HELD

    strict, _ = _merge(WorldChange(unions=Unions.FOR_LIFE), draft)
    assert strict.unions is Unions.FOR_LIFE
    kept, _ = chain.apply_change(strict, current_rules(draft.state()), WorldChange(tone="noir"))
    assert kept.unions is Unions.FOR_LIFE and kept.tone == "noir"


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


def _cultivation_with_open_rule() -> tuple[chain.Draft, list[RuleP]]:
    draft = _cultivation_draft()
    cost = RuleP(
        id="time-costs-years",
        text="Each use of a time power costs a year of life.",
        fixed=False,
        topic="limits",
        about=["time-powers"],
    )
    return draft, [*current_rules(draft.state()), cost]


def test_removing_a_kind_takes_its_open_rules_along_and_keeps_its_fixed_ones():
    draft, rules = _cultivation_with_open_rule()
    gone = RemovalP(section="extraordinary", id="time-powers")

    world, let_go = chain.apply_change(draft.proposal.world, rules, WorldChange(removed=[gone]))

    assert "time-powers" not in {k.id for k in world.extraordinary}
    assert {r.id for r in world.rules} == {"qi-exists", "time-powers-exist", "realm-ceiling"}
    assert let_go == frozenset()

    change = WorldChange(removed=[gone], dropped_rule_ids=["time-powers-exist"])
    world, let_go = chain.apply_change(draft.proposal.world, rules, change)

    assert {r.id for r in world.rules} == {"qi-exists", "realm-ceiling"}
    assert let_go == {"time-powers-exist"}


def test_a_fixed_rule_listed_as_removed_stays_until_the_change_drops_it():
    removed = [RemovalP(section="rules", id="human-limits"), RemovalP(section="rules", id="omerta")]

    world, let_go = _merge(WorldChange(removed=removed))

    assert [r.id for r in world.rules] == ["no-supernatural", "human-limits"]
    assert let_go == frozenset()


def test_a_removal_that_could_mean_two_records_or_none_removes_nothing():
    draft = _naples_draft()
    vampires = WorldChange(
        extraordinary=[ExtraordinaryP(id="vampires", kind="vampires", prevalence="hidden")],
        peoples=[PeopleP(id="vampires", name="Vampires")],
    )
    world, _ = _merge(vampires, draft)
    with_vampires = replace(
        draft, proposal=DraftProposal(world=world, character=draft.proposal.character)
    )

    again, _ = _merge(
        WorldChange(
            removed=[
                RemovalP(section="monsters", id="vampires"),  # a kind and a people: which?
                RemovalP(section="stuff", id="the-moon"),  # in no list at all
            ]
        ),
        with_vampires,
    )

    assert again == world


def test_a_record_given_a_new_id_by_mistake_brings_its_references_back_to_the_old_one():
    draft = _naples_draft()
    carmine = draft.proposal.world.npcs[0]
    opening = draft.proposal.world.opening
    change = WorldChange(
        npcs=[carmine.model_copy(update={"id": "carmine-russo", "description": "Grey now."})],
        opening=opening.model_copy(
            update={"present_ids": ["player", "carmine-russo", "bartender"]}
        ),
    )

    world, _ = _merge(change, draft)

    assert [n.id for n in world.npcs] == [n.id for n in draft.proposal.world.npcs]
    assert world.npcs[0].description == "Grey now."
    assert world.opening.present_ids == ["player", "carmine", "bartender"]
    again = replace(draft, proposal=DraftProposal(world=world, character=draft.proposal.character))
    assert set(again.state().characters) == set(draft.state().characters)
    assert again.state().scene.present_ids == draft.state().scene.present_ids


def test_a_kind_given_a_new_id_by_mistake_is_matched_by_what_it_is():
    draft = _cultivation_draft()
    rare = ExtraordinaryP(id="qi-cultivation", kind="qi cultivation", prevalence="rare")
    rule = RuleP(
        id="qi-is-scarce",
        text="Few are born able to gather qi.",
        fixed=False,
        topic="limits",
        about=["qi-cultivation"],
    )

    world, _ = _merge(WorldChange(extraordinary=[rare], rules=[rule]), draft)

    assert [k.id for k in world.extraordinary] == ["qi", "time-powers"]
    assert world.extraordinary[0].prevalence == "rare"
    assert next(r for r in world.rules if r.id == "qi-is-scarce").about == ["qi"]


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


def test_the_drafter_is_asked_for_the_cast_s_couples_and_no_romance_of_its_own_making():
    """W17: who among the key characters is a couple is the world's, so a rival can exist. A
    romance with the player character is the premise's to set up or the story's to find."""
    assert "Give nobody else a romance with the player character or any attraction" in SYSTEM
    assert "Record each couple on one of the two, with partner_id and partner_bond." in SYSTEM
    assert "A couple that hides it is a secret instead." in SYSTEM
    assert "several_partners only where having several partners at once is the custom" in SYSTEM
    assert "opening, several_partners or unions only if the change alters them" in WORLD_CHANGE
    # How faithful its people are is the world's custom, and a person's own where the premise
    # says it (Miki, 2026-11-13).
    assert "Set unions to how couples hold in this world" in SYSTEM
    assert "Give a key character faith only where the premise or who they plainly are" in SYSTEM
    # People lead lives of their own, so the draft only says who never would (W6).
    assert "anyone single may find a partner in time: set solitary only for someone" in SYSTEM


def test_the_drafter_is_asked_for_the_whole_ladder_and_the_rungs_everyone_knows():
    """G18, C6: the ladder reaches the world's strongest beings, and only its common rungs are
    told at the start."""
    assert "up to the rung its strongest beings stand on" in SYSTEM
    assert "known_to_all says how many of its rungs, counted from the lowest" in SYSTEM
    assert "or a ladder's higher rungs" in SYSTEM
    # W6, G19: whether climbing it lengthens life, and how long each rung then lives.
    assert "lengthens_life says whether a higher rung means a longer life" in SYSTEM
    assert "then every rung gives lifespan_years" in SYSTEM
    assert "that only measure skill, strength or standing lengthen no life" in SYSTEM
    assert "neither does a ladder that gives no years" in SYSTEM
    # G18: whoever has the ladder's power stands on it, so the world knows who outranks whom.
    assert "Everyone who has the power a ladder measures stands on it" in SYSTEM
    assert "Only someone with none of that power has no rung." in SYSTEM


def test_the_drafter_is_asked_for_talents_only_from_the_players_own_words():
    """A4, G2: how fast the character learns each thing, written when they are made, and
    never read off how strong they are. In the first live drafts half the characters were one
    of a kind at something: the strongest sorcerer alive at perception, a chess prodigy at
    openings, a boy good at everything at everything."""
    assert "- Talents say how fast the character learns, never how good they already are." in (
        SYSTEM
    )
    assert '"the strongest sorcerer alive"' in SYSTEM and "give no talent" in SYSTEM
    assert "Write a talent only where the player's own words speak of how they learn" in SYSTEM
    assert "copy those words into said" in SYSTEM
    assert "never from how strong the character is" in SYSTEM
    assert "genius for a genius or a prodigy" in SYSTEM
    assert "only where their words put the talent beyond anyone else's" in SYSTEM
    assert "Between two strengths take the lower" in SYSTEM
    assert "One of a kind is always at the one thing the player named" in SYSTEM
    assert "three such talents at most" in SYSTEM
    assert "A power, an eye, a body or a skill of their own is no talent, however rare" in SYSTEM
    assert "nobody is one of a kind at everything" in SYSTEM


def test_the_drafter_gives_a_power_only_where_the_premise_does_and_says_what_it_does():
    """A8, G22: someone the premise makes ordinary stays ordinary. In the first live drafts
    a courtesan who charms people got a power over minds, and most powers said nothing of
    what they do."""
    assert "only where the premise gives the character one or anyone in their place" in SYSTEM
    assert "someone the premise makes ordinary stays ordinary" in SYSTEM
    assert "Each power says what it does in a sentence or two the player reads" in SYSTEM
    assert "A premise that gives them no gift leaves them without one." in SYSTEM
    assert "Give them the level the premise's words say, no more and no less" in SYSTEM
    # A name is never written the way an id is.
    assert "An id is never a name" in SYSTEM
