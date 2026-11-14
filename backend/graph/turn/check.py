"""Code checks on what the model nodes propose and on the plan, before anything is narrated (C5).

Narration streams to the player as it is written (S3), so a contradiction has to be caught before
the narrator starts. Each check returns a repaired copy and the issues it found; nothing here
raises for a bad proposal, and nothing here calls a model. Model nodes propose; code decides
(CLAUDE.md rule 2).

- `check_intent`: the interpret step's proposal against the state (V3, B5, W10, N2, N6).
- `doubtful`: whether that reading would do something that can't be taken back on the model's
  word alone, so it is read once more before code decides (B8, W1).
- `check_resolution`: resolve's outcome classes and where a chained plan stops (A2, A3, R6).
- `check_plan`: the director's pick against the state and the player's settings (M1, M2, F7, N1).
- `check_update`: the narrator's proposed scene end, before `engine.apply` applies it (R3, C1).
- `check_told`: whether a scene the player acted in told their action before its outcome (R1).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from engine import injuries, limits, naming, path, possessions
from engine.context import ImageSetting, Language, TurnContext
from engine.contracts import (
    ActionKind,
    DirectorPlan,
    GrowthKind,
    Intent,
    IntentStep,
    ItemChange,
    NewRung,
    OutcomeClass,
    PictureTrigger,
    Resolution,
    SheetPart,
    StateDelta,
    StepFacts,
    StepResolution,
    StopReason,
    SuggestionPlan,
    UseSource,
)
from engine.director.themes import allowed_themes, fits
from engine.invariants import is_real_name
from engine.labels import only_the_clock
from engine.resolve import bouts, checks
from engine.resolve.powers import growth, sensing
from engine.state.cast import CharacterStatus
from engine.state.records import GoalStatus, LeadStatus, RollRecord, StepResult, Transfer
from engine.state.world import WorldState
from engine.text import stems
from engine.timekeeping import DURATION_BOUNDS, names_a_span, parse_clock
from engine.world.geography import scene_ids
from graph.turn.form import Above
from graph.turn.outputs import NarratorOutput
from graph.turn.types import Issue

# R6: a chained plan this long is already more than one scene can play. The steps past it are
# handed back unplayed.
MAX_STEPS = 8
# An action that fits no category still becomes a step (B5), taking a few seconds.
FALLBACK_DURATION_S = 5
# W10: the kinds of stretch that become a time skip when the player gave one more time than its
# kind can last: "I train here for a year" read as work would stop at eighteen hours.
STRETCHES = (
    ActionKind.REST,
    ActionKind.WORK,
    ActionKind.TASK,
    ActionKind.WAIT,
    ActionKind.OBSERVE,
)
# M1: the only pictures a dead character can be the subject of.
LAST_PICTURES = (PictureTrigger.DEATH, PictureTrigger.DECISIVE_BLOW)
# G12: the issue code for a real person or organisation left out of the narrator's update.
REAL_ENTITY = "real_entity"
# N6, A8: an edge or hindrance about an injury the record doesn't hold, left out.
UNRECORDED_HARM = "unrecorded_harm"
# R3: the issue code for a scene end that gave only the date or the hour.
CLOCK_SCENE_END = "clock_scene_end"
# G18: the update listed a rung above a ladder's top that the scene's words never named.
RUNG_UNTOLD = "rung_untold"
# C1: someone new the update left without a name took the one the scene calls them by.
NAMED_BY_SCENE = "named_by_scene"
# G18: the longest answer to the form's question about the rung above an open top
# (`NarratorOutput.rung_above`) that is read as a rung's name. A sentence is not one.
MAX_RUNG_NAME = 60
# B8: the issue code for a turn the larger model read again, and what its first reading would
# have done that can't be taken back (W1).
READ_AGAIN = "read_again"
BEYOND_TERMS = "beyond_terms"
BREAKTHROUGH = "breakthrough"
# C10, R2: something the reading filed as the character's own that they don't hold and the
# player's words never named: a prop the reading added, so it is a thing of the place.
PROP_ADDED = "prop_added"


@dataclass(frozen=True)
class CheckedIntent:
    intent: Intent
    issues: list[Issue]
    overflow: list[str]  # the text of steps past MAX_STEPS, which the scene hands back (R6)


def check_intent(
    intent: Intent, state: WorldState, action: str, language: Language = Language.EN
) -> CheckedIntent:
    """The intent with references the state can't resolve turned back into words.

    The actor is always the player character: the player plays their own character and can't
    make anyone else act (A6), so words that have someone else act are the character's order or
    hope. The interpret step never refuses (B5), so an intent with no step and no standing action
    becomes one step that carries the player's words as they are. An edge or hindrance that
    leans on an injury the record doesn't hold is left out (N6, `engine.injuries`). Hiding or
    showing strength is a step of its own (G20, `_shows_apart`). A step whose reading left out
    who it is aimed at finds them where the player's words point (V3, W1, `_aimed`). A stretch
    the player timed for longer than its kind can last is a time skip (W10): the reading marks
    it `timed`, and the player's own words count beside that mark when they name a span of
    time, in English or in the story's `language` (`timekeeping.names_a_span`). Something the
    reading says the character carries, which they don't hold and the player never named, is
    the reading's own prop and no claim of the player's (C10, R2, `_props`).
    """
    issues: list[Issue] = []
    intent = intent.model_copy(deep=True)
    if intent.actor_id is not None and intent.actor_id != state.player_id:
        issues.append(
            Issue("not_the_player", _actor_reason(state, intent.actor_id), intent.actor_id)
        )
    intent.actor_id = None

    known = state.characters.keys() | state.places.keys() | state.factions.keys()
    for step in intent.steps:
        unknown = [ref for ref in step.target_ids if ref not in known]
        if unknown:
            issues.append(Issue("unknown_target", "kept as words", ", ".join(unknown)))
            step.target_ids = [ref for ref in step.target_ids if ref in known]
            step.targets = list(dict.fromkeys([*step.targets, *unknown]))
        if step.until is not None and parse_clock(step.until) is None:
            # W10: a time that isn't a time of day leaves the proposed seconds to stand.
            if step.until.strip():
                issues.append(Issue("bad_until", "not a time of day, so the seconds stand"))
            step.until = None
        if (
            step.kind in STRETCHES
            and step.proposed_duration_s > DURATION_BOUNDS[step.kind][1]
            and (step.timed or names_a_span(action, language))
        ):
            # W10: the player said how long, so the time stands and the kind gives way. Their
            # own words count beside the reading's mark: the real model left it off "I spend
            # the next week courting Mara", read as a week of work, and the week stopped at
            # eighteen hours (2026-11-13).
            issues.append(Issue("long_stretch", "longer than its kind lasts, so a time skip"))
            step.kind = ActionKind.TIME_SKIP
        facts = step.facts
        unknown = [ref for ref in facts.opposition_ids if ref not in known]
        if unknown:
            issues.append(Issue("unknown_opposition", "kept as words", ", ".join(unknown)))
            facts.opposition_ids = [ref for ref in facts.opposition_ids if ref in known]
            facts.opposition = "; ".join(filter(None, [facts.opposition, *unknown]))
        _aimed(step, state, issues, action if len(intent.steps) == 1 else "")
        _props(step, state, action, issues)
        # N6, A8: an edge or hindrance that leans on an injury the record doesn't hold, such as
        # an "old wound" the character never had, is left out of the odds and the scene.
        step.facts, dropped = injuries.unrecorded_harm(state, state.player, step)
        if dropped:
            issues.append(Issue(UNRECORDED_HARM, f"{dropped} left out", str(step.text)))

    # W16, N1, N2: only open threads the player knows and leads still on offer can be taken up.
    taken_up = []
    for ref in dict.fromkeys(intent.responds_to):
        thread, lead = state.threads.get(ref), state.leads.get(ref)
        if thread is not None and not thread.status.closed and state.player_id in thread.known_by:
            taken_up.append(ref)
        elif lead is not None and lead.status is LeadStatus.OPEN:
            taken_up.append(ref)
        else:
            issues.append(Issue("unknown_response", "not an open thread or lead", ref))
    intent.responds_to = taken_up

    # N2: only the character's active goals can be dropped.
    dropped = []
    for ref in dict.fromkeys(intent.dropped_goals):
        goal = state.goals.get(ref)
        if goal is not None and goal.status is GoalStatus.ACTIVE:
            dropped.append(ref)
        else:
            issues.append(Issue("unknown_goal", "not an active goal", ref))
    intent.dropped_goals = dropped

    intent.steps = _shows_apart(intent.steps, state, issues)

    overflow: list[str] = []
    if len(intent.steps) > MAX_STEPS:
        overflow = [step.text for step in intent.steps[MAX_STEPS:]]
        issues.append(Issue("too_many_steps", f"the last {len(overflow)} are handed back"))
        intent.steps = intent.steps[:MAX_STEPS]

    if not intent.steps and intent.standing is None:
        issues.append(Issue("no_step", "the action became one step as written"))
        text = action.strip()
        intent.steps = [
            IntentStep(
                text=text,
                verb="act",
                kind=ActionKind.INSTANT,
                proposed_duration_s=FALLBACK_DURATION_S,
            )
        ]
        intent.summary = intent.summary or text
    return CheckedIntent(intent=intent, issues=issues, overflow=overflow)


def doubtful(intent: Intent, state: WorldState) -> str | None:
    """What a reading would do that can't be taken back and rests on the model's word alone, or
    None: such a turn is read once more, by the larger model, before code decides (B8).

    Two things so far. A blow the reading says is meant to go beyond the terms of a bout (W1),
    which ends the bout as an attack on a friend, for good. Read on the real model on
    2026-11-12, one plain lesson blow in 36 came back that way, and every blow after it in that
    story was an attack on the teacher. A fight already in earnest has no terms left to break,
    and a blow the terms allow breaks nothing, whatever the reading said of it
    (`engine.resolve.bouts`). And an attempt to break through at the peak of a rank (G19), which
    is thrown for: neither a climb nor what a miss costs can be taken back, and an attempt was
    once read into "you propose a short rest". Before the peak the same reading is only
    training, so it is not read again."""
    if _ends_a_bout(intent, state):
        return BEYOND_TERMS
    for step in intent.steps:
        training = step.training
        if training is None or training.kind is not GrowthKind.BREAKTHROUGH:
            continue
        if training.attempt and growth.at_peak(state, state.player, step):
            return BREAKTHROUGH
    return None


def _ends_a_bout(intent: Intent, state: WorldState) -> bool:
    """W1. Whether a blow of the reading is meant to go beyond the terms of a bout that is on,
    or that the blow itself agrees."""
    encounter = state.scene.encounter
    bout = encounter.bout if encounter is not None else None
    if bout is None and encounter is not None and encounter.in_earnest:
        return False
    for step in intent.steps:
        facts = step.facts
        if not facts.breaks_terms or not bouts.is_blow(step):
            continue
        terms = facts.terms if bout is None else bouts.milder(bout.terms, facts.terms)
        if terms is not None and not bouts.allows(terms, bouts.meant(step)):
            return True
    return False


def _aimed(step: IntentStep, state: WorldState, issues: list[Issue], action: str = "") -> None:
    """V3, W1, in place. Who a step is aimed at, where the reading left their id out. The real
    model often names nobody under target_ids: "I cut Han's throat" was read as a killing aimed
    at no one (2026-11-11), so nobody died on record while the scene told a death.

    Words under `targets` that are exactly the name of one person in the scene, or else of one
    person the player character knows, become that person. A step that means harm and still
    aims at nothing on record, with no stranger to make real, is aimed at the one person of the
    scene its own words name (`action` is the player's words, when the whole action is this
    step); else at those the reading put in its way, as in a bout (`bouts.against`); else at
    the one they are fighting. Past that it is aimed at nobody: code never picks a victim the
    player's words don't point at."""
    you = state.player_id
    people = state.characters
    scene = [i for i in scene_ids(state) if i != you and i in people and people[i].alive]
    known = [
        c.id for c in state.npcs() if c.id not in scene and (you in c.known_by or you in c.met_by)
    ]
    words = []
    for said in step.targets:
        match = naming.called(state, said, scene) or naming.called(state, said, known)
        if match is None:
            words.append(said)
        elif match not in step.target_ids:
            step.target_ids.append(match)
            issues.append(Issue("target_by_name", "the words name them", match))
    step.targets = words
    if not step.aim.harmful or step.stranger is not None or step.target_ids:
        return
    named = naming.named_in(state, [step.text, *step.targets, action], scene)
    in_way = [i for i in dict.fromkeys(step.facts.opposition_ids) if i != you and i in people]
    encounter = state.scene.encounter
    fought = [i for i in (encounter.opponent_ids if encounter else []) if i in scene]
    if len(named) == 1:
        found, how = named, "the step's words name them"
    elif in_way:
        found, how = in_way, "they stand in its way"
    elif len(fought) == 1:
        found, how = fought, "they are who the character is fighting"
    else:
        issues.append(Issue("no_target", "a step that means harm is aimed at nobody"))
        return
    step.target_ids = list(found)
    issues.append(Issue("target_found", how, ", ".join(found)))


def _props(step: IntentStep, state: WorldState, action: str, issues: list[Issue]) -> None:
    """C10, R2, in place. The belongings are the truth about what the player says their
    character has: "I drink my healing draught" with no draught on the sheet is refused. A
    prop the reading added by itself is no such claim. The real model read "I nurse her until
    she is well" as a step that uses "herbs of the region" the character carries, and the step
    was ruled out for herbs the player never mentioned (2026-11-14).

    So something a step files as the character's own (an item it draws on, or a thing a beat
    carries) that they don't hold in any way (`checks.not_theirs`), and that no word of the
    player's names, is taken for what it is: an item the step draws on is left out, and a
    thing a beat uses is one of the place, there or not as a place like this would have it
    (R2). What the player's own words name stays under C10."""
    said = stems(action)
    you = state.player

    def added(words: str, ref: str | None = None) -> bool:
        return not (stems(words) & said) and checks.not_theirs(state, you, words, ref)

    kept = [u for u in step.uses if not (u.part is SheetPart.ITEM and added(u.ref))]
    for use in step.uses:
        if use not in kept:
            issues.append(Issue(PROP_ADDED, "left out: the player never named it", use.ref))
    step.uses = kept
    for beat in step.beats:
        for use in beat.uses:
            if use.source is UseSource.CARRIED and added(use.thing, use.ref):
                use.source = UseSource.NEW
                issues.append(Issue(PROP_ADDED, "a thing of the place", use.thing))


