import json

import pytest
from pydantic import ValidationError

from engine.base import MAIN_TIMELINE
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Attitude,
    Character,
    CharacterStatus,
    Clock,
    DeathCertainty,
    Deed,
    EventStatus,
    Extraordinary,
    Faction,
    PendingEvent,
    PowerAxis,
    Prevalence,
    Ruling,
    Rumor,
    SkillLevel,
    WorldBible,
    WorldState,
)

SAMPLES = [grounded_world, cultivation_world]


def minimal_state(**kwargs) -> WorldState:
    return WorldState(player_id="p", characters={"p": Character(id="p", name="Player")}, **kwargs)


@pytest.mark.parametrize("make", SAMPLES, ids=lambda f: f.__name__)
def test_samples_round_trip_through_json(make):
    state = make()

    assert WorldState.model_validate_json(state.model_dump_json()) == state


@pytest.mark.parametrize("make", SAMPLES, ids=lambda f: f.__name__)
def test_samples_round_trip_through_jsonb_style_dicts(make):
    # Django's JSONField stores json.dumps(model_dump(mode="json")) and loads it back as dicts.
    state = make()

    stored = json.loads(json.dumps(state.model_dump(mode="json")))

    assert WorldState.model_validate(stored) == state


def test_loading_ignores_unknown_keys_and_fills_new_defaults():
    stored = minimal_state().model_dump(mode="json")
    stored["field_from_a_newer_engine"] = {"anything": 1}
    del stored["director"]

    state = WorldState.model_validate(stored)

    assert state.director.turns_without_stakes == 0
    assert state.timeline_id == MAIN_TIMELINE


def test_collection_keys_must_match_record_ids():
    with pytest.raises(ValidationError, match="holds a record with id"):
        WorldState(
            player_id="p",
            characters={"p": Character(id="p", name="Player"), "x": Character(id="y", name="Y")},
        )


def test_the_player_character_must_exist():
    with pytest.raises(ValidationError, match="not in characters"):
        WorldState(player_id="ghost", characters={"p": Character(id="p", name="Player")})


@pytest.mark.parametrize("name", ["", "   "])
def test_a_character_needs_a_name(name):
    with pytest.raises(ValidationError):
        Character(id="x", name=name)


def test_a_death_needs_a_certainty_and_only_a_death_has_one():
    with pytest.raises(ValidationError, match="death certainty"):
        Character(id="x", name="X", status=CharacterStatus.DEAD)
    with pytest.raises(ValidationError, match="death certainty"):
        Character(id="x", name="X", death_certainty=DeathCertainty.PRESUMED)

    dead = Character(
        id="x", name="X", status=CharacterStatus.DEAD, death_certainty=DeathCertainty.CONFIRMED
    )

    assert not dead.alive


@pytest.mark.parametrize(
    ("make", "field", "value"),
    [
        (lambda v: Attitude(affinity=v), "affinity", 101),
        (lambda v: Attitude(fear=v), "fear", -1),
        (lambda v: Attitude(trust=v), "trust", -101),
        (lambda v: Faction(id="f", name="F", threat=v), "threat", 6),
        (
            lambda v: Deed(
                id="d", actor_id="p", kind="kill", text="", turn=1, world_s=0, severity=v
            ),
            "severity",
            6,
        ),
    ],
)
def test_scales_are_bounded(make, field, value):
    with pytest.raises(ValidationError, match=field):
        make(value)


def test_a_clock_cannot_fill_more_steps_than_it_has():
    with pytest.raises(ValidationError, match="steps filled"):
        Clock(id="c", name="The exam", steps=["one", "two"], filled=3)

    assert Clock(id="c", name="The exam", steps=["one", "two"], filled=1).remaining == 1


def test_stances_between_factions_are_bounded():
    with pytest.raises(ValidationError):
        Faction(id="f", name="F", relations={"g": 150})


def test_new_ids_are_sequential_and_skip_ids_in_use():
    state = minimal_state()
    state.deeds["deed-2"] = Deed(id="deed-2", actor_id="p", kind="x", text="", turn=1, world_s=0)

    assert [state.new_id("deed"), state.new_id("deed"), state.new_id("rumor")] == [
        "deed-1",
        "deed-3",
        "rumor-1",
    ]


def test_due_events_are_pending_on_this_timeline_and_in_time_order():
    def event(event_id, due_s, **kwargs):
        return PendingEvent(id=event_id, kind="test", due_s=due_s, **kwargs)

    state = minimal_state(
        pending_events={
            e.id: e
            for e in [
                event("late", 50),
                event("first", 10),
                event("tied", 10),
                event("fired", 5, status=EventStatus.FIRED),
                event("other-timeline", 5, timeline_id="rewound"),
                event("future", 500),
            ]
        }
    )

    assert [e.id for e in state.due_events(100)] == ["first", "tied", "late"]


def test_personal_clock_is_world_time_plus_offset():
    lin = cultivation_world().player
    lin.personal_offset_s = 3

    assert lin.personal_s(100) == 103


def test_player_and_npcs():
    state = grounded_world()

    assert state.player.name == "Luca Esposito"
    assert {c.id for c in state.npcs()} == {"carmine", "bartender"}


def test_apparent_attitude_hides_a_traitor():
    carmine = grounded_world().characters["carmine"]

    attitude = carmine.attitude_toward("luca")

    assert attitude.affinity < 0 < attitude.shown_affinity
    assert carmine.attitude_toward("nobody") == Attitude()


def test_a_world_with_nothing_extraordinary_is_grounded():
    assert grounded_world().bible.grounded
    assert not cultivation_world().bible.grounded
    assert not WorldBible(
        extraordinary=[Extraordinary(id="v", kind="vampires", prevalence=Prevalence.HIDDEN)]
    ).grounded


def test_sheet_lookups():
    sheet = cultivation_world().player.sheet
    sheet.rulings.append(
        Ruling(
            id="r1",
            topic="throw_speed",
            power_id="time-stop",
            question="Does a stopped-time throw hit at the speed of light?",
            answer="Yes.",
            holds=True,
        )
    )

    assert sheet.power("time-stop").time.lasts_s == 3
    assert sheet.skill("HERB LORE").level is SkillLevel.FAIR
    assert sheet.axes.on(PowerAxis.KNOWLEDGE) == 3
    assert sheet.ruling("throw_speed", "time-stop").holds
    assert sheet.ruling("throw_speed") is None
    assert SkillLevel.MASTER.rank > SkillLevel.NOVICE.rank


def test_rumor_hearers_come_from_heard_at():
    rumor = Rumor(id="r", text="A monster did it.", is_true=False, heard_at={"p": 30, "q": 60})

    assert rumor.heard_by == ["p", "q"]
