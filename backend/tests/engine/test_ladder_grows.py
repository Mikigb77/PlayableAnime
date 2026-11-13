"""A ladder gains a rung above its top in the middle of a story (G18, G7): the story names it
and code decides whether it holds (`engine.path.beyond_problem`, `engine.apply`)."""

import pytest

from engine import path
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, TIER_MAX, YEAR
from engine.context import TurnContext
from engine.contracts import (
    CharacterChange,
    GrowthKind,
    Intent,
    NewRung,
    OutcomeClass,
    StateDelta,
)
from engine.resolve.power import base_tier, rungs_above
from engine.resolve.powers import growth
from engine.samples import cultivation_world
from engine.state import Gain, LadderPosition, PowerAxis, RuleTopic, Rung, RungHeard, WorldRule
from engine.world import old_age
from tests.engine.resolve.power_worlds import play, train

TOP = 4  # Soul Transformation, the highest rung the sample world was drafted with
VOID = "Void Refinement"


def at_the_top() -> object:
    """The sample world with Lin Feng standing on its ladder's highest rung."""
    state = cultivation_world()
    state.world_s = 400 * DAY
    state.player.sheet.ladders = [LadderPosition(ladder_id="realms", rung=TOP)]
    return state


def told(state, **rung):
    """A scene that names a rung above the realms, as a turn settles it: the narrator's update
    applied, and the scene's words heard (`engine.path.hear`)."""
    new = NewRung(**({"ladder_id": "realms", "name": VOID} | rung))
    delta = StateDelta(rungs=[new], characters=rung_people(rung))
    applied = apply_delta(
        state, delta, TurnContext(story_id="s1", turn=9), source=DeltaSource.NARRATOR
    )
    path.hear(applied.state, f"“Above it lies {new.name},” the voice says.")
    return applied


def rung_people(rung) -> list[CharacterChange]:
    return [
        CharacterChange(id=who, name=who.replace("-", " ").title(), age=900)
        for who in rung.get("stands", [])
        if who.startswith("new-")
    ]


def realms(state):
    return state.bible.ladder("realms")


def reasons(applied) -> list[str]:
    return [r.reason for r in applied.rejected]


def test_the_story_puts_a_rung_above_the_top_once_it_has_reached_the_top():
    state = at_the_top()

    applied = told(state, description="Where the soul leaves the body behind.")

    assert not applied.rejected
    ladder = realms(applied.state)
    assert [rung.name for rung in ladder.rungs][-2:] == ["Soul Transformation", VOID]
    new = ladder.rungs[-1]
    # As far above the last rung as the ladder's rungs lie apart, and dated.
    assert (new.tier, new.added_s) == (12, 400 * DAY)
    assert new.description == "Where the soul leaves the body behind."
    # Nobody has told a way there, and the record can't say how long its people live.
    assert (new.needs, new.lifespan_years) == ([], None)
    # The world it was told to is untouched.
    assert len(realms(state).rungs) == TOP + 1


def test_nobody_stands_on_a_new_rung_by_its_being_told():
    # A4: the rung is somewhere to climb to. Nobody, the player character included, is on it.
    state = at_the_top()

    after = told(state).state

    assert all(
        position.rung <= TOP
        for character in after.characters.values()
        for position in character.sheet.ladders
    )


def test_the_rungs_the_world_has_are_told_first():
    # The player character has heard of nothing above Qi Condensation: the ladder still has
    # rungs to tell, so nothing goes above it yet.
    state = cultivation_world()

    applied = told(state)

    assert len(realms(applied.state).rungs) == TOP + 1
    assert reasons(applied) == [
        "the story hasn't told them of Soul Transformation yet: the rungs it has come first"
    ]
    assert path.top_problem(state, realms(state)) == reasons(applied)[0]


def test_hearing_of_the_top_is_reaching_it():
    # From a low rung too, once a scene has named the ladder's highest to them.
    state = cultivation_world()
    state.player.sheet.rungs_heard = [RungHeard(ladder_id="realms", rung=TOP, heard_s=DAY)]

    assert path.top_told(state, realms(state))
    assert not told(state).rejected


def test_where_everyone_has_heard_of_every_rung_the_top_is_told_from_the_start():
    state = cultivation_world()
    realms(state).known_to_all = TOP + 1

    assert path.top_problem(state, realms(state)) is None


def test_a_rung_takes_a_name_no_rung_has():
    state = at_the_top()

    again = told(state, name="nascent soul")
    blank = told(state, name="?")

    assert reasons(again) == ["cultivation realms already has a rung called nascent soul"]
    assert reasons(blank) == ["'?' isn't a name"]
    assert len(realms(again.state).rungs) == len(realms(blank.state).rungs) == TOP + 1