def _shows_apart(
    steps: list[IntentStep], state: WorldState, issues: list[Issue]
) -> list[IntentStep]:
    """G20. Hiding one's strength or letting it show is a step of its own, which code settles
    for certain. Read into a step that also strikes someone, trains or builds on a talent, it
    would settle that too, with no throw: so the show comes first, as its own step, and the
    rest of the step plays as what it is. A show that names a ladder the world doesn't have is
    left out, and so is one that has nothing to change (no such strength, or nothing hidden to
    show) on a step that does something else."""
    apart: list[IntentStep] = []
    for step in steps:
        if step.show_strength is None:
            apart.append(step)
            continue
        # Showing the very rung they stand on is showing their true strength.
        show = sensing.meant(state.player, step.show_strength)
        step = step.model_copy(update={"show_strength": show})
        if state.bible.ladder(show.ladder_id) is None:
            issues.append(Issue("unknown_ladder", "the show of strength is left out"))
            apart.append(step.model_copy(update={"show_strength": None}))
            continue
        busy = step.aim.harmful or step.training is not None or step.bridge is not None
        if not busy:
            apart.append(step)
            continue
        mine = next((p for p in state.player.sheet.ladders if p.ladder_id == show.ladder_id), None)
        changes = mine is not None and (show.shown_rung is not None or mine.shown_rung is not None)
        if changes:
            issues.append(Issue("show_apart", "the show of strength became its own step"))
            apart.append(
                IntentStep(
                    text=step.text,
                    verb="hide" if show.shown_rung is not None else "reveal",
                    kind=ActionKind.INSTANT,
                    proposed_duration_s=1,
                    show_strength=show,
                    # W2: a reveal before a crowd is as public as the blow that follows it.
                    facts=StepFacts(crowd=step.facts.crowd),
                )
            )
        else:
            issues.append(Issue("idle_show", "the show of strength is left out"))
        apart.append(step.model_copy(update={"show_strength": None}))
    return apart


