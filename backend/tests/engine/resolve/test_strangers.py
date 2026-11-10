"""F1, W1, W2. "I grab a knife and kill some random guy": a victim the scene hasn't named is made
real when the place holds them, with a strength rolled by the world, so the killing has a victim,
witnesses and consequences. Most strangers are ordinary, a few can fight, and a hidden master is
rare and always sees it coming (Miki, 2026-11-05)."""

import pytest

from engine import pipeline
from engine.contracts import Aim, Intent, MeansVerdict, OutcomeClass, Plausibility, Stranger
from engine.contracts.resolution import BeatVerdict
from engine.resolve import strangers
from engine.rng import SeededRng
from engine.samples import cultivation_world, grounded_world
from engine.state import CharacterStatus, PassingState, StepResult

from .worlds import SEEDS, ctx, facts, item, resolve, rng, step


def kill_someone(
    plausibility: Plausibility = Plausibility.PLAUSIBLE,
    *,
    crowd: bool = False,
    unaware: bool = True,
):
    return step(
        "stab some random guy",
        verb="kill",
        aim=Aim.KILL,
        uses=[item("knife")],
        targets=["some random guy"],
        stranger=Stranger(who="a man buying cigarettes", plausibility=plausibility, crowd=crowd),
        facts=facts(
            can_respond=False if unaware else None,
            why_not="unaware" if unaware else "",
            means=MeansVerdict.CLEARLY_ENOUGH,
        ),
    )


def in_the_street():
    """Luca alone in the streets of Naples, where the police keep the law."""
    state = grounded_world()
    state.characters["luca"].location_id = "naples"
    state.scene.place_id = "naples"
    state.scene.present_ids = ["luca"]
    return state


def ordinary(monkeypatch):
    monkeypatch.setattr(strangers, "TOUGH_ODDS", 0.0)
    monkeypatch.setattr(strangers, "MASTER_ODDS", dict.fromkeys(strangers.MASTER_ODDS, 0.0))


def test_an_ordinary_stranger_who_never_saw_it_coming_dies(monkeypatch):
    ordinary(monkeypatch)
    state = in_the_street()

    resolution = resolve(state, Intent(steps=[kill_someone()]))
    (settled,) = resolution.steps
    (stranger_id,) = settled.strangers
    assert (settled.outcome_class, settled.result) == (OutcomeClass.CERTAIN, StepResult.SUCCESS)
    created, killed = settled.effects.characters
    assert (created.id, created.name, created.location_id) == (
        stranger_id,
        "a man buying cigarettes",
        "naples",
    )
    assert created.meets_player
    assert (killed.id, killed.status) == (stranger_id, CharacterStatus.DEAD)
    assert killed.known_to_player  # the player saw what they did, scene record or not
    (deed,) = settled.deeds
    assert deed.victim_ids == [stranger_id]
    assert settled.beats[-1].verdict is BeatVerdict.MADE_CANON
    assert stranger_id not in state.characters  # resolve never changes the state it was given


