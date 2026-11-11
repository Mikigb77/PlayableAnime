"""W1, W4, W11: how the world takes a fight both sides agreed to (`engine.resolve.bouts`).

From Miki's long story (2026-11): every blow of a lesson with a mentor was recorded as an attack
on him, which left him at the bottom of affinity, afraid, bearing five grudges and due to come
for revenge. A bout is one deed that nobody takes as an attack; a death both accepted is a loss
only to those close to the dead; and a blow beyond the terms costs more trust than an open one.
"""

import pytest

from engine.base import DAY
from engine.contracts import ActionKind, Aim, IntentStep, ProposedDeed, StepFacts
from engine.samples import cultivation_world
from engine.state import (
    Attitude,
    Bout,
    Character,
    CharacterSheet,
    Encounter,
    EncounterKind,
    Health,
    LadderPosition,
    Membership,
    PowerAxes,
    PowerAxis,
    Prominence,
    Terms,
    WorldState,
)
from engine.visibility import memory_view
from engine.world import Kind
from engine.world.answers import Answer
from engine.world.norms import Nature, deed_nature, is_crime
from engine.world.telling import account
from engine.world.tuning import BOUT_REGARD, BOUT_REGARD_MAX, BROKEN_TERMS_TRUST

from .test_encounters import turn
from .test_world import deed_step, idle, moved_on, pending_of, play, the_deed

WORLD_KINDS = (Kind.REPORT, Kind.ANSWER, Kind.RUMOR, Kind.TIDINGS, Kind.DISCOVERY)


def lesson() -> WorldState:
    """Lin at the well with Master Shen, a key elder two realms above him who is fond of him.
    Zhao, who dislikes Lin, looks on."""
    state = cultivation_world()
    shen = Character(
        id="shen",
        name="Master Shen",
        prominence=Prominence.KEY,
        location_id="well",
        memberships=[Membership(faction_id="inner-court", rank="elder", loyalty=80)],
        sheet=CharacterSheet(
            axes=PowerAxes(might=6), ladders=[LadderPosition(ladder_id="realms", rung=2)]
        ),
    )
    shen.sheet.disposition.attitudes["lin"] = Attitude(affinity=20)
    state.characters["shen"] = shen
    state.scene.present_ids.append("shen")
    return state


def blow(aim: Aim, terms: Terms | None = None, meant: Aim | None = None) -> IntentStep:
    """A blow at Master Shen as the interpret step proposes it, with what he means in answer."""
    return IntentStep(
        text="strike at Master Shen",
        verb="strike",
        kind=ActionKind.EXCHANGE,
        proposed_duration_s=5,
        aim=aim,
        target_ids=["shen"],
        axis=PowerAxis.MIGHT,
        facts=StepFacts(opposition_ids=["shen"], can_respond=True, terms=terms, foes_mean=meant),
    )


def standing(state: WorldState) -> dict:
    """The player's reputation everywhere, to see that nothing moved it."""
    places = {p.id: p.player_reputation.model_dump() for p in state.places.values()}
    factions = {f.id: f.player_reputation.model_dump() for f in state.factions.values()}
    return {"places": places, "factions": factions}


def bout(terms: Terms = Terms.NO_HARM, partner: str = "zhao") -> ProposedDeed:
    return ProposedDeed(
        kind="bout", text="trade blows", target_ids=[partner], severity=1, terms=terms
    )


# --- the bout ----------------------------------------------------------------------------------


def test_a_long_lesson_with_a_mentor_leaves_no_grudge_fear_rumor_report_or_revenge():
    """Thirty exchanges, some read as woundings or killings, and Shen striking back each time:
    one deed, a little more regard, and nothing else."""
    state = lesson()
    before = standing(state)
    aims = (Aim.SUBDUE, Aim.WOUND, Aim.KILL)
    for n in range(30):
        first = n == 0
        step = blow(aims[n % 3], Terms.NO_HARM if first else None, (None, Aim.WOUND)[n % 2])
        state, played, _ = turn(state, step, seed=n, turn_no=3 + n)
        assert played.resolution.steps[0].bout is not None, n

    [deed] = state.deeds.values()
    assert deed.is_bout and deed.terms is Terms.NO_HARM
    assert deed_nature(state, deed) is Nature.OTHER and not is_crime(state, deed)
    shen = state.characters["shen"].attitude_toward("lin")
    assert shen == Attitude(affinity=20 + BOUT_REGARD, trust=BOUT_REGARD)
    # Zhao watched it all and thinks of Lin what he thought before.
    assert state.characters["zhao"].attitude_toward("lin") == Attitude(affinity=-30)
    assert standing(state) == before
    assert not state.rumors
    assert not [e for kind in WORLD_KINDS for e in pending_of(state, kind)]
    for fighter in ("lin", "shen"):
        condition = state.characters[fighter].sheet.condition
        assert (condition.health, condition.states, condition.wounds) == (Health.UNHURT, [], [])

    # And nothing comes of it later.
    state, fired = idle(state, state.world_s + 30 * DAY, turn=40)
    assert not [e for e in fired if e.kind in WORLD_KINDS]
    assert not state.characters["shen"].attitude_toward("lin").grudges