def _actor_reason(state: WorldState, actor_id: str) -> str:
    actor = state.characters.get(actor_id)
    if actor is None:
        return "the actor is not in the story, so the player character acts"
    if actor.status is CharacterStatus.DEAD:
        return "the actor is dead, so the player character acts"
    return "the player plays only their own character (A6)"


def check_resolution(
    resolution: Resolution, overflow: list[str] | None = None
) -> tuple[Resolution, list[Issue]]:
    """Resolve's outcome, held to A2, A3 and R6 before the steps play out.

    A2: no roll can overturn a certain or ruled-out step, so the class wins over a result that
    disagrees with it. A3: a contested or long-shot step is decided by its roll, so the roll's
    result wins. R6: a chained plan stops at its first step that doesn't cleanly succeed, or
    after which something struck back and hurt the player character (N6), and the steps after
    it, with any `overflow` past `MAX_STEPS`, are listed as unplayed, so the narrator hands the
    scene back.
    """
    issues: list[Issue] = []
    steps: list[StepResolution] = []
    unplayed = list(resolution.unplayed)
    stopped_at = resolution.stopped_at_step
    stop_reason = resolution.stop_reason

    for position, original in enumerate(resolution.steps):
        step, found = _check_step(original)
        issues += found
        steps.append(step)

        later = resolution.steps[position + 1 :]
        declared = step.index == resolution.stopped_at_step
        if later and (declared or not step.clean_success or step.hurt_by_peril):
            issues.append(
                Issue("plan_not_stopped", "the steps after it were not played", str(step.index))
            )
            stopped_at = step.index
            if not declared:
                stop_reason = _stop_reason(step)
            unplayed = [*(s.text for s in later if s.text not in unplayed), *unplayed]
            break

    if stopped_at is not None and stopped_at not in {s.index for s in steps}:
        issues.append(Issue("bad_stop", "the stop names no played step", str(stopped_at)))
        stopped_at, stop_reason = None, None

    repaired = resolution.model_copy(
        update={
            "steps": steps,
            "stopped_at_step": stopped_at,
            "stop_reason": stop_reason,
            "unplayed": [*unplayed, *(overflow or [])],
        }
    )
    return repaired, issues


