import pytest

from engine.contracts import (
    ActionKind,
    AttitudeShift,
    Beat,
    BeatUse,
    ChainLink,
    CharacterChange,
    DirectorPlan,
    EventKind,
    EventSource,
    Intent,
    IntentStep,
    ItemChange,
    LinkResolution,
    MeansVerdict,
    NewFact,
    OutcomeClass,
    PictureDecision,
    PictureKind,
    PictureTrigger,
    PlaceChange,
    PlannedEvent,
    Plausibility,
    PowerTheory,
    ProposedDeed,
    Resolution,
    SceneEnd,
    SheetPart,
    SheetUse,
    StandingAction,
    StateDelta,
    StepFacts,
    StepResolution,
    StopReason,
    TalentCase,
    UseSource,
)
from engine.state import (
    Attributes,
    CauseMechanism,
    CharacterStatus,
    DeathCertainty,
    EventSize,
    Judged,
    PowerAxis,
    RollRecord,
    StepResult,
    TalentFit,
    Trace,
    TraceKind,
    Visibility,
)


def time_stop_intent() -> Intent:
    """'When Senior Brother Zhao kicks my water bucket over again, I stop time and break his
    arm.' (G3)"""
    return Intent(
        summary="Lin stops time and breaks Zhao's arm.",
        steps=[
            IntentStep(
                text="Stop time",
                verb="stop time",
                kind=ActionKind.INSTANT,
                uses=[SheetUse(part=SheetPart.POWER, ref="time-stop")],
                proposed_duration_s=0,
                proposed_personal_s=1,
            ),
            IntentStep(
                text="Walk between the hanging droplets and break Zhao's arm",
                verb="break",
                target_ids=["zhao"],
                axis=PowerAxis.MIGHT,
                uses=[SheetUse(part=SheetPart.ATTRIBUTE, ref="strength")],
                beats=[
                    Beat(
                        text="step between the droplets",
                        uses=[BeatUse(source=UseSource.BODY, thing="legs")],
                    ),
                    Beat(
                        text="grab a fallen branch",
                        uses=[
                            BeatUse(
                                source=UseSource.NEW,
                                thing="a fallen branch",
                                plausibility=Plausibility.PLAUSIBLE,
                            )
                        ],
                    ),
                ],
                facts=StepFacts(
                    opposition_ids=["zhao"],
                    can_respond=False,
                    why_not="frozen in stopped time",
                    means=MeansVerdict.CLEARLY_ENOUGH,
                ),
                lines=["Kick it again, senior brother."],
                kind=ActionKind.EXCHANGE,
                proposed_duration_s=2,
                proposed_personal_s=2,
            ),
        ],
        theories=[
            PowerTheory(
                power_id="time-stop", topic="hit_mode", claim="It should hit like lightning."
            )
        ],
        backstory=["I was a pharmacist in my past life."],
        goals=["Win the ranking tournament."],
        outcome_claims=["and everyone cheers"],
    )


def resolution() -> Resolution:
    return Resolution(
        steps=[
            StepResolution(
                index=0,
                text="Stop time",
                outcome_class=OutcomeClass.CERTAIN,
                reason="Lin has time stop.",
                result=StepResult.SUCCESS,
                duration_s=0,
                personal_s=1,
            ),
            StepResolution(
                index=1,
                text="Break Zhao's arm",
                outcome_class=OutcomeClass.CERTAIN,
                reason="Zhao is frozen and can't defend.",
                result=StepResult.SUCCESS,
                duration_s=0,
                personal_s=2,
                chain=[
                    LinkResolution(
                        text="A frozen arm can't brace",
                        outcome_class=OutcomeClass.CERTAIN,
                        reason="Nothing moves in stopped time.",
                        holds=True,
                    )
                ],
                effects=StateDelta(
                    characters=[
                        CharacterChange(
                            id="zhao",
                            attitudes=[AttitudeShift(fear=30, grudge="his arm")],
                        )
                    ]
                ),
                deeds=[
                    ProposedDeed(
                        kind="maim",
                        text="Broke Zhao's arm in stopped time.",
                        victim_ids=["zhao"],
                        severity=2,
                        visibility=Visibility.SECRET,
                        traces=[Trace(kind=TraceKind.WOUND, text="An arm snapped by no one.")],
                        in_stopped_time=True,
                    )
                ],
            ),
        ],
        canon=["a fallen branch by the well"],
        stakes=True,
    )