def test_the_same_blow_with_no_terms_is_an_attack_on_him():
    """What the lesson's first blow does when nobody agreed to anything: Shen remembers it."""
    state, _, _ = turn(lesson(), blow(Aim.WOUND, meant=Aim.NONE))

    [deed] = state.deeds.values()
    assert not deed.agreed and deed_nature(state, deed) is Nature.HARM
    shen = state.characters["shen"].attitude_toward("lin")
    assert shen.affinity < 20 and shen.fear > 0 and shen.grudges


def test_the_blows_of_one_bout_are_one_deed_and_a_later_bout_is_another():
    state = cultivation_world()
    terms = Bout(terms=Terms.NO_HARM, with_ids=["zhao"])
    state = play(state, deed_step(bout())).state  # its first blow, before the encounter is on
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=["zhao"],
        started_turn=2,
        started_s=state.world_s - 2,
        bout=terms,
    )
    for _ in range(5):
        state = play(state, deed_step(bout())).state
    assert len(state.deeds) == 1

    # The encounter over, they meet again another day: a new bout, and a new deed.
    state, _ = idle(state, state.world_s + DAY)
    state.scene.encounter = None
    state = play(state, deed_step(bout())).state
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=["zhao"],
        started_turn=9,
        started_s=state.world_s - 2,
        bout=terms,
    )
    state = play(state, deed_step(bout())).state
    assert len(state.deeds) == 2


def test_bouts_alone_make_nobody_a_close_friend():
    state = cultivation_world()
    state.characters["zhao"].sheet.disposition.attitudes["lin"] = Attitude()
    seen = []
    for _ in range(20):
        state = play(state, deed_step(bout())).state  # a bout a day, each its own
        zhao = state.characters["zhao"].attitude_toward("lin")
        seen.append((zhao.affinity, zhao.trust))

    assert seen[0] == (BOUT_REGARD, BOUT_REGARD)
    assert seen[-1] == (BOUT_REGARD_MAX, BOUT_REGARD_MAX)
    assert zhao.fear == 0 and not zhao.grudges


def test_a_wound_inside_terms_that_accept_wounds_is_still_the_bout():
    """First blood drawn in a duel both agreed to: no crime, no grudge, nothing to report."""
    state = play(cultivation_world(), deed_step(bout(Terms.WOUNDS))).state
    deed = the_deed(state)

    assert deed.is_bout and not is_crime(state, deed)
    assert not state.characters["zhao"].attitude_toward("lin").grudges
    assert not pending_of(state, Kind.REPORT) and not state.rumors


@pytest.mark.parametrize(
    ("terms", "told"),
    [
        (Terms.NO_HARM, "sparred with"),
        (Terms.WOUNDS, "fought a duel with"),
        (Terms.DEATH, "fought a duel to the death with"),
    ],
)
def test_the_world_tells_a_bout_as_the_fight_both_wanted(terms, told):
    state = play(cultivation_world(), deed_step(bout(terms))).state
    deed = the_deed(state)

    assert account(state, deed) == f"Lin Feng {told} Zhao Kun at the outer-court well."
    (entry,) = memory_view(state).deeds
    assert entry.text == f"You {told} Zhao Kun at the outer-court well."


# --- beyond the terms --------------------------------------------------------------------------


def test_a_blow_beyond_the_terms_costs_more_trust_than_an_open_one():
    def after(broke: bool) -> Attitude:
        attack = ProposedDeed(
            kind="attack",
            text="strike Zhao in earnest (it worked)",
            victim_ids=["zhao"],
            severity=3,
            broke_terms=broke,
        )
        state = play(cultivation_world(), deed_step(attack)).state
        assert is_crime(state, the_deed(state))  # an attack either way
        return state.characters["zhao"].attitude_toward("lin")

    open_attack, under_cover = after(False), after(True)
    assert open_attack.trust < 0
    assert under_cover.trust == pytest.approx(open_attack.trust * BROKEN_TERMS_TRUST, abs=1)
    assert (under_cover.affinity, under_cover.fear) == (open_attack.affinity, open_attack.fear)
    assert under_cover.grudges and open_attack.grudges