def _check_step(step: StepResolution) -> tuple[StepResolution, list[Issue]]:
    settled = _settled_result(step.outcome_class)
    if settled is not None:
        if step.result is settled and (step.roll is None or _time_only(step.roll, settled)):
            return step, []
        issue = Issue(
            "class_result_mismatch",
            f"a {step.outcome_class} step can't be rolled or end in {step.result}",
            str(step.index),
        )
        return step.model_copy(update={"result": settled, "roll": None}), [issue]
    if step.roll is None:
        return step, [
            Issue("unrolled", f"a {step.outcome_class} step has no roll", str(step.index))
        ]
    if step.roll.result is not step.result:
        issue = Issue("roll_result_mismatch", "the roll decides", str(step.index))
        return step.model_copy(update={"result": step.roll.result}), [issue]
    return step, []


def _time_only(roll: RollRecord, settled: StepResult) -> bool:
    """W10, A3. A roll that only picked how long a settled step took: certain odds, the settled
    result, and the time it picked. Its seed is kept so the time replays."""
    return roll.odds == 1 and roll.result is settled and roll.duration_s is not None


def _settled_result(outcome_class: OutcomeClass) -> StepResult | None:
    if outcome_class is OutcomeClass.CERTAIN:
        return StepResult.SUCCESS
    if outcome_class is OutcomeClass.RULED_OUT:
        return StepResult.FAILURE
    return None


