"""W10, M1, M2: code starts and ends encounters, so a fight's protections and pictures work in play.

Every test runs the pipeline's own seams (resolve, play out, direct), many seeds where a roll is
involved, on the cultivation sample: Lin at the outer-court well with Senior Brother Zhao, a key
NPC a realm above him.
"""

import pytest

from engine import encounters, pipeline
from engine.apply import DeltaSource, apply_delta
from engine.base import HOUR, MINUTE
from engine.context import ImageSetting, StorySettings, TurnContext
from engine.contracts import (
    ActionKind,
    Aim,
    CharacterChange,
    ConditionChange,
    Intent,
    IntentStep,
    PictureTrigger,
    SceneEnd,
    StateDelta,
    StepFacts,
)
from engine.rng import SeededRng
from engine.samples import cultivation_world
from engine.state import (
    Character,
    CharacterSheet,
    CharacterStatus,
    Condition,
    Encounter,
    EncounterKind,
    PassingState,
    PowerAxes,
    PowerAxis,
    Prominence,
    WorldState,
)

SEEDS = range(200)


def ctx(turn: int = 3, **settings) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn, settings=StorySettings(**settings))


def rng(seed: int | str = 0, turn: int = 3) -> SeededRng:
    return SeededRng.for_turn(f"seed-{seed}", "main", turn)


def step(text: str, kind: ActionKind = ActionKind.EXCHANGE, duration_s: int = 5, **kw):
    return IntentStep(
        text=text,
        verb=kw.pop("verb", text.split()[0]),
        kind=kind,
        proposed_duration_s=duration_s,
        **kw,
    )


def attack(target: str = "zhao", aim: Aim = Aim.WOUND, **kw) -> IntentStep:
    return step(
        f"punch {target}",
        aim=aim,
        target_ids=[target],
        axis=PowerAxis.MIGHT,
        facts=kw.pop("facts", StepFacts(opposition_ids=[target], can_respond=True)),
        **kw,
    )


def strike(n: int = 0) -> IntentStep:
    """An exchange that names no one, as a scripted strike in a fight already on does."""
    return step(f"strike ({n})", duration_s=10, verb="strike")


def turn(state: WorldState, *steps: IntentStep, seed: int | str = 0, turn_no: int = 3, **settings):
    """One turn through the seams, as the graph runs them: resolve, play out, direct, record."""
    context = ctx(turn_no, **settings)
    turn_rng = rng(seed, turn_no)
    intent = Intent(steps=list(steps))
    resolution = pipeline.resolve(state, intent, context, turn_rng)
    played = pipeline.play_out(state, resolution, context, turn_rng)
    plan = pipeline.direct(played.state, played.resolution, context, turn_rng, intent=intent)
    after = pipeline.record_direction(played.state, plan, context)
    after.turn = turn_no
    return after, played, plan


def fight_on(state: WorldState, *opponents: str, started_turn: int = 2) -> WorldState:
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=list(opponents or ["zhao"]),
        started_turn=started_turn,
        started_s=state.world_s,
        key=True,
    )
    return state


def zhao_out(state: WorldState) -> bool:
    zhao = state.characters["zhao"]
    return not zhao.alive or not encounters.still_in_it(state, "zhao")


# --- Start --------------------------------------------------------------------------------------


@pytest.mark.parametrize("aim", [Aim.KILL, Aim.WOUND, Aim.SUBDUE])
def test_aiming_harm_at_someone_who_can_answer_starts_a_fight_whatever_the_roll(aim):
    for seed in SEEDS:
        state = cultivation_world()
        after, played, _ = turn(state, attack(aim=aim), seed=seed)
        fight = after.scene.encounter
        if zhao_out(after):
            # Killed, subdued or left dying by the first blow: the fight began and ended with it.
            assert fight is None, seed
            continue
        assert fight is not None, (seed, played.resolution.steps[0].reason)
        assert fight.kind is EncounterKind.FIGHT
        assert fight.opponent_ids == ["zhao"]
        assert fight.started_turn == 3 and fight.started_s == state.world_s
        assert fight.key  # Zhao is a key NPC (M1)