def test_a_ladder_gains_one_rung_in_a_scene():
    state = at_the_top()
    delta = StateDelta(
        rungs=[
            NewRung(ladder_id="realms", name=VOID),
            NewRung(ladder_id="realms", name="Body Integration"),
            NewRung(ladder_id="titles", name="Sovereign"),
        ]
    )

    applied = apply_delta(
        state, delta, TurnContext(story_id="s1", turn=9), source=DeltaSource.NARRATOR
    )

    assert [rung.name for rung in realms(applied.state).rungs][-1] == VOID
    assert reasons(applied) == [
        f"the story hasn't told them of {VOID} yet: the rungs it has come first",
        "no such ladder",
    ]


def test_a_rung_the_story_added_is_climbed_before_the_ladder_grows_again():
    state = told(at_the_top()).state
    ladder = realms(state)

    refused = told(state, name="Body Integration")

    assert reasons(refused) == [
        "nobody has climbed to Void Refinement yet, and the ladder grows no faster than that"
    ]
    # Lin Feng breaks through to it: the next rung can be told.
    state.player.sheet.ladders = [LadderPosition(ladder_id="realms", rung=TOP + 1)]
    state.player.sheet.growth.append(
        Gain(what=VOID, change="", source=GrowthKind.BREAKTHROUGH.value, reason="years of it")
    )
    assert path.climbed_to(state, VOID)
    assert path.top_problem(state, ladder) is None
    assert not told(state, name="Body Integration").rejected


def test_only_a_breakthrough_to_that_rung_is_a_climb_to_it():
    state = told(at_the_top()).state
    zhao = state.characters["zhao"].sheet
    # Someone's breakthrough to another rung, and a gain that is no breakthrough at all.
    zhao.growth.append(
        Gain(what="Core Formation", change="", source=GrowthKind.BREAKTHROUGH.value, reason="years")
    )
    zhao.growth.append(
        Gain(
            what=VOID, change="", source=GrowthKind.TECHNIQUE.value, reason="a manual of that name"
        )
    )

    assert not path.climbed_to(state, VOID)
    assert told(state, name="Body Integration").rejected

    # A breakthrough to it that was lost again is no climb either.
    zhao.growth.append(
        Gain(what=VOID, change="", source=GrowthKind.BREAKTHROUGH.value, reason="fell", loss=True)
    )
    assert not path.climbed_to(state, VOID)


def test_whoever_came_with_a_rung_never_climbed_to_it():
    # The beings a rung arrived with stand on it, and the ladder still waits for a climber.
    state = told(at_the_top(), stands=["new-sovereign"]).state

    assert not path.climbed_to(state, VOID)
    assert path.top_problem(state, realms(state)) is not None


def test_a_rule_that_never_changes_holds_the_ladder_where_it_is():
    # G7: a fixed rule on how far the power goes, naming the highest rung, ends the ladder.
    state = at_the_top()
    ceiling = next(rule for rule in state.bible.rules if rule.id == "realm-ceiling")
    assert not ceiling.fixed and path.top_problem(state, realms(state)) is None  # open: no bar

    ceiling.fixed = True

    assert told(state).rejected[0].reason == (
        "a rule that never changes holds the ladder at Soul Transformation (G7)"
    )
    # A fixed rule about something else that names the rung says nothing of how far it goes.
    ceiling.topic = RuleTopic.LAW
    assert path.top_problem(state, realms(state)) is None
    state.bible.rules.append(
        WorldRule(
            id="r", text="Nobody ever passes Nascent Soul.", fixed=True, topic=RuleTopic.LIMITS
        )
    )
    assert path.top_problem(state, realms(state)) is None  # it names a rung under the top


@pytest.mark.parametrize(
    ("tiers", "above"),
    [
        ((2, 4, 6, 8, 10), 12),  # two tiers a rung
        ((1, 2, 3), 4),
        ((1, 2, 4, 8), 10),  # the usual gap, never the widest
        ((5,), 6),  # a ladder of one rung: a tier up
        ((3, 3, 3), 4),  # rungs on the same tier: a tier up all the same
        ((10, 15, TIER_MAX - 2), TIER_MAX),  # no further than the scale goes
        ((10, TIER_MAX), None),  # nothing stands above the end of the scale
    ],
)
def test_a_new_rung_stands_as_far_above_the_top_as_the_rungs_lie_apart(tiers, above):
    state = at_the_top()
    ladder = realms(state)
    ladder.rungs = [Rung(name=f"Rank {i}", tier=tier) for i, tier in enumerate(tiers)]
    state.player.sheet.ladders = [LadderPosition(ladder_id="realms", rung=len(tiers) - 1)]

    assert path.above_tier(ladder) == above
    applied = told(state)
    if above is None:
        assert reasons(applied) == [
            f"nothing stands above Rank {len(tiers) - 1}: the scale ends there"
        ]
    else:
        assert realms(applied.state).rungs[-1].tier == above


