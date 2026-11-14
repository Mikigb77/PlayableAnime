"""T18's first reading: what the first model makes of a plain line (V3, B5).

Every turn starts with the interpret step filling a form from the player's words, and code
decides everything else from that form: a killing read with no target kills nobody, a trip with
no destination can't be timed, a lesson whose blow carries no terms is an attack. Each line
here is read alone, where its story stands, with no turn played, and has one or two things the
reading must get right: mostly the slips the real model has made in play. The score is the
share read right, which is what a change of the form, of the guide or of the model is weighed
by, next to what the step costs (B6, B8, `evals.results`).

Live only: a scripted reading would only read back what the script wrote.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from engine.base import DAY, HOUR, MINUTE
from engine.context import Language, StorySettings
from engine.contracts import (
    ActionKind,
    Aim,
    ExchangeKind,
    GrowthKind,
    Intent,
    IntentStep,
    Plausibility,
    SheetPart,
    StandingAction,
)
from engine.contracts.intent import Challenge, UseSource
from engine.samples import grounded_world
from engine.state.bible import RuleTopic, WorldRule
from engine.state.scene import Bout, Encounter, EncounterKind, Terms
from engine.state.sheet import TalentFit
from engine.state.world import WorldState
from engine.timekeeping import parse_clock
from evals import worlds
from evals.runner import Eval, Read
from evals.scenario import LIVE_ONLY, REGISTRY
from evals.scenarios.t17 import lesson_begins

scenario = REGISTRY.scenario

type Test = Callable[[Intent], bool]

# How much of a reading a line read wrong shows: enough for a plan of two or three steps.
SHOWN_CHARS = 1500
# What a reading's words are left out of when it is shown: only what code decides from is.
WORDS = {"text", "summary", "up_against", "miss_costs", "why_not", "lines", "reason", "effect"}


@dataclass(frozen=True)
class Line:
    """One line the first model reads where `world` stands, in the story's `language`, and
    what its reading must get right, each under the name the results keep it by."""

    world: Callable[[], WorldState]
    says: str
    reads: tuple[tuple[str, Test], ...]
    language: Language = Language.EN


def line(world: Callable[[], WorldState], says: str, language: Language = Language.EN, **reads):
    """A line, with each thing to read right as `name_in_words=test`."""
    named = tuple((name.replace("_", " "), test) for name, test in reads.items())
    return Line(world, says, named, language)


# --- what a reading is tested for ----------------------------------------------------------------


def some(test: Callable[[IntentStep], bool]) -> Test:
    return lambda intent: any(test(step) for step in intent.steps)


def every(test: Callable[[IntentStep], bool]) -> Test:
    """Every step, and at least one: a reading with no step read nothing."""
    return lambda intent: bool(intent.steps) and all(test(step) for step in intent.steps)


def at(who: str, aim: Aim | None = None) -> Callable[[IntentStep], bool]:
    """A step aimed at `who`, and with `aim` when one is given."""
    return lambda step: who in step.target_ids and (aim is None or step.aim is aim)


def named(ref: str | None, *words: str) -> bool:
    """Whether an id or a name holds every one of `words`: "aura", "blade" for `aura-blade` and
    for "Aura blade". Code finds a power, a technique or an item by its id or by its name
    (`engine.resolve.checks`), so either is a right reading."""
    said = (ref or "").casefold().replace("-", " ").replace("_", " ").split()
    return all(word in said for word in words)


def uses(*words: str, part: SheetPart | None = None) -> Callable[[IntentStep], bool]:
    """A step that draws on something of the sheet named by `words`, under `part` when one is
    given, or that a beat of it uses."""

    def found(step: IntentStep) -> bool:
        sheet = any(named(u.ref, *words) and part in (None, u.part) for u in step.uses)
        beats = part is None and any(
            named(u.ref, *words) or named(u.thing, *words) for b in step.beats for u in b.uses
        )
        return sheet or beats

    return found


def things(
    step: IntentStep, word: str, source: UseSource | None = None
) -> list[Plausibility | None]:
    """How a step judged everything its beats use whose name holds `word`, from `source` when
    one is given."""
    return [
        u.plausibility
        for b in step.beats
        for u in b.uses
        if word in u.thing.casefold() and source in (None, u.source)
    ]


def clock(step: IntentStep, hhmm: str) -> bool:
    return step.until is not None and parse_clock(step.until) == parse_clock(hhmm)


def lasts(step: IntentStep, seconds: int) -> bool:
    return step.timed and step.proposed_duration_s == seconds


def moves(step: IntentStep, kind: ExchangeKind, with_id: str | None = None) -> bool:
    return any(e.kind is kind and (with_id is None or e.with_id == with_id) for e in step.exchanges)


# --- the worlds a few lines need -----------------------------------------------------------------


def lesson() -> WorldState:
    """Elder Mo has agreed to test Lin at the well, touches only, and nothing has been struck."""
    state = worlds.sect()
    lesson_begins(state)
    return state


def mid_lesson() -> WorldState:
    """The same lesson a few blows in: the bout is under way on record (W1)."""
    state = lesson()
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=["elder-mo"],
        started_turn=state.turn,
        started_s=state.world_s,
        bout=Bout(terms=Terms.NO_HARM, with_ids=["elder-mo"]),
    )
    state.scene.ended_on = (
        "Elder Mo turns Lin's cut aside and steps in close to correct his stance. 'Your weight "
        "is on the wrong foot, boy.'"
    )
    return state


def first_blood() -> WorldState:
    """Lin and Guo Tai, who has just taken up a duel to first blood."""
    state = worlds.duel(charging=False)
    state.scene.ended_on = "Guo Tai draws his blade and salutes. 'To first blood, then. Come.'"
    return state


def evening_on_the_farm() -> WorldState:
    """The Weller farm at supper time, which the sample starts in the morning of."""
    state = worlds.farm()
    state.world_s = 12 * HOUR
    return state


def deadly_without_a_pill() -> WorldState:
    """Lin at the peak of his realm with no pill, in a world whose own rule says the climb
    kills without one: a danger the player may choose to run (G19, G8)."""
    state = worlds.seclusion()
    state.bible.rules.append(
        WorldRule(
            id="foundation-bottleneck",
            text=(
                "Breaking through to Foundation Establishment is highly lethal without a "
                "Foundation Pill."
            ),
            fixed=False,
            topic=RuleTopic.LIMITS,
        )
    )
    return state


def sources(step: IntentStep, word: str) -> list[UseSource]:
    """Where a step's beats say they get everything whose name holds `word`."""
    return [u.source for b in step.beats for u in b.uses if word in u.thing.casefold()]