def test_a_swing_the_power_gap_rules_out_still_starts_the_fight():
    """A2, A8: the god notices the swing. Lin against the elder, two realms up, is ruled out, and
    the elder answers it."""
    state = cultivation_world()
    state.characters["elder-mo"].location_id = "well"
    state.scene.present_ids.append("elder-mo")
    after, played, _ = turn(state, attack("elder-mo", aim=Aim.KILL))
    assert played.resolution.steps[0].outcome_class.value == "ruled_out"
    assert after.scene.encounter.opponent_ids == ["elder-mo"]


def test_a_step_settled_before_it_was_tried_starts_nothing():
    """Reaching for a sword Lin doesn't carry meets nobody (R2, G14)."""
    from engine.contracts import SheetPart, SheetUse

    state = cultivation_world()
    swing = attack(aim=Aim.KILL, uses=[SheetUse(part=SheetPart.ITEM, ref="sword")])
    after, played, _ = turn(state, swing)
    assert played.resolution.steps[0].outcome_class.value == "ruled_out"
    assert after.scene.encounter is None


def test_a_step_at_nobody_or_a_harmless_one_starts_nothing():
    state = cultivation_world()
    for quiet in (
        strike(),
        step("draw water", ActionKind.TASK, 60),
        step("bow to Zhao", ActionKind.INSTANT, 2, target_ids=["zhao"]),
    ):
        after, _, _ = turn(state, quiet)
        assert after.scene.encounter is None, quiet.text


def test_a_proposed_negotiation_starts_only_with_someone_who_can_answer():
    talk = step(
        "haggle with Zhao over the rations",
        ActionKind.CONVERSATION,
        3 * MINUTE,
        axis=PowerAxis.INFLUENCE,
        target_ids=["zhao"],
        encounter=EncounterKind.NEGOTIATION,
        facts=StepFacts(opposition_ids=["zhao"], can_respond=True),
    )
    for seed in range(20):
        after, _, _ = turn(cultivation_world(), talk, seed=seed)
        assert after.scene.encounter.kind is EncounterKind.NEGOTIATION, seed
        assert after.scene.encounter.opponent_ids == ["zhao"]

    # Nobody in the way, or only someone asleep: the proposal stands for nothing.
    alone = talk.model_copy(update={"target_ids": [], "facts": StepFacts()})
    assert turn(cultivation_world(), alone)[0].scene.encounter is None
    state = cultivation_world()
    state.characters["zhao"].sheet.condition.states.append(PassingState(name="asleep"))
    assert turn(state, talk)[0].scene.encounter is None


def test_an_npcs_step_aimed_at_the_player_starts_a_fight_with_that_npc():
    state = cultivation_world()
    context = ctx()
    intent = Intent(actor_id="zhao", steps=[attack("lin", aim=Aim.WOUND)])
    resolution = pipeline.resolve(state, intent, context, rng())
    played = pipeline.play_out(state, resolution, context, rng())
    if played.state.player.alive and encounters.still_in_it(played.state, "zhao"):
        assert played.state.scene.encounter.opponent_ids == ["zhao"]


def test_a_fight_is_followed_only_when_the_step_played():
    """A step an event cut short didn't happen as resolved, so it starts nothing."""
    state = cultivation_world()
    resolution = pipeline.resolve(state, Intent(steps=[attack()]), ctx(), rng())
    cut = resolution.steps[0].model_copy(update={"interrupted": True})
    encounters.follow(state, cut, "lin", ctx())
    assert state.scene.encounter is None


# --- Carry on -----------------------------------------------------------------------------------