def test_a_cause_and_effect_chain_round_trips():
    intent = Intent(
        steps=[
            IntentStep(
                text="Set the hall on fire",
                verb="burn",
                kind=ActionKind.TASK,
                proposed_duration_s=600,
                chain=[
                    ChainLink(text="The field keeps out air", rests_on=["field-air"]),
                    ChainLink(text="The air inside runs out", takes_s=300),
                ],
            )
        ]
    )

    assert Intent.model_validate_json(intent.model_dump_json()) == intent


@pytest.mark.parametrize(
    "contract",
    [
        time_stop_intent(),
        resolution(),
        DirectorPlan(
            event=PlannedEvent(
                size=EventSize.LOCAL,
                kind=EventKind.ARRIVAL,
                source=EventSource.DUE,
                title="An inner-court elder",
                brief="Elder Mo felt the ripple of stopped time and comes to look.",
            ),
            callbacks=["tournament"],
            picture=PictureDecision(
                kind=PictureKind.SCENE, trigger=PictureTrigger.DECISIVE_BLOW, subject_id="zhao"
            ),
        ),
        StateDelta(
            characters=[CharacterChange(id="gennaro-cousin", name="Tonino", meets_player=True)],
            facts=[NewFact(text="The bartender saw Luca's face.", known_to_player=False)],
            items=[ItemChange(name="bullet", quantity=2, from_id="luca", to_id="world")],
            scene_end=SceneEnd(ended_on="Headlights turn the corner behind him."),
            summary="Luca shot Carmine and ran.",
        ),
    ],
    ids=lambda c: type(c).__name__,
)
def test_contracts_round_trip_through_json(contract):
    assert type(contract).model_validate_json(contract.model_dump_json()) == contract


def test_resolution_totals_world_and_lived_time():
    settled = resolution()

    assert settled.duration_s == 0
    assert settled.personal_s == 3
    assert settled.steps[1].clean_success


def test_a_stopped_plan_lists_what_never_happened():
    settled = Resolution(
        steps=[
            StepResolution(
                index=0,
                text="Throw the stone",
                outcome_class=OutcomeClass.CONTESTED,
                reason="The troll is moving.",
                roll=RollRecord(seed="s", odds=0.6, value=0.8, result=StepResult.FAILURE),
                result=StepResult.FAILURE,
                duration_s=2,
            )
        ],
        stopped_at_step=0,
        stop_reason=StopReason.FAILED,
        unplayed=["Run for the tunnel"],
    )

    assert not settled.steps[0].clean_success
    assert Resolution.model_validate_json(settled.model_dump_json()) == settled


def test_engine_only_fields_exist_for_c1_reversals():
    change = CharacterChange(
        id="kaede",
        status=CharacterStatus.ALIVE,
        cause={"mechanism": "survived", "ref_kind": "event", "ref_id": "found-alive"},
    )
    killed = CharacterChange(
        id="guard", status=CharacterStatus.DEAD, death_certainty=DeathCertainty.CONFIRMED
    )

    assert change.cause.mechanism is CauseMechanism.SURVIVED
    assert killed.cause is None
    assert StateDelta().empty
    assert not StateDelta(summary="x").empty


def _walk(schema, path="$"):
    yield path, schema
    if isinstance(schema, dict):
        for key, value in schema.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(schema, list):
        for i, value in enumerate(schema):
            yield from _walk(value, f"{path}[{i}]")


@pytest.mark.parametrize("model", [Intent, StateDelta], ids=lambda m: m.__name__)
def test_model_output_schemas_avoid_free_form_maps_and_unions(model):
    # The interpret and narrate models return these through structured output (B5), which
    # handles neither free-form maps nor unions of several types well.
    schema = model.model_json_schema()

    for path, node in _walk(schema):
        if not isinstance(node, dict):
            continue
        assert node.get("additionalProperties") in (None, False), f"free-form map at {path}"
        branches = [b for b in node.get("anyOf", []) if b.get("type") != "null"]
        assert len(branches) <= 1, f"union at {path}"


def test_what_only_the_engine_writes_is_left_out_of_the_form_the_narrator_fills():
    # F1, A3: a stranger's body and the level a place keeps for a thing are the engine's own, so
    # the narrate model is never offered them, and the engine can still write both.
    schema = StateDelta.model_json_schema()
    assert "attributes" not in schema["$defs"]["CharacterChange"]["properties"]
    assert "judged" not in schema["$defs"]["PlaceChange"]["properties"]
    assert not {"Attributes", "Judged"} & set(schema["$defs"])
    assert CharacterChange(id="x", attributes=Attributes(strength=5)).attributes.strength == 5
    kept = PlaceChange(id="well", judged=[Judged(key="lock pick", level=3)])
    assert PlaceChange.model_validate(kept.model_dump()).judged == kept.judged