def _stop_reason(step: StepResolution) -> StopReason:
    """Why a plan stops at a step that didn't cleanly succeed. An interruption is `play_out`'s
    to record, since events fire only as the steps play out (W10)."""
    if step.outcome_class is OutcomeClass.RULED_OUT:
        return StopReason.RULED_OUT
    if step.result is StepResult.PARTIAL:
        return StopReason.PARTIAL
    if step.result is StepResult.SUCCESS and step.hurt_by_peril:
        return StopReason.STRUCK  # it worked, but something struck back and hurt them (N6)
    return StopReason.FAILED


def with_rung_above(delta: StateDelta, name: str, above: Above | None) -> StateDelta:
    """G18. The update with the rung the narrator named where its form asked for one above an
    open top (`NarratorOutput.rung_above`, `form.narrator_form`): one of its `rungs`, on the
    ladder the form asked about, unless the update lists a rung of that name already. An answer
    that is blank, isn't a name, or that no form asked for changes nothing. Whether the rung
    holds is still `check_update`'s to say, by the scene's own words, and then the engine's."""
    name = name.strip()
    if above is None or not is_real_name(name) or len(name) > MAX_RUNG_NAME:
        return delta
    said = limits.normalize(name)
    if any(limits.normalize(rung.name) == said for rung in delta.rungs):
        return delta
    rung = NewRung(ladder_id=above.ladder_id, name=name)
    return delta.model_copy(update={"rungs": [*delta.rungs, rung]})