def test_thirty_exchanges_keep_a_fight_on_for_its_few_minutes():
    state = fight_on(cultivation_world())
    for n in range(30):
        state, _, plan = turn(state, strike(n), turn_no=3 + n)
        assert state.scene.encounter is not None, n
        assert plan.stall_pressure == 0 and plan.event is None
    assert state.world_s <= 10 * MINUTE


def test_a_new_foe_joins_the_fight_and_a_fight_stays_a_fight():
    state = fight_on(cultivation_world())
    state.characters["wei"] = Character(id="wei", name="Wei", location_id="well")
    state.scene.present_ids.append("wei")
    state, _, _ = turn(state, attack("wei", aim=Aim.WOUND))
    assert state.scene.encounter.opponent_ids[:2] == ["zhao", "wei"]
    flee = step(
        "run from Zhao",
        ActionKind.MOVE,
        20,
        verb="flee",
        encounter=EncounterKind.CHASE,
        facts=StepFacts(opposition_ids=["zhao"], can_respond=True),
    )
    state, _, _ = turn(state, flee, turn_no=4)
    if state.scene.encounter is not None:
        assert state.scene.encounter.kind is EncounterKind.FIGHT  # the chase is the same fight


def test_a_negotiation_that_turns_violent_becomes_a_fight_and_is_pictured_as_one():
    state = cultivation_world()
    state.director.pictured = ["portrait:lin", "cover", "place:well", "portrait:zhao"]
    state.scene.encounter = Encounter(
        kind=EncounterKind.NEGOTIATION, opponent_ids=["zhao"], started_turn=2, started_s=0
    )
    for seed in SEEDS:
        after, _, plan = turn(state, attack(aim=Aim.WOUND), seed=seed)
        if after.scene.encounter is None:
            continue
        assert after.scene.encounter.kind is EncounterKind.FIGHT
        assert plan.picture is not None
        assert plan.picture.trigger in (PictureTrigger.FIGHT_START, PictureTrigger.DECISIVE_BLOW)
        return
    raise AssertionError("no seed left the fight on")


# --- End ----------------------------------------------------------------------------------------


def test_the_fight_ends_when_its_only_foe_is_dead_or_subdued():
    from engine.resolve.power import SUBDUED_STATE

    knocked_out = CharacterChange(id="zhao", condition=ConditionChange(states=[SUBDUED_STATE]))
    killed = CharacterChange(id="zhao", status=CharacterStatus.DEAD, death_certainty="confirmed")
    for change, on in ((None, True), (knocked_out, False), (killed, False)):
        state = fight_on(cultivation_world())
        resolution = pipeline.resolve(state, Intent(steps=[strike()]), ctx(), rng())
        if change is not None:
            # The blow's own effect, as resolve records it for a blow that lands (F4).
            effects = StateDelta(characters=[change])
            steps = [resolution.steps[0].model_copy(update={"effects": effects})]
            resolution = resolution.model_copy(update={"steps": steps})
        played = pipeline.play_out(state, resolution, ctx(), rng())
        assert (played.state.scene.encounter is not None) is on, change


def test_a_certain_blow_on_someone_who_cant_answer_begins_and_ends_the_fight_at_once():
    state = cultivation_world()
    state.characters["wei"] = Character(
        id="wei",
        name="Wei",
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=2), condition=Condition(states=[PassingState(name="asleep")])
        ),
    )
    after, played, _ = turn(state, attack("wei", aim=Aim.KILL))
    assert played.resolution.steps[0].outcome_class.value == "certain"
    assert not after.characters["wei"].alive
    assert after.scene.encounter is None


def test_the_fight_ends_when_the_foe_is_somewhere_the_player_is_not():
    state = fight_on(cultivation_world())
    state.characters["zhao"].location_id = "inner-court"
    state.scene.present_ids = ["lin"]
    after, _, _ = turn(state, strike())
    assert after.scene.encounter is None

    # In the scene, or somewhere inside the player character's place, the foe is still there.
    state = fight_on(cultivation_world())
    state.characters["zhao"].location_id = "azure-peak"
    assert turn(state, strike())[0].scene.encounter is not None
    state.characters["zhao"].location_id = "inner-court"
    state.scene.present_ids = ["lin", "zhao"]
    assert turn(state, strike())[0].scene.encounter is not None


