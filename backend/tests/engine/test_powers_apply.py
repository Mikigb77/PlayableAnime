"""apply_delta for the state of powers (WS9b): settled details never change (A9), growth and
ladders are the engine's (A4, G19, G20), and time effects take hold on their user's clock
(W10a)."""

from engine.apply import DeltaSource, apply_delta
from engine.context import TurnContext
from engine.contracts import CharacterChange, PowerChange, PowerSetting, StateDelta
from engine.samples import cultivation_world
from engine.state import (
    ActiveTimeEffect,
    CharacterStatus,
    HitMode,
    LadderPosition,
    Mastery,
    Practice,
    Skill,
    SkillLevel,
    Technique,
    TimeEffect,
    WorldState,
)
from engine.timekeeping import in_time_stop, world_stopped

ENGINE = DeltaSource.ENGINE
NARRATOR = DeltaSource.NARRATOR


def apply(state: WorldState, source: DeltaSource = ENGINE, **delta):
    return apply_delta(
        state, StateDelta(**delta), TurnContext(story_id="s1", turn=3), source=source
    )


def lin(**change) -> CharacterChange:
    return CharacterChange(id="lin", **change)


def unsettled() -> WorldState:
    state = cultivation_world()
    state.characters["lin"].sheet.power("time-stop").time.hit_mode = None
    return state


def test_a_hit_mode_is_settled_once_and_never_changed():
    state = unsettled()
    first = apply(
        state, characters=[lin(powers=[PowerChange(id="time-stop", hit_mode=HitMode.NORMAL_FORCE)])]
    )
    assert not first.rejected
    assert (
        first.state.characters["lin"].sheet.power("time-stop").time.hit_mode is HitMode.NORMAL_FORCE
    )

    second = apply(
        first.state,
        characters=[lin(powers=[PowerChange(id="time-stop", hit_mode=HitMode.RELATIVE_SPEED)])],
    )
    assert [r.reason for r in second.rejected] == ["settled for good (A9)"]
    power = second.state.characters["lin"].sheet.power("time-stop")
    assert power.time.hit_mode is HitMode.NORMAL_FORCE


def test_a_setting_is_kept_and_a_different_value_refused():
    state = cultivation_world()
    setting = PowerSetting(key="throws", value="relative_speed")
    first = apply(state, characters=[lin(powers=[PowerChange(id="time-stop", settings=[setting])])])
    other = PowerSetting(key="throws", value="normal_force")
    second = apply(
        first.state, characters=[lin(powers=[PowerChange(id="time-stop", settings=[other])])]
    )

    assert second.state.characters["lin"].sheet.power("time-stop").settings == {
        "throws": "relative_speed"
    }
    assert len(second.rejected) == 1


def test_the_narrator_cant_touch_powers_growth_ladders_or_time():
    state = cultivation_world()
    applied = apply(
        state,
        NARRATOR,
        characters=[
            lin(
                powers=[PowerChange(id="time-stop", ready_at_personal_s=0)],
                techniques=[Technique(id="t", name="Falling Star")],
                ladders=[LadderPosition(ladder_id="realms", rung=4)],
                practice=[Practice(key="skill:sword", what="sword", effort_s=10)],
                skills=[Skill(name="sword", level=SkillLevel.MASTER)],
            )
        ],
        time_effects=[
            ActiveTimeEffect(
                character_id="lin",
                power_id="time-stop",
                effect=TimeEffect.STOP,
                started_personal_s=0,
                ends_personal_s=100,
            )
        ],
    )
    assert len(applied.rejected) == 6
    sheet = applied.state.characters["lin"].sheet
    assert sheet.techniques == [] and sheet.ladders[0].rung == 0 and sheet.skill("sword") is None
    assert applied.state.time_effects == []


def test_the_engine_records_growth():
    state = cultivation_world()
    applied = apply(
        state,
        characters=[
            lin(
                techniques=[Technique(id="t", name="Falling Star", power_id="time-stop")],
                ladders=[LadderPosition(ladder_id="realms", rung=1)],
                practice=[Practice(key="skill:sword", what="sword", effort_s=10)],
                skills=[Skill(name="herb lore", level=SkillLevel.SKILLED)],
            )
        ],
    )
    assert not applied.rejected
    sheet = applied.state.characters["lin"].sheet
    assert sheet.technique("t").power_id == "time-stop"
    assert sheet.ladders == [LadderPosition(ladder_id="realms", rung=1)]
    assert sheet.practiced("skill:sword").effort_s == 10
    assert [s.level for s in sheet.skills] == [SkillLevel.SKILLED]


def test_a_technique_they_have_keeps_what_it_is_and_only_its_mastery_moves():
    """A4. Use and practice change how well they have a technique, never what it is."""
    state = cultivation_world()
    star = Technique(id="t", name="Falling Star", effect="A thrown star.", learned_from="zhao")
    state.characters["lin"].sheet.techniques.append(star)
    grown = Technique(id="t", name="Some other name", mastery=Mastery.SKILLED, uses=4)

    applied = apply(state, characters=[lin(techniques=[grown])])

    assert not applied.rejected
    (kept,) = applied.state.characters["lin"].sheet.techniques
    assert (kept.name, kept.effect, kept.learned_from) == ("Falling Star", "A thrown star.", "zhao")
    assert (kept.mastery, kept.uses) == (Mastery.SKILLED, 4)


def test_the_narrator_cant_raise_a_techniques_mastery():
    state = cultivation_world()
    state.characters["lin"].sheet.techniques.append(Technique(id="t", name="Falling Star"))
    told = Technique(id="t", name="Falling Star", mastery=Mastery.OWN, uses=9)

    applied = apply(state, NARRATOR, characters=[lin(techniques=[told])])

    assert len(applied.rejected) == 1
    (kept,) = applied.state.characters["lin"].sheet.techniques
    assert (kept.mastery, kept.uses) == (Mastery.PRACTICED, 0)


def test_strength_can_be_hidden_but_never_shown_above_the_truth():
    state = cultivation_world()
    bad = apply(
        state, characters=[lin(ladders=[LadderPosition(ladder_id="realms", rung=0, shown_rung=2)])]
    )
    assert [r.reason for r in bad.rejected] == ["can't show more than they have"]
    unknown = apply(state, characters=[lin(ladders=[LadderPosition(ladder_id="realms", rung=9)])])
    assert [r.reason for r in unknown.rejected] == ["no such rung"]


def test_a_stop_holds_the_world_until_its_user_has_lived_it_out_or_dies():
    state = cultivation_world()
    stop = ActiveTimeEffect(
        character_id="lin",
        power_id="time-stop",
        effect=TimeEffect.STOP,
        started_personal_s=0,
        ends_personal_s=60,
    )
    held = apply(state, time_effects=[stop]).state
    assert in_time_stop(held, "lin") and world_stopped(held)

    held.characters["lin"].status = CharacterStatus.DEAD
    assert not world_stopped(held)
    ran_out = stop.model_copy(update={"ends_personal_s": 0})
    assert apply(state, time_effects=[ran_out]).state.time_effects == []