def waits_until(intent: Intent, first: str, last: str) -> bool:
    """Whether the reading's first step waits for an hour of the clock from `first` to `last`,
    with the step the player set for that hour after it."""
    if len(intent.steps) < 2 or intent.steps[0].until is None:
        return False
    hour = parse_clock(intent.steps[0].until)
    return hour is not None and parse_clock(first) <= hour <= parse_clock(last)


# --- the lines -----------------------------------------------------------------------------------

LINES: tuple[Line, ...] = (
    # Who a step is aimed at, and what it would do to them (V3, F4).
    line(
        worlds.one_witness,
        "I cut Han's throat while he sleeps",
        a_throat_cut_is_a_killing_aimed_at_Han=some(at("han", Aim.KILL)),
        a_killing_in_his_sleep_is_no_bout=every(lambda s: s.facts.terms is None),
        an_empty_yard_is_no_crowd=every(lambda s: not s.facts.crowd),
    ),
    line(
        worlds.sect,
        "I punch Zhao in the stomach",
        a_punch_harms_Zhao_and_is_no_killing=some(
            lambda s: "zhao" in s.target_ids and s.aim in (Aim.WOUND, Aim.SUBDUE)
        ),
    ),
    line(
        worlds.sect_with_a_witness,
        "I knock Wei out with the pommel of my sword",
        knocking_Wei_out_subdues_him=some(at("wei", Aim.SUBDUE)),
    ),
    line(
        worlds.sect,
        "I bow to Senior Brother Zhao and ask how his training goes",
        a_bow_and_a_question_are_aimed_at_Zhao=some(at("zhao")),
        a_bow_and_a_question_harm_nobody=every(lambda s: s.aim is Aim.NONE),
    ),
    line(
        worlds.sect,
        "I rest my hand on my sword and tell Zhao to step away from the bucket",
        a_threat_is_no_blow=every(lambda s: s.aim is Aim.NONE),
    ),
    line(
        worlds.insulted,
        "I slap him across the face",
        him_is_the_one_the_scene_left_them_facing=some(at("zhao")),
    ),
    line(
        worlds.noon_at_the_well,
        "I grab the nearest disciple in the queue and break his arm",
        someone_unnamed_in_a_queue_is_a_stranger_the_place_holds=some(
            lambda s: (
                s.aim.harmful
                and "han" not in s.target_ids
                and s.stranger is not None
                and s.stranger.plausibility is Plausibility.PLAUSIBLE
            )
        ),
    ),
    # What a step uses, and whether it is there (G14, R2, A4).
    line(
        worlds.sect,
        "I draw my sword and cut the rope of the well bucket",
        the_sword_they_carry_is_the_item_on_the_sheet=some(uses("sword")),
    ),
    line(
        worlds.among_the_pines,
        "I snap a dead branch off the nearest pine",
        a_branch_among_pines_is_simply_there=every(
            lambda s: all(p in (None, Plausibility.PLAUSIBLE) for p in things(s, "branch"))
        ),
    ),
    line(
        worlds.throne_room,
        "I grab a stone from the floor and throw it at Elder Mo",
        # Whatever the reading calls what they reach for: the stone, or the bare floor.
        a_stone_in_a_polished_marble_hall_is_absent=some(
            lambda s: Plausibility.ABSENT in things(s, "", UseSource.SCENE)
        ),
    ),
    line(
        worlds.sect,
        "I stop time and step behind Zhao",
        stopping_time_is_the_power_on_the_sheet=some(uses("time", "stop", part=SheetPart.POWER)),
        a_step_in_stopped_time_has_its_own_lived_seconds=some(
            lambda s: bool(s.proposed_personal_s)
        ),
    ),
    line(
        worlds.born_to_the_blade,
        "I shape my aura into a blade and cut at the practice post",
        an_aura_blade_they_know_is_the_move_on_their_sheet=some(uses("aura", "blade")),
        each_talent_is_ruled_on_for_a_thing_not_ruled_yet=some(
            lambda s: (
                {c.talent_id for c in s.talent_cases}
                >= {"talent-the-sword", "talent-genius-architect"}
            )
        ),
        a_blade_of_aura_is_inside_a_talent_for_the_blade=some(
            lambda s: any(
                c.talent_id == "talent-the-sword" and c.fit is TalentFit.INSIDE
                for c in s.talent_cases
            )
        ),
    ),
    line(
        worlds.born_to_the_blade,
        "I send aura into my feet and leap onto the roof of the well house",
        a_move_made_with_their_aura_draws_on_it=some(uses("aura")),
        # Named as a technique, or filed under the power with a name of its own ("aura-jump"),
        # which code takes as a move all the same (`engine.resolve.checks`).
        a_move_not_on_the_sheet_is_named_as_a_move=some(
            lambda s: any(
                u.part in (SheetPart.TECHNIQUE, SheetPart.POWER)
                and not named(u.ref, "aura", "blade")
                and (u.ref or "").casefold() != "aura"
                for u in s.uses
            )
        ),
    ),
    # Where a step goes and how long it takes (W10).
    line(
        worlds.noodle_road,
        "I walk down to Qinghe market town",
        a_walk_to_the_market_town_is_a_trip_there=some(
            lambda s: s.destination == "market-town" and s.kind is ActionKind.TRAVEL
        ),
        a_trip_is_one_step=lambda i: sum(bool(s.destination) for s in i.steps) == 1,
    ),
    line(
        worlds.noodle_road,
        "I walk toward Qinghe market town for an hour",
        a_trip_with_a_time_keeps_its_destination=some(lambda s: s.destination == "market-town"),
        a_trip_with_a_time_lasts_the_time_the_player_gave=some(lambda s: lasts(s, HOUR)),
    ),
    line(
        worlds.sect,
        "I sit down on the rim of the well",
        a_step_that_stays_names_no_destination=every(lambda s: not s.destination),
        a_step_of_one_thing_is_one_step=lambda i: len(i.steps) == 1,
    ),
    line(
        worlds.sect,
        "I meditate by the well until nightfall",
        until_nightfall_is_seven_in_the_evening=some(lambda s: clock(s, "19:00")),
    ),
    line(
        worlds.above_the_camp,
        "I lie down in the lee of the wall and sleep till dawn",
        sleeping_till_dawn_is_a_rest_until_five=some(
            lambda s: s.kind is ActionKind.REST and clock(s, "05:00")
        ),
    ),
    line(
        worlds.sect,
        "I practise sword forms for two hours",
        for_two_hours_is_timed=some(lambda s: lasts(s, 2 * HOUR)),
        practice_is_training=some(
            lambda s: (
                s.training is not None
                and s.training.kind in (GrowthKind.SKILL, GrowthKind.TECHNIQUE)
            )
        ),
    ),
    line(
        worlds.sect,
        "I train with the sword here for a year",
        a_year_of_training_is_a_time_skip=some(
            lambda s: s.kind is ActionKind.TIME_SKIP and s.proposed_duration_s >= 300 * DAY
        ),
    ),
    line(
        worlds.sect,
        "I nod to Zhao",
        a_nod_takes_seconds=lambda i: (
            0 < len(i.steps) and sum(s.proposed_duration_s for s in i.steps) <= MINUTE
        ),
    ),
    line(
        evening_on_the_farm,
        "I go up to bed and sleep through the night",
        a_nights_sleep_is_a_rest_of_hours=some(
            lambda s: (
                s.kind is ActionKind.REST
                and (5 * HOUR <= s.proposed_duration_s <= 11 * HOUR or s.until is not None)
            )
        ),
    ),
    line(
        worlds.sect,
        "I wait by the well until midday",
        # Midday starts at eleven on the clock the guide gives, and twelve is midday too. A
        # standing action given beside the step changes nothing: code plays the step.
        waiting_until_a_time_is_a_step_with_that_time=some(
            lambda s: clock(s, "11:00") or clock(s, "12:00")
        ),
    ),
    line(
        worlds.sect,
        "I wait",
        only_waiting_is_the_standing_action=lambda i: (
            i.standing is StandingAction.WAIT and not i.steps
        ),
    ),
    # A chained plan, and nothing added to it (R6).
    line(
        worlds.troll_lunges,
        "I throw a stone at the troll's eye, then run for the tunnel",
        a_plan_of_two_things_is_two_steps=lambda i: len(i.steps) == 2,
        the_throw_is_aimed_at_the_troll=lambda i: (
            bool(i.steps) and "troll" in i.steps[0].target_ids and i.steps[0].aim.harmful
        ),
        the_run_names_the_tunnel=lambda i: (
            len(i.steps) > 1 and "tunnel" in i.steps[-1].destination.casefold()
        ),
    ),
    # A bout both sides agreed to (W1).
    line(
        lesson,
        "I step in and aim a cut at Elder Mo's shoulder",
        a_lessons_first_blow_carries_its_terms=some(
            lambda s: (
                "elder-mo" in s.target_ids
                and s.facts.terms is Terms.NO_HARM
                and not s.facts.breaks_terms
            )
        ),
    ),
    line(
        mid_lesson,
        "While he corrects my stance I drop the sword and drive my fingers at his eyes, "
        "meaning to blind him for good",
        his_eyes_are_those_of_the_one_they_spar_with=some(at("elder-mo")),
        a_blow_meant_to_blind_goes_beyond_a_lessons_terms=some(
            lambda s: "elder-mo" in s.target_ids and s.facts.breaks_terms
        ),
    ),
    line(
        first_blood,
        "I salute him and open with a cut at his forearm",
        a_duel_to_first_blood_accepts_wounds=some(
            lambda s: (
                "guo" in s.target_ids and s.facts.terms is Terms.WOUNDS and not s.facts.breaks_terms
            )
        ),
    ),
    # The crowd and the talk (W2).
    line(
        worlds.noon_at_the_well,
        "I stab Han Jie in the heart where he dozes",
        a_killing_at_a_thronged_well_has_a_crowd=some(
            lambda s: "han" in s.target_ids and s.aim is Aim.KILL and s.facts.crowd
        ),
    ),
    line(
        worlds.noon_at_the_well,
        "I slip two fingers into the pouch of the disciple in front of me, so that nobody notices",
        what_is_done_unnoticed_has_no_crowd=every(lambda s: not s.facts.crowd),
    ),
    line(
        worlds.foot_village,
        "I ask Old Pan what people are saying in the village these days",
        asking_what_people_say_asks_for_the_talk=some(
            lambda s: "villager-0" in s.target_ids and s.facts.asks_talk
        ),
    ),
    line(
        worlds.foot_village,
        "I ask Tian the smith how much a new hoe would cost",
        a_question_about_one_thing_asks_for_no_talk=every(lambda s: not s.facts.asks_talk),
        a_question_about_a_price_is_put_to_the_smith=some(at("villager-2")),
    ),
    # Strength hidden and shown (G20).
    line(
        worlds.disguised_expert,
        "I hide my cultivation so they sense only Qi Condensation",
        hiding_strength_names_the_rung_to_show=some(
            lambda s: (
                s.show_strength is not None
                and s.show_strength.ladder_id == "realms"
                and s.show_strength.shown_rung == 0
            )
        ),
    ),
    line(
        worlds.disguised_expert,
        "I stop holding back and let my true cultivation show",
        letting_strength_show_names_no_rung=some(
            lambda s: (
                s.show_strength is not None
                and s.show_strength.ladder_id == "realms"
                and s.show_strength.shown_rung is None
            )
        ),
    ),
    line(
        worlds.disguised_expert,
        "I greet Young Master Wu with a polite bow",
        a_greeting_hides_and_shows_nothing=every(lambda s: s.show_strength is None),
    ),
    # Growth (A4, G19).
    line(
        lambda: worlds.seclusion(pill=True),
        "I swallow the Foundation Pill and sit down to break through to Foundation Establishment",
        breaking_through_is_the_next_rung_of_its_ladder=some(
            lambda s: (
                s.training is not None
                and s.training.kind is GrowthKind.BREAKTHROUGH
                and s.training.ladder_id == "realms"
            )
        ),
        sitting_down_to_break_through_is_an_attempt=some(
            lambda s: s.training is not None and s.training.attempt
        ),
    ),
    line(
        worlds.seclusion,
        "I circulate my qi until dawn, working toward Foundation Establishment",
        cultivating_is_work_toward_the_next_rung=some(
            lambda s: s.training is not None and s.training.kind is GrowthKind.BREAKTHROUGH
        ),
        work_toward_a_rung_is_no_attempt=every(
            lambda s: s.training is None or not s.training.attempt
        ),
    ),
    line(
        worlds.sect,
        "I sit against the well and rest for an hour",
        a_rest_trains_nothing=every(lambda s: s.training is None),
        a_rest_of_an_hour_is_timed=some(lambda s: s.kind is ActionKind.REST and lasts(s, HOUR)),
    ),
    line(
        grounded_world,
        "I ask Gennaro for a grappa and drink it at the bar",
        a_drink_in_a_world_with_no_ladder_trains_nothing=every(lambda s: s.training is None),
        a_drink_is_asked_of_the_bartender=some(at("bartender")),
    ),
    # What changes hands (C10).
    line(
        worlds.potion_stall,
        "I hand Old Hu the gold tael and take the healing draught",
        buying_gives_the_price=some(lambda s: moves(s, ExchangeKind.GIVE, "old-hu")),
        buying_takes_the_thing=some(lambda s: moves(s, ExchangeKind.TAKE, "old-hu")),
    ),
    line(
        worlds.potion_stall,
        "I snatch the draught off Old Hu's board and run for the gate",
        a_theft_takes_and_gives_nothing=lambda i: (
            any(moves(s, ExchangeKind.TAKE, "old-hu") for s in i.steps)
            and not any(moves(s, ExchangeKind.GIVE) for s in i.steps)
        ),
    ),
    line(
        worlds.farm,
        "I give Ilse ten silver pennies for the market",
        a_gift_of_money_is_counted=some(
            lambda s: any(
                e.kind is ExchangeKind.GIVE and e.money and e.amount == 10 and e.with_id == "ilse"
                for e in s.exchanges
            )
        ),
    ),
    # The everyday things of a place, the character's own home included (R2, C10). In play a
    # glass of brandy poured for a guest at home was a gift of something he didn't have.
    line(
        worlds.millers_daughter,
        "I pour Mara a cup of cider from the jug in my kitchen and ask her how the mill is doing",
        a_drink_poured_at_home_is_no_gift_and_nothing_spent=every(
            lambda s: not moves(s, ExchangeKind.GIVE) and not moves(s, ExchangeKind.SPEND)
        ),
        the_cider_in_their_own_kitchen_is_no_thing_they_carry=every(
            lambda s: UseSource.CARRIED not in sources(s, "cider")
        ),
        the_question_is_asked_of_Mara=some(at(worlds.MARA)),
    ),
    line(
        worlds.millers_daughter,
        "Mara has cut her hand on the gate. I look after it until it stops bleeding",
        tending_a_cut_carries_nothing_the_player_never_named=every(
            lambda s: (
                UseSource.CARRIED not in sources(s, "")
                and not any(u.part is SheetPart.ITEM for u in s.uses)
            )
        ),
    ),
    # A step set at a later hour begins with the wait for it (W10). In play "That evening I
    # find the widow who keeps the inn" was played at half past ten in the morning.
    line(
        worlds.farm,
        "This evening I walk down to Millbrook to hear the news",
        a_step_set_for_the_evening_waits_for_the_evening=lambda i: waits_until(i, "17:00", "21:00"),
        the_walk_to_the_village_comes_after_the_wait=lambda i: (
            len(i.steps) > 1 and i.steps[-1].destination == "village"
        ),
    ),
    # A danger is the player's to run, never a rule broken (G8, G19). In play an attempt the
    # world calls deadly without a pill was refused as against that rule.
    line(
        deadly_without_a_pill,
        "I have no pill and no time left. I sit down and force the breakthrough to Foundation "
        "Establishment anyway",
        an_attempt_the_world_calls_deadly_breaks_no_rule=every(
            lambda s: not s.facts.against_rule_ids and s.facts.world_allows
        ),
        forcing_it_without_the_pill_is_a_risky_attempt=some(
            lambda s: s.training is not None and s.training.attempt and s.training.risky
        ),
    ),
    # Goals and threads (N2, W16).
    line(
        worlds.sect,
        "I go and put my name down for the ranking tournament",
        signing_up_takes_up_the_tournament=lambda i: "tournament" in i.responds_to,
    ),
    line(
        worlds.sect,
        "I draw another bucket of water from the well",
        drawing_water_takes_up_nothing=lambda i: not i.responds_to and not i.goals,
    ),
    line(
        worlds.sect,
        "From today I mean to become the strongest swordsman this sect has ever had",
        a_lasting_aim_is_a_goal=lambda i: bool(i.goals),
    ),
    line(
        grounded_world,
        "I am done looking for whoever killed my father. From now on I only want to get rich",
        giving_up_a_goal_names_it=lambda i: "find-killer" in i.dropped_goals,
        an_aim_taken_in_its_place_is_a_goal=lambda i: bool(i.goals),
    ),
    # Theories, the past and what others do (A9, N4, A6).
    line(
        worlds.sect,
        "If time stands still for everything but me, a stone I throw should fly on at full "
        "speed once time starts again. I stop time and throw one at the wall to see",
        reasoning_about_their_power_is_a_theory=lambda i: bool(i.theories),
    ),
    line(
        worlds.sect,
        "I remember that my grandfather left me a jade sword that cuts through anything, and "
        "I take it out of my robe",
        a_past_that_hands_them_a_weapon_is_flagged=lambda i: any(
            claim.grants_power for claim in i.backstory
        ),
    ),
    line(
        worlds.sect,
        "I tell Zhao I know he stole the rations, and he bursts into tears and begs my forgiveness",
        what_someone_else_does_is_a_hope=lambda i: bool(i.outcome_claims),
        telling_Zhao_what_they_know_harms_nobody=every(lambda s: s.aim is Aim.NONE),
    ),
    # The facts a step is settled from (A2, A3, G15, N6).
    line(
        worlds.insulted,
        "I swallow my anger and say nothing",
        only_their_own_temper_stands_in_the_way=some(lambda s: s.facts.inner),
    ),
    line(
        worlds.duel,
        "I meet his charge blade to blade, strength against strength",
        a_clash_meets_him_head_on=some(lambda s: "guo" in s.target_ids and s.facts.head_on is True),
    ),
    line(
        lambda: worlds.duel(charging=False),
        "I toss my scabbard to his left and slip past him on the right while he looks at it",
        a_trick_goes_around_his_strength=some(lambda s: s.facts.head_on is False),
    ),
    line(
        worlds.among_the_pines,
        "I sit down under the pines and breathe slowly",
        nothing_in_the_way_is_nothing_to_throw_for=every(
            lambda s: s.facts.challenge in (None, Challenge.TRIVIAL)
        ),
    ),
    line(
        worlds.bridge_ambush,
        "I vault the rope and drop into the river to get away from them",
        a_drop_into_a_gorge_is_a_danger=some(lambda s: bool(s.facts.danger.strip())),
        getting_away_names_who_it_gets_away_from=some(
            lambda s: any(ref.startswith("thug-") for ref in s.facts.opposition_ids)
        ),
    ),
    line(
        worlds.troll_lunges,
        "I roll aside from the club",
        a_beast_in_a_fight_means_to_kill=some(lambda s: s.facts.foes_mean is Aim.KILL),
    ),
    # The story's own language (S10).
    line(
        worlds.one_witness,
        "Le corto el cuello a Han mientras duerme",
        Language.ES,
        in_Spanish_a_throat_cut_is_a_killing_aimed_at_Han=some(at("han", Aim.KILL)),
    ),
    line(
        worlds.foot_village,
        "Le pregunto al viejo Pan qué se cuenta por el pueblo",
        Language.ES,
        in_Spanish_asking_what_is_said_asks_for_the_talk=some(lambda s: s.facts.asks_talk),
    ),
    line(
        lesson,
        "Doy un paso y lanzo un tajo al hombro del anciano Mo",
        Language.ES,
        in_Spanish_a_lessons_blow_carries_its_terms=some(
            lambda s: "elder-mo" in s.target_ids and s.facts.terms is Terms.NO_HARM
        ),
    ),
    line(
        worlds.noodle_road,
        "Baixo caminant fins al mercat de Qinghe",
        Language.CA,
        in_Catalan_a_walk_to_the_market_town_is_a_trip_there=some(
            lambda s: s.destination == "market-town" and s.kind is ActionKind.TRAVEL
        ),
    ),
    line(
        worlds.sect,
        "Practico formes d'espasa durant dues hores",
        Language.CA,
        in_Catalan_for_two_hours_is_timed=some(lambda s: lasts(s, 2 * HOUR)),
    ),
)