def test_the_fight_ends_when_the_player_character_falls():
    state = fight_on(cultivation_world())
    state.characters["lin"].sheet.condition.states.append(PassingState(name="unconscious"))
    assert turn(state, step("lie still", ActionKind.INSTANT, 1))[0].scene.encounter is None


def test_ten_minutes_with_no_exchange_end_it_and_nothing_is_timed_in_turns():
    state = fight_on(cultivation_world())
    chat = step("tell Wei a story", ActionKind.CONVERSATION, 4 * MINUTE, verb="tell")
    state, _, _ = turn(state, chat)
    state, _, _ = turn(state, chat, turn_no=4)
    assert state.scene.encounter is not None  # eight minutes of talk with nobody in the way
    state, _, _ = turn(state, chat, turn_no=5)
    assert state.scene.encounter is None
    assert state.world_s >= encounters.LAPSE_S


def test_a_step_that_faces_the_foe_keeps_it_on_however_long_the_talk():
    state = fight_on(cultivation_world())
    parley = step(
        "talk Zhao down",
        ActionKind.CONVERSATION,
        6 * MINUTE,
        axis=PowerAxis.INFLUENCE,
        target_ids=["zhao"],
        facts=StepFacts(opposition_ids=["zhao"], can_respond=True),
    )
    for n in range(4):
        state, _, _ = turn(state, parley, seed=n, turn_no=3 + n)
        assert state.scene.encounter is not None, n


def test_a_long_stretch_ends_the_encounter_before_it_plays_so_the_montage_rolls():
    """E7: a fight can't be slept through, and a year of training gets its events."""
    state = fight_on(cultivation_world())
    sleep = step("sleep", ActionKind.REST, 8 * HOUR, verb="sleep")
    after, _, _ = turn(state, sleep)
    assert after.scene.encounter is None

    state = fight_on(cultivation_world())
    skip = step("train here for a year", ActionKind.TIME_SKIP, 365 * 24 * HOUR, verb="train")
    after, played, _ = turn(state, skip)
    assert after.scene.encounter is None
    rolled = [e for e in after.pending_events.values() if e.kind.startswith("director.")]
    fired = [e for e in played.fired if e.kind.startswith("director.")]
    assert rolled or fired  # the stretch rolled its W16 events


# --- Pictures (M1, M2) --------------------------------------------------------------------------


def met_zhao(state: WorldState) -> WorldState:
    state.director.pictured = ["portrait:lin", "cover", "place:well", "portrait:zhao"]
    return state


def test_a_key_fight_gets_its_start_and_its_decisive_blow_in_play_even_with_the_budget_spent():
    decided_at_once = 0
    for seed in range(60):
        state = met_zhao(cultivation_world())
        state.director.picture_credit = 0
        pictures = []
        for n in range(12):
            blow = attack(aim=Aim.WOUND) if n == 0 else strike(n)
            if n == 11:
                # The last blow lands on a Zhao left senseless: it kills him or leaves him badly
                # wounded, never less (A2), and either decides the fight.
                state.characters["zhao"].sheet.condition.states.append(PassingState(name="stunned"))
                blow = attack(aim=Aim.KILL)
            state, _, plan = turn(state, blow, seed=f"{seed}/{n}", turn_no=3 + n)
            if plan.picture is not None:
                pictures.append(plan.picture.trigger)
            if n < 11 and state.scene.encounter is None:
                break  # the first blow already decided it
        if pictures == [PictureTrigger.DECISIVE_BLOW]:
            decided_at_once += 1  # one picture a scene, and the blow outranks the start (M1)
            continue
        assert pictures == [PictureTrigger.FIGHT_START, PictureTrigger.DECISIVE_BLOW], (
            seed,
            pictures,
        )
        assert state.scene.encounter is None and state.director.fight is None
        assert state.director.picture_credit >= -2.0  # borrowed, never past the floor (M2)
    assert decided_at_once < 30