def called_in(told: str, character_id: str) -> str | None:
    """C1. The name a scene gives someone whose id is made of that name's words: the words in
    a row, as the scene writes them, whatever their case or accents ("elder-song" finds "Elder
    Song", "elder_nunez" finds "Elder Núñez"). Where the scene writes them as a name, its
    first word and its last with a capital, that is the name ("Lin de la Cruz"); else each
    word takes a capital ("the envoy" gives "The Envoy"). None where the scene never says
    them."""
    wanted = limits.normalize(character_id).split()
    words = re.findall(r"[^\W_]+", told)
    folded = [limits.normalize(word) for word in words]
    runs = [
        words[start : start + len(wanted)]
        for start in range(len(words) - len(wanted) + 1)
        if wanted and folded[start : start + len(wanted)] == wanted
    ]
    if not runs:
        return None
    as_written = next((run for run in runs if run[0][:1].isupper() and run[-1][:1].isupper()), None)
    if as_written is not None:
        return " ".join(as_written)
    return " ".join(word[:1].upper() + word[1:] for word in runs[0])


def _named_by_scene(
    delta: StateDelta, state: WorldState, told: str
) -> tuple[StateDelta, list[Issue]]:
    """C1. Someone new the update leaves without a name takes the name the scene calls them by,
    where their id is made of its words (`called_in`). The narrator's form doesn't require a
    name, the model answers only what a form requires as often as not, and in a live story an
    elder the scene named throughout was refused for want of one, so the record never had him
    (2026-11-13). Anyone the scene doesn't name that way stays nameless and is refused as
    before (`engine.apply`), and so does an id whose words are what someone on record goes by:
    that is their id written another way, not someone new."""
    taken = {name for known in state.characters for name in naming.names(state, known)}
    issues, characters = [], []
    for change in delta.characters:
        if change.id not in state.characters and not is_real_name(change.name):
            name = called_in(told, change.id)
            if name is not None and is_real_name(name) and limits.normalize(name) not in taken:
                issues.append(Issue(NAMED_BY_SCENE, "the scene's name for them", change.id))
                change = change.model_copy(update={"name": name})
        characters.append(change)
    if not issues:
        return delta, issues
    return delta.model_copy(update={"characters": characters}), issues