def test_a_new_rung_is_as_loud_to_break_through_to_as_the_last():
    state = at_the_top()
    realms(state).rungs[-1].loud = True

    assert realms(told(state).state).rungs[-1].loud


def test_who_the_scene_brought_in_can_come_standing_on_it():
    # The beings the story reached past the top for: new in this same update, so that is who
    # they are. They stand above everyone the world held.
    state = at_the_top()

    applied = told(state, stands=["new-sovereign", "new-herald"])

    assert not applied.rejected
    after = applied.state
    for who in ("new-sovereign", "new-herald"):
        being = after.characters[who]
        assert [(p.ladder_id, p.rung) for p in being.sheet.ladders] == [("realms", TOP + 1)]
        assert being.sheet.axes.might == base_tier(after, being, PowerAxis.MIGHT) == 12
        # One rung above the player character at the old top, on the world's own scale.
        assert rungs_above(after, PowerAxis.MIGHT, after.player, being)[0] == 1
        # The record can't say how long they live, so old age takes none of them (A2).
        assert old_age.open_ended(after, being)


def test_nobody_on_record_is_lifted_onto_a_new_rung():
    # A4 (Miki, 2026-11-13: "to all power-ups there should be a reason"): the rung is climbed.
    state = at_the_top()

    applied = told(state, stands=["elder-mo", "lin", "nobody-at-all"])

    refusal = "only someone this scene brought in comes standing on it: nobody is lifted"
    assert reasons(applied) == [refusal] * 3
    after = applied.state
    assert len(realms(after).rungs) == TOP + 2  # the rung itself holds
    assert after.characters["elder-mo"].sheet.ladders == state.characters["elder-mo"].sheet.ladders
    assert after.player.sheet.ladders == state.player.sheet.ladders


def test_three_come_with_a_rung_at_most():
    state = at_the_top()
    people = ["new-one", "new-two", "new-three", "new-four"]

    applied = told(state, stands=[*people, "new-one"])

    assert reasons(applied) == ["three come with a rung at most"]
    after = applied.state
    assert [bool(after.characters[who].sheet.ladders) for who in people] == [
        True,
        True,
        True,
        False,
    ]


def test_someone_new_whose_rung_was_refused_stands_on_none():
    # The ladder holds where it is, and whoever the scene brought in is in the story all the
    # same, on no rung.
    state = cultivation_world()

    applied = told(state, stands=["new-sovereign"])

    after = applied.state
    assert len(realms(after).rungs) == TOP + 1
    assert after.characters["new-sovereign"].sheet.ladders == []


def test_the_scene_that_names_a_new_rung_is_where_they_hear_of_it():
    # C6: heard of from the scene that named it, and confirmed before whoever stands on it.
    state = at_the_top()
    delta = StateDelta(
        rungs=[NewRung(ladder_id="realms", name=VOID, stands=["new-sovereign"])],
        characters=[CharacterChange(id="new-sovereign", name="The Sovereign", meets_player=True)],
    )
    ctx = TurnContext(story_id="s1", turn=9)
    state = apply_delta(state, delta, ctx, source=DeltaSource.NARRATOR).state
    state.scene.present_ids = [*state.scene.present_ids, "new-sovereign"]

    found = path.hear(state, "“This is Void Refinement,” the stranger says.")

    assert [(t.rung, t.known, t.before) for t in found] == [
        (TOP + 1, False, ""),
        (TOP + 1, True, "new-sovereign"),
    ]
    (standing,) = path.known(state, state.player, realms(state))
    assert (standing.rung, standing.known, standing.known_from) == (TOP + 1, True, "new-sovereign")


def test_a_rung_nobody_named_to_them_is_not_yet_a_top_the_story_reached():
    # The update alone tells the character nothing: the scene's words do.
    state = at_the_top()
    delta = StateDelta(rungs=[NewRung(ladder_id="realms", name=VOID)])
    ctx = TurnContext(story_id="s1", turn=9)
    state = apply_delta(state, delta, ctx, source=DeltaSource.NARRATOR).state

    assert not path.top_told(state, realms(state))
    assert path.known(state, state.player, realms(state)) == []