def test_nobody_there_means_the_knife_meets_no_one():
    state = in_the_street()

    resolution = resolve(state, Intent(steps=[kill_someone(Plausibility.ABSENT)]))
    (settled,) = resolution.steps
    assert (settled.outcome_class, settled.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert settled.strangers == []
    assert settled.effects.characters == []
    assert settled.deeds == []
    assert settled.beats[-1].verdict is BeatVerdict.EMPTY


def test_an_uncertain_stranger_is_rolled_for():
    state = in_the_street()
    intent = Intent(steps=[kill_someone(Plausibility.UNCERTAIN)])
    found = set()
    for seed in SEEDS[:80]:
        (settled,) = resolve(state, intent, seed).steps
        found.add(bool(settled.strangers))
        assert settled.beats[-1].roll is not None
    assert found == {True, False}


def test_a_known_target_is_never_replaced_by_a_stranger(monkeypatch):
    ordinary(monkeypatch)
    state = grounded_world()
    aimed = kill_someone()
    aimed.target_ids = ["bartender"]

    (settled,) = resolve(state, Intent(steps=[aimed])).steps
    assert settled.strangers == []
    assert settled.deeds[0].victim_ids == ["bartender"]


def test_a_hidden_master_always_sees_it_coming(monkeypatch):
    monkeypatch.setattr(strangers, "MASTER_ODDS", dict.fromkeys(strangers.MASTER_ODDS, 1.0))
    state = in_the_street()

    for seed in SEEDS[:40]:
        resolution = resolve(state, Intent(steps=[kill_someone()]), seed)
        (settled,) = resolution.steps
        # One step above Luca, with a body at a person's peak, and alert, whatever the
        # interpret step said: a long shot at best.
        assert settled.outcome_class is OutcomeClass.LONG_SHOT
        created = settled.effects.characters[0]
        assert created.axes is not None and created.axes.might == 4
        assert created.attributes == strangers._body(4, True)
        assert [(part.text, part.points) for part in settled.roll.throw.made_of] == [
            ("a man buying cigarettes' strength and speed, level 4", 37),
            ("one step of power above you, met head-on", 10),
        ]


def test_a_stranger_who_can_fight_is_made_with_the_body_for_it():
    # G13, A3: a throw against them reads their level from their sheet like anyone's.
    assert strangers._body(strangers.ORDINARY_TIER, False) is None
    tough = strangers._body(strangers.ORDINARY_TIER + 2, False)
    assert (tough.strength, tough.speed, tough.toughness, tough.wits) == (4, 4, 4, 3)
    master = strangers._body(4, True)
    assert (master.strength, master.speed, master.toughness, master.wits) == (5, 5, 5, 5)


def test_a_hidden_master_is_never_stronger_than_the_world_holds(monkeypatch):
    monkeypatch.setattr(strangers, "MASTER_ODDS", dict.fromkeys(strangers.MASTER_ODDS, 1.0))
    state = cultivation_world()
    state.characters["lin"].sheet.axes.might = 10  # stronger than the top realm's tier

    might, master = strangers._measure(state, state.player, SeededRng("s-t"))
    assert master
    assert might == 10  # the strongest body in the world, never beyond it


def test_the_dead_never_set_how_strong_a_hidden_master_can_be(monkeypatch):
    monkeypatch.setattr(strangers, "MASTER_ODDS", dict.fromkeys(strangers.MASTER_ODDS, 1.0))
    state = in_the_street()
    state.player.sheet.axes.might = 8
    state.characters["carmine"].sheet.axes.might = 9
    state.characters["carmine"].status = CharacterStatus.DEAD

    might, master = strangers._measure(state, state.player, SeededRng("s-t"))
    assert master
    assert might == 8  # as strong as the strongest one living, never the dead Carmine


@pytest.mark.parametrize(
    ("world", "master"),
    [(grounded_world, 1 / 1000), (cultivation_world, 1 / 200)],
)
def test_hidden_masters_are_rare_and_rarer_where_nothing_is_extraordinary(world, master):
    state = world()
    assert strangers.master_odds(state) == master

    draws = [
        strangers._measure(state, state.player, SeededRng(f"seed-{i}-who")) for i in range(30000)
    ]
    masters = sum(1 for _, is_master in draws if is_master) / len(draws)
    tough = sum(1 for might, is_master in draws if might > 1 and not is_master) / len(draws)
    assert masters == pytest.approx(master, abs=0.003)
    assert tough == pytest.approx(strangers.TOUGH_ODDS, abs=0.01)


def test_a_killing_in_a_crowd_has_a_witness_who_can_go_to_the_police(monkeypatch):
    ordinary(monkeypatch)
    state = in_the_street()
    resolution = resolve(state, Intent(steps=[kill_someone(crowd=True)]))
    (settled,) = resolution.steps
    stranger_id, onlooker_id = settled.strangers

    played = pipeline.play_out(state, resolution, ctx(), rng())
    after = played.state
    assert after.characters[stranger_id].status is CharacterStatus.DEAD
    assert after.characters[onlooker_id].alive
    (deed,) = after.deeds.values()
    assert deed.victim_ids == [stranger_id]
    assert deed.witness_ids == [onlooker_id]
    # The witness sets off on their way to the law (W2, W11).
    assert any(
        e.kind == "world.report" and onlooker_id in e.subject_ids
        for e in after.pending_events.values()
    )


def test_no_onlooker_is_made_up_where_someone_already_saw_it(monkeypatch):
    ordinary(monkeypatch)
    state = grounded_world()  # at the bar, with Carmine and the bartender

    (settled,) = resolve(state, Intent(steps=[kill_someone(crowd=True)])).steps
    assert len(settled.strangers) == 1


def test_someone_asleep_nearby_sees_nothing_so_the_crowd_gives_a_witness(monkeypatch):
    ordinary(monkeypatch)
    state = in_the_street()
    sleeper = state.characters["bartender"]
    sleeper.location_id = "naples"
    sleeper.sheet.condition.states = [PassingState(name="asleep")]

    (settled,) = resolve(state, Intent(steps=[kill_someone(crowd=True)])).steps
    assert len(settled.strangers) == 2