def test_a_key_fight_decided_by_its_first_blow_still_gets_that_blow_pictured():
    """The fight begins and ends within one turn's steps, so the encounter is already over when
    the director looks: the felled foe still gets the decisive blow, and the fight no start."""
    for seed in range(40):
        state = cultivation_world()
        state.director.pictured = ["portrait:lin", "cover", "place:well"]
        might = state.player.sheet.axes.might + encounters.STRONG_FOE_TIERS
        state.characters["beast"] = Character(
            id="beast",
            name="the cave bear",
            prominence=Prominence.MINOR,
            location_id="well",
            sheet=CharacterSheet(
                axes=PowerAxes(might=might),
                condition=Condition(states=[PassingState(name="asleep")]),
            ),
        )
        state.scene.present_ids.append("beast")
        after, played, plan = turn(state, attack("beast", aim=Aim.KILL), seed=seed)
        assert played.resolution.steps[0].encounter is EncounterKind.FIGHT
        assert after.scene.encounter is None and after.director.fight is None
        assert plan.picture is not None, (seed, played.resolution.steps[0].reason)
        assert plan.picture.trigger is PictureTrigger.DECISIVE_BLOW
        assert plan.picture.subject_id == "beast"


def test_a_swing_that_fails_or_only_wounds_is_never_the_decisive_blow():
    """Before, any deed of severity 3 on a foe counted, and a failed attempt to kill is one."""
    blows = 0
    for seed in SEEDS:
        state = met_zhao(cultivation_world())
        state.director.picture_credit = 2.0
        for n, aim in enumerate((Aim.WOUND, Aim.KILL, Aim.KILL)):
            before = state.characters["zhao"].sheet.condition.health
            state, played, plan = turn(state, attack(aim=aim), seed=f"{seed}/{n}", turn_no=3 + n)
            zhao = state.characters["zhao"]
            decided = not zhao.alive or zhao.sheet.condition.health.value in (
                "badly_wounded",
                "dying",
            )
            decisive = plan.picture is not None and plan.picture.trigger in (
                PictureTrigger.DECISIVE_BLOW,
                PictureTrigger.DEATH,
            )
            if decisive:
                blows += 1
                assert decided and (not zhao.alive or zhao.sheet.condition.health != before)
            if played.resolution.steps[0].result.value == "failure":
                assert not decisive, seed
            if state.scene.encounter is None:
                break
    assert blows  # some fights were decided, and each picture was of a blow that decided one


def test_an_ordinary_scuffle_is_a_fight_but_gets_no_pictures():
    state = cultivation_world()
    state.director.pictured = ["portrait:lin", "cover", "place:well"]
    state.characters["wei"] = Character(
        id="wei",
        name="Wei",
        prominence=Prominence.MINOR,
        location_id="well",
        sheet=CharacterSheet(axes=PowerAxes(might=2), condition=Condition()),
    )
    state.scene.present_ids = ["lin", "wei"]
    for seed in range(40):
        after, _, plan = turn(state, attack("wei", aim=Aim.WOUND), seed=seed)
        if after.scene.encounter is not None:
            assert not after.scene.encounter.key
        assert plan.picture is None or plan.picture.trigger not in (
            PictureTrigger.FIGHT_START,
            PictureTrigger.DECISIVE_BLOW,
        )


# --- Where the player is (R3, C2) ---------------------------------------------------------------