def test_a_climb_stops_at_the_top_until_the_ladder_grows_and_then_goes_on():
    # G19: with a rung above, the player character's rank starts to fill toward it, each rung
    # taking twice the last.
    state = at_the_top()
    ladder = realms(state)
    assert growth.rank_of(state.player, ladder) is None
    assert growth.no_rung_above(ladder) == "Nothing anyone knows of lies above Soul Transformation."

    after = told(state).state

    rank = growth.rank_of(after.player, realms(after))
    assert rank is not None and rank.rung.name == VOID
    assert rank.need_s == growth.rung_need_s(TOP + 1) == 2 * growth.rung_need_s(TOP)
    assert rank.effort_s == 0


def breaks_through(state):
    """Lin Feng sets out to break through to whatever lies above his rung."""
    step = train(GrowthKind.BREAKTHROUGH, "the next realm", 12, ladder_id="realms", attempt=True)
    return play(state, Intent(steps=[step]))


def test_played_out_the_top_stops_a_breakthrough_and_a_rung_above_it_takes_the_work():
    state = at_the_top()

    stopped = breaks_through(state).resolution.steps[0]

    assert stopped.outcome_class is OutcomeClass.RULED_OUT
    assert stopped.reason == "Nothing anyone knows of lies above Soul Transformation."

    played = breaks_through(told(state).state)

    settled = played.resolution.steps[0]
    assert settled.outcome_class is OutcomeClass.CERTAIN
    assert "this is training toward Void Refinement" in settled.reason
    rank = growth.rank_of(played.state.player, realms(played.state))
    assert rank is not None and rank.effort_s > 0
    assert played.state.player.sheet.ladders[0].rung == TOP  # earned first, then thrown for


def against_the_ceiling(state):
    """The same climb as a model that reads the player's words may file it: against the open
    rule that nobody is known to have passed the top."""
    step = train(GrowthKind.BREAKTHROUGH, "the next realm", 12, ladder_id="realms", attempt=True)
    facts = step.facts.model_copy(update={"against_rule_ids": ["realm-ceiling"]})
    return play(state, Intent(steps=[step.model_copy(update={"facts": facts})]))


def test_the_open_rule_that_held_the_ladder_is_struck_once_a_rung_is_told():
    # G7: the discovery breaks the open rule, for everyone. Left standing, it would rule out
    # every climb to the new rung.
    state = at_the_top()
    ladder = realms(state)
    state.bible.rules += [
        WorldRule(
            id="vault",
            text="Only elders of Soul Transformation enter the vault.",
            fixed=False,
            topic=RuleTopic.LAW,
        ),
        WorldRule(
            id="core-toll",
            text="Core Formation costs a decade of life.",
            fixed=False,
            topic=RuleTopic.LIMITS,
        ),
    ]
    assert [rule.id for rule in path.ceilings(state, ladder)] == ["realm-ceiling"]
    stopped = against_the_ceiling(state).resolution.steps[0]
    assert stopped.outcome_class is OutcomeClass.RULED_OUT
    assert stopped.reason == "Nobody is known to have passed Soul Transformation."

    after = told(state).state

    kept = [rule.id for rule in after.bible.rules]
    assert "realm-ceiling" not in kept and {"vault", "core-toll", "qi-exists"} <= set(kept)
    assert all("realm-ceiling" not in kind.rule_ids for kind in after.bible.extraordinary)
    assert path.ceilings(after, realms(after)) == []
    # Filed against the rule that is gone, the climb is training toward the new rung.
    settled = against_the_ceiling(after).resolution.steps[0]
    assert settled.outcome_class is OutcomeClass.CERTAIN
    assert "this is training toward Void Refinement" in settled.reason


def test_a_rung_that_was_refused_strikes_no_rule():
    state = cultivation_world()  # Lin Feng on the lowest rung: the top is not his to pass yet

    refused = told(state)

    assert refused.rejected
    assert "realm-ceiling" in [rule.id for rule in refused.state.bible.rules]


def test_the_engine_too_holds_to_the_ladders_rules():
    state = cultivation_world()
    delta = StateDelta(rungs=[NewRung(ladder_id="realms", name=VOID, stands=["elder-mo"])])

    applied = apply_delta(
        state, delta, TurnContext(story_id="s1", turn=9), source=DeltaSource.ENGINE
    )

    assert len(realms(applied.state).rungs) == TOP + 1
    assert len(applied.rejected) == 1


def test_the_new_rung_reads_as_any_rung_from_then_on():
    # Heard of on the day the scene named it, like a rung the world started with.
    state = told(at_the_top()).state
    state.world_s += YEAR

    (standing,) = path.known(state, state.player, realms(state))
    assert (standing.rung, standing.known, standing.heard_s) == (TOP + 1, False, 400 * DAY)
    assert path.top_told(state, realms(state))