def check_update(
    delta: StateDelta,
    state: WorldState,
    moved: Sequence[Transfer] = (),
    told: str = "",
    *,
    looks: bool = True,
) -> tuple[StateDelta, list[Issue]]:
    """The narrator's scene end, before `engine.apply.apply_delta` applies the rest with C1.

    A scene ends on a moment the next one starts from (R3), so a blank one keeps the last. One
    that gives only the date or the hour ("Day 1, morning, 07:00") tells the next scene nothing
    of who is where doing what, so the scene's own last sentence (`told` is its text) stands in
    for it. The
    dead can't be present (C1), and the rolling summary is never blanked. A new character or
    faction named after a real person or organisation is left out, and a known one keeps its
    name (G12); someone new the update left nameless is first given the name the scene calls
    them by (`_named_by_scene`), so that name is held to the same. What the engine already
    moved this turn (`moved`, the transfers its steps and
    events made, C10) is left out, so a payment told in the scene is never made twice. A rung
    above a ladder's top that the scene's own words never named is left out too (G18).

    `looks` false says the scene was written without the player character's appearance (R9).
    An appearance it writes for them all the same was made up, so it is left out and the kept
    one stands (C9); a lasting change it names is still added to the kept one (`engine.looks`).
    """
    delta, issues = _named_by_scene(delta, state, told)
    delta, hits = limits.strip_real_entities(delta, state)
    issues += [Issue(REAL_ENTITY, hit.detail, hit.subject) for hit in hits]
    if not looks:
        characters = []
        for change in delta.characters:
            if change.id == state.player_id and change.appearance is not None:
                issues.append(Issue(LOOKS_UNSEEN, "kept the appearance on record", change.id))
                change = change.model_copy(update={"appearance": None})
            characters.append(change)
        delta = delta.model_copy(update={"characters": characters})
    if moved and delta.items:
        kept = [change for change in delta.items if not _already_moved(change, moved)]
        if len(kept) < len(delta.items):
            issues.append(Issue("move_recorded", "the step already moved it"))
            delta = delta.model_copy(update={"items": kept})
    if delta.rungs:
        # G18, G7: a rung above a ladder's top is the story's once its own words name it, so
        # the record never holds a rung the player didn't read of.
        named = [rung for rung in delta.rungs if path.named(told, rung.name)]
        if len(named) < len(delta.rungs):
            issues.append(Issue(RUNG_UNTOLD, "the scene never named it"))
            delta = delta.model_copy(update={"rungs": named})
    end = delta.scene_end
    if end is not None:
        end.ended_on = end.ended_on.strip()
        if only_the_clock(state.bible.calendar, state.world_s, end.ended_on):
            issues.append(Issue(CLOCK_SCENE_END, "the scene's end gave only the time"))
            end.ended_on = _last_sentence(told)
        if not end.ended_on:
            issues.append(Issue("blank_scene_end", "kept the last scene's ending"))
            end.ended_on = state.scene.ended_on
        present = []
        for character_id in dict.fromkeys(end.present_ids):
            character = state.characters.get(character_id)
            if character is not None and character.status is CharacterStatus.DEAD:
                issues.append(Issue("dead_present", "left out of the scene", character_id))
            else:
                # Someone new in this same delta is added first; apply_delta drops ids that
                # still name nobody.
                present.append(character_id)
        end.present_ids = present
    if delta.summary is not None and not delta.summary.strip():
        delta.summary = None
    return delta, issues


# R3: how much of a scene's last sentence stands in for a scene end that gave only the time.
LAST_SENTENCE_CHARS = 300


def _last_sentence(told: str) -> str:
    """The last sentence of a scene's text, or the end of it when nothing ends a sentence in
    it. Blank for a scene with no text."""
    text = " ".join(told.split())
    if not text:
        return ""
    sentences = [s for s in re.split(r"(?<=[.!?…])[\"'”’»)]*\s+", text) if s.strip()]
    return sentences[-1].strip()[-LAST_SENTENCE_CHARS:]


# R1: the issue code for a scene that skipped the player's action and opened on what came of it.
ACTION_UNTOLD = "action_untold"
# R9: the issue code for an appearance written for the player character by a scene that was
# never handed theirs.
LOOKS_UNSEEN = "looks_unseen"


def check_told(told: NarratorOutput, intent: Intent | None) -> list[Issue]:
    """R1. A scene the player acted in opens on the character doing it, in its own field, so
    code can see one that skipped straight to what came of it. The scene has already streamed
    (S3), so this only reports it, for the logs and the evals (T5, T18)."""
    if intent is None or told.action.strip():
        return []
    return [Issue(ACTION_UNTOLD, "the scene opened on the outcome, not the action")]