def test_the_scene_ending_somewhere_moves_the_player_and_those_with_them():
    state = cultivation_world()
    state.characters["mei"] = Character(id="mei", name="Mei", location_id="well")
    state.characters["ghost"] = Character(
        id="ghost",
        name="the old ghost",
        location_id="well",
        status=CharacterStatus.DEAD,
        death_certainty="confirmed",
    )
    end = SceneEnd(
        ended_on="They reach the halls.", place_id="inner-court", present_ids=["mei", "ghost"]
    )
    after = apply_delta(state, StateDelta(scene_end=end), ctx(), source=DeltaSource.NARRATOR).state
    assert after.scene.place_id == "inner-court"
    assert after.player.location_id == "inner-court"
    assert after.characters["mei"].location_id == "inner-court"
    assert after.characters["zhao"].location_id == "well"  # left behind
    assert after.characters["ghost"].location_id == "well"

    from engine.director.sources import here

    assert here(after) == "inner-court"  # the director places events where the player is


def test_the_scene_ending_in_a_wider_place_keeps_the_exact_spot_and_an_unknown_place_moves_no_one():
    state = cultivation_world()
    wide = SceneEnd(ended_on="Still at the well.", place_id="azure-peak", present_ids=["zhao"])
    after = apply_delta(state, StateDelta(scene_end=wide), ctx(), source=DeltaSource.NARRATOR).state
    assert after.player.location_id == "well" and after.characters["zhao"].location_id == "well"
    nowhere = SceneEnd(ended_on="Somewhere.", place_id="atlantis", present_ids=["zhao"])
    after = apply_delta(state, StateDelta(scene_end=nowhere), ctx(), source=DeltaSource.NARRATOR)
    assert after.state.player.location_id == "well"


def test_naming_someone_far_off_or_missing_as_present_moves_no_one_but_the_player():
    """Only the engine's own record moves people: the narrator writing the elder into the scene
    at the inner court doesn't fetch him, and a missing man stays lost."""
    state = cultivation_world()
    state.characters["shen"] = Character(
        id="shen", name="Shen", location_id="well", status=CharacterStatus.MISSING
    )
    end = SceneEnd(
        ended_on="By the well.", place_id="azure-peak", present_ids=["zhao", "elder-mo", "shen"]
    )
    after = apply_delta(state, StateDelta(scene_end=end), ctx(), source=DeltaSource.NARRATOR).state
    assert after.characters["elder-mo"].location_id == "inner-court"
    end = SceneEnd(ended_on="Gone.", place_id="inner-court", present_ids=["zhao", "shen"])
    after = apply_delta(state, StateDelta(scene_end=end), ctx(), source=DeltaSource.NARRATOR).state
    assert after.player.location_id == after.characters["zhao"].location_id == "inner-court"
    assert after.characters["shen"].location_id == "well"


@pytest.mark.parametrize("helpless", ["subdued", "knocked out", "stunned"])
def test_engine_changes_that_leave_someone_helpless_count_as_subdued(helpless):
    from engine.director.turn import read_turn

    state = cultivation_world()
    resolution = pipeline.resolve(state, Intent(steps=[strike()]), ctx(), rng())
    knocked = StateDelta(
        characters=[CharacterChange(id="zhao", condition=ConditionChange(states=[helpless]))]
    )
    steps = [resolution.steps[0].model_copy(update={"effects": knocked})]
    facts = read_turn(state, resolution.model_copy(update={"steps": steps}), ctx(), None)
    assert facts.subdued == frozenset({"zhao"})
    winded = StateDelta(
        characters=[CharacterChange(id="zhao", condition=ConditionChange(states=["winded"]))]
    )
    steps = [resolution.steps[0].model_copy(update={"effects": winded})]
    facts = read_turn(state, resolution.model_copy(update={"steps": steps}), ctx(), None)
    assert not facts.subdued


def test_images_off_still_follow_the_fight():
    state = met_zhao(cultivation_world())
    for seed in range(20):
        after, _, plan = turn(state, attack(aim=Aim.WOUND), seed=seed, images=ImageSetting.OFF)
        assert plan.picture is None
        if after.scene.encounter is not None:
            assert after.director.fight is not None