def test_even_a_light_blow_beyond_the_terms_is_remembered():
    def grudges(broke: bool) -> list:
        swing = ProposedDeed(
            kind="attack",
            text="strike at Zhao after he yielded (it failed)",
            target_ids=["zhao"],
            severity=1,
            broke_terms=broke,
        )
        state = play(cultivation_world(), deed_step(swing)).state
        return state.characters["zhao"].attitude_toward("lin").grudges

    assert not grudges(False)
    assert [g.reason for g in grudges(True)] == [
        "Lin Feng attacked Zhao Kun at the outer-court well."
    ]


# --- a death both accepted ---------------------------------------------------------------------


def duel_world() -> WorldState:
    """Zhao's sworn friend Mei is away in the inner court, and Wei, a stranger to both, looks
    on at the well."""
    state = cultivation_world()
    state.characters["mei"] = Character(id="mei", name="Mei", location_id="inner-court")
    state.characters["mei"].sheet.disposition.attitudes["zhao"] = Attitude(affinity=80)
    state.characters["wei"] = Character(id="wei", name="Wei", location_id="well")
    state.scene.present_ids.append("wei")
    return state


def killing(terms: Terms | None) -> ProposedDeed:
    return ProposedDeed(
        kind="kill", text="kill Zhao (it worked)", victim_ids=["zhao"], severity=4, terms=terms
    )


def test_a_death_both_accepted_is_no_crime_and_turns_no_bystander_against_them():
    state = play(duel_world(), deed_step(killing(Terms.DEATH), dead=("zhao",))).state
    deed = the_deed(state)

    assert deed.agreed and not deed.is_bout
    assert deed_nature(state, deed) is Nature.HARM and not is_crime(state, deed)
    assert not pending_of(state, Kind.REPORT)
    assert account(state, deed) == "Lin Feng killed Zhao Kun in a duel at the outer-court well."
    assert not state.rumors  # Wei, who watched, hasn't told anyone yet (W2)
    wei = state.characters["wei"].attitude_toward("lin")
    assert wei.affinity == 0 and not wei.grudges and wei.fear > 0  # he saw what Lin can do

    state, fired = idle(moved_on(state), state.world_s + 30 * DAY)

    told = [r.text for r in state.rumors.values() if r.deed_id == deed.id]
    assert told == [account(state, deed)]  # still news
    assert state.places["well"].mood == ""  # nobody there is shaken by it
    # Word reaches Zhao's court and the sect: they think a little less of Lin, fear him a
    # little more, and send nobody. The mountain only learns what he can do.
    for faction_id in ("outer-court", "azure-cloud"):
        faction = state.factions[faction_id]
        assert (faction.player_reputation.esteem, faction.threat) == (-4, 0)
        assert faction.player_reputation.fear > 0
    peak = state.places["azure-peak"].player_reputation
    assert peak.esteem == 0 and peak.fear > 0
    sent = [e.payload for e in fired if e.kind == Kind.ANSWER and e.payload.get("faction_id")]
    assert sent == []


def test_the_same_killing_with_no_terms_is_a_crime_the_whole_mountain_holds_against_them():
    state = play(duel_world(), deed_step(killing(None), dead=("zhao",))).state
    deed = the_deed(state)

    assert is_crime(state, deed) and pending_of(state, Kind.REPORT)
    assert state.characters["wei"].attitude_toward("lin").affinity < 0
    # Until Wei gets away with it, the mountain knows nothing.
    assert state.places["well"].mood == ""
    assert state.places["azure-peak"].player_reputation.esteem == 0

    state, fired = idle(state, state.world_s + 30 * DAY)

    assert state.places["well"].mood.startswith("shaken")
    assert state.places["azure-peak"].player_reputation.esteem < 0
    sent = {e.payload["answer"] for e in fired if e.kind == Kind.ANSWER}
    assert Answer.ARREST.value in sent


def test_those_close_to_the_dead_still_grieve_a_death_both_accepted():
    """Mei was Zhao's sworn friend: the terms were his to accept, and the loss is hers."""
    state = play(duel_world(), deed_step(killing(Terms.DEATH), dead=("zhao",))).state

    assert not pending_of(state, Kind.TIDINGS)  # nobody has told anyone yet (W2)

    state, fired = idle(moved_on(state), state.world_s + 30 * DAY)

    told = {e.payload.get("character_id") for e in fired if e.kind == Kind.TIDINGS}
    assert "mei" in told
    mei = state.characters["mei"].attitude_toward("lin")
    assert mei.affinity < 0 and mei.grudges
    avengers = [e.payload["avenger_id"] for e in fired if e.payload.get("answer") == "revenge"]
    assert avengers == ["mei"]