def shown(read: Read) -> str:
    """A reading in short, for the detail of a line read wrong: what code decides from, without
    the words that only the telling reads. A live run's log is all that can be read of it
    afterwards (T18), and the lines are the eval's own, so nothing of a player's shows (T16)."""
    if read.intent is None:
        return f"not read ({read.failed})"
    given = _bare(read.intent.model_dump(mode="json", exclude_defaults=True))
    text = json.dumps(given, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= SHOWN_CHARS else text[: SHOWN_CHARS - 1] + "…"


def _bare(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _bare(v) for k, v in value.items() if k not in WORDS}
    if isinstance(value, list):
        return [_bare(v) for v in value]
    return value


@scenario(
    "t18.first-reading",
    suite="T18",
    title="First reading",
    requirements=("V3", "B5", "B6", "S10", "T18"),
    passes_when=(
        "The first model reads each line's fact as the engine needs it; the score is the share "
        "read right, by which a change of the form or of the model is weighed, next to what "
        "the step costs (V3, B5, B6)"
    ),
    modes=LIVE_ONLY,
    notes="No turn is played: only the interpret step runs, once a line.",
)
async def first_reading(ev: Eval) -> None:
    slow = 0.0
    for n, said in enumerate(LINES):
        story = ev.story(
            said.world(),
            seed=f"{ev.scenario.id}/{n}",
            settings=StorySettings(language=said.language),
            under_way=True,
        )
        read = await story.read(said.says)
        slow = max(slow, read.seconds)
        for name, test in said.reads:
            right = read.intent is not None and test(read.intent)
            ev.check(name, right, f"{said.says!r}: {shown(read)}")
    ev.metric("lines", len(LINES))
    ev.metric("slowest_reading_s", round(slow, 1))