def _already_moved(change: ItemChange, moved: Sequence[Transfer]) -> bool:
    """Whether the narrator's change retells one the engine made: the same sides, however the
    world is spelled, no more of it, and money for money or the same thing."""
    sides = (possessions.side(change.from_id), possessions.side(change.to_id))
    amount = possessions.count(change.name, change.quantity)
    for done in moved:
        if sides != (done.from_id, done.to_id) or amount > done.quantity:
            continue
        if done.money:
            if change.money or possessions.is_money(change.name, done.currency):
                return True
            continue
        if change.money:
            continue
        if change.item_id and change.item_id == done.item_id:
            return True
        if possessions.same_thing(change.name, done.name):
            return True
    return False


def check_plan(
    state: WorldState, plan: DirectorPlan, ctx: TurnContext
) -> tuple[DirectorPlan, list[Issue]]:
    """The director's pick, held to the state and the player's settings.

    A picture needs pictures switched on (M2) and a subject that exists, and a dead character is
    drawn only for their death or the blow that ended their fight. An event, and anything told
    as having happened, may only carry themes the director may start: switched on, within the
    rating, and romance only for an adult player character (F7, F2, F3). An event may only point
    at threads, clocks, events, characters and factions that exist. Callbacks pull in only
    dormant or open threads (N1). Suggestions follow the player's setting (S2).
    """
    issues: list[Issue] = []
    plan = plan.model_copy(deep=True)

    picture = plan.picture
    if picture is not None:
        reason = _picture_problem(state, picture.subject_id, picture.trigger, ctx)
        if reason is not None:
            issues.append(Issue("picture_dropped", reason, picture.subject_id))
            plan.picture = None

    allowed = allowed_themes(state, ctx)
    event = plan.event
    if event is not None:
        refused = [theme for theme in event.themes if theme not in allowed]
        if refused:
            names = ", ".join(sorted(theme.value for theme in refused))
            issues.append(Issue("event_dropped", f"themes switched off: {names}", event.title))
            plan.event = None
        else:
            if event.thread_id is not None and event.thread_id not in state.threads:
                issues.append(Issue("unknown_thread", "event's thread cleared", event.thread_id))
                event.thread_id = None
            known_sources = (
                state.clocks.keys()
                | state.threads.keys()
                | state.pending_events.keys()
                | state.characters.keys()
                | state.factions.keys()
            )
            if event.source_id is not None and event.source_id not in known_sources:
                issues.append(Issue("unknown_source", "event's source cleared", event.source_id))
                event.source_id = None

    happenings = []
    for happening in plan.happenings:
        if fits(happening.themes, allowed):
            happenings.append(happening)
        else:
            issues.append(Issue("happening_dropped", "a theme is switched off", happening.title))
    plan.happenings = happenings

    callbacks = []
    for thread_id in plan.callbacks:
        thread = state.threads.get(thread_id)
        if thread is None or thread.status.closed:
            issues.append(Issue("callback_dropped", "not an open or dormant thread", thread_id))
        else:
            callbacks.append(thread_id)
    plan.callbacks = list(dict.fromkeys(callbacks))

    if not ctx.settings.suggestions and plan.suggestions.count:
        plan.suggestions = SuggestionPlan(count=0, kinds=[])
    return plan, issues


def _picture_problem(
    state: WorldState, subject_id: str | None, trigger: PictureTrigger, ctx: TurnContext
) -> str | None:
    if ctx.settings.images is ImageSetting.OFF and trigger is not PictureTrigger.COVER:
        return "pictures are switched off"
    if subject_id is None:
        return None
    character = state.characters.get(subject_id)
    if character is not None:
        if character.status is CharacterStatus.DEAD and trigger not in LAST_PICTURES:
            return "the subject is dead"
        return None
    if subject_id in state.places or subject_id in state.deeds or subject_id in state.threads:
        return None
    return "the subject isn't in the story"