def test_the_interpret_model_must_always_answer_with_steps():
    # B5, W10: Gemini leaves out what a schema doesn't require, and an intent with no steps
    # played every action as a five-second nothing. Code may still leave them out.
    assert {"summary", "steps"} <= set(Intent.model_json_schema()["required"])
    assert Intent(standing=StandingAction.WAIT).steps == []


def test_the_interpret_model_must_always_judge_each_steps_challenge():
    # A2, A3: a step with no judged challenge fell back to even odds whoever the character was.
    schema = Intent.model_json_schema()
    assert {"facts", "uses"} <= set(schema["$defs"]["IntentStep"]["required"])
    assert "challenge" in schema["$defs"]["StepFacts"]["required"]
    assert StepFacts().challenge is None  # code may still leave it out


def test_the_interpret_model_must_always_say_whether_a_fight_is_a_bout():
    # W1: left to the model, the terms came on some blows of a lesson and not on others. Code
    # keeps a bout once it has begun, but its first blow has only the model's word to go by.
    assert "terms" in Intent.model_json_schema()["$defs"]["StepFacts"]["required"]
    assert StepFacts().terms is None  # null is an answer: any other fight, or no fight


def test_the_interpret_model_must_always_say_whether_a_crowd_is_around():
    # W2: left out, a killing in a full square would have nobody the scene doesn't name to
    # see it, and so no witness.
    assert "crowd" in Intent.model_json_schema()["$defs"]["StepFacts"]["required"]
    assert StepFacts().crowd is False  # code may still leave it out


def test_the_interpret_model_must_always_judge_whether_a_thing_is_there():
    # R2: a use with no judgement is one code can only guess at, and the guess used to be a roll
    # that failed natural things. The model always answers; code may leave it out, and then the
    # thing is there (`engine.resolve.checks`).
    use = Intent.model_json_schema()["$defs"]["BeatUse"]
    assert {"source", "thing", "plausibility"} <= set(use["required"])
    assert "ref" not in use["required"]
    assert BeatUse(source=UseSource.NEW, thing="a branch").plausibility is None


def test_talent_rulings_and_bridges_are_left_out_of_the_form_the_narrator_fills():
    # A4: which talent covers what is the engine's to record, from what the interpret step
    # proposes on a step, so the narrate model is never offered either.
    schema = StateDelta.model_json_schema()
    offered = set(schema["$defs"]["CharacterChange"]["properties"])
    assert not {"talent_rulings", "bridges"} & offered
    assert not {"TalentRuling", "TalentBridge", "TalentCover"} & set(schema["$defs"])


def test_the_interpret_model_must_always_answer_on_talent_for_each_step():
    # A4: Gemini leaves out what a schema doesn't require, and in the first live run with
    # talents (2026-11-10) it never made a case, so no talent was ruled on and every one of
    # them did nothing. Each step now says how the talents stand, an empty list when there is
    # nothing to rule on, and the bridge it builds, null on any other step.
    schema = Intent.model_json_schema()
    step = schema["$defs"]["IntentStep"]
    assert {"talent_cases", "bridge"} <= set(step["required"])
    assert {"type": "null"} in step["properties"]["bridge"]["anyOf"]
    # A case names the thing and gives the reason the player reads in the ruling.
    assert set(schema["$defs"]["TalentCase"]["required"]) == {"what", "reason", "talent_id", "fit"}
    # Code may still leave them out.
    plain = IntentStep(text="wait", verb="wait", kind=ActionKind.TASK, proposed_duration_s=5)
    assert plain.talent_cases == [] and plain.bridge is None
    assert TalentCase(talent_id="sword", fit=TalentFit.INSIDE).what == ""


def test_an_empty_bridge_is_no_bridge():
    # A4: a form that must always answer can answer with an empty bridge where it means none.
    # Left as one, an ordinary step would be refused for building on a talent nobody has.
    def step(bridge):
        return IntentStep.model_validate(
            {
                "text": "cut the rope",
                "verb": "cut",
                "kind": "exchange",
                "proposed_duration_s": 2,
                "bridge": bridge,
            }
        )

    assert step({"talent_id": "", "what": " ", "rests_on": ""}).bridge is None
    assert step(None).bridge is None
    real = step({"talent_id": "architect", "what": "Aura wall", "rests_on": "the load formula"})
    assert real.bridge is not None and real.bridge.what == "Aura wall"
    # One that reaches something still stands, and code rules on it.
    assert step({"talent_id": "", "what": "Aura wall", "rests_on": ""}).bridge is not None
