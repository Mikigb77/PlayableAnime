"""Code checks on what the model nodes propose and on the plan, before anything is narrated (C5).

Narration streams to the player as it is written (S3), so a contradiction has to be caught before
the narrator starts. Each check returns a repaired copy and the issues it found; nothing here
raises for a bad proposal, and nothing here calls a model. Model nodes propose; code decides
(CLAUDE.md rule 2).

- `check_intent`: the interpret step's proposal against the state (V3, B5).
- `check_resolution`: resolve's outcome classes and where a chained plan stops (A2, A3, R6).
- `check_plan`: the director's pick against the state and the player's settings (M1, M2, F7, N1).
- `check_update`: the narrator's proposed scene end, before `engine.apply` applies it (R3, C1).
"""

from dataclasses import dataclass

from engine.context import GoreLevel, ImageSetting, Rating, TurnContext
from engine.contracts import (
    ActionKind,
    DirectorPlan,
    Intent,
    IntentStep,
    OutcomeClass,
    PictureTrigger,
    Resolution,
    StateDelta,
    StepResolution,
    StopReason,
    SuggestionPlan,
    Theme,
)
from engine.state.cast import CharacterStatus
from engine.state.records import StepResult
from engine.state.world import WorldState
from graph.turn.types import Issue

# R6: a chained plan this long is already more than one scene can play. The steps past it are
# handed back unplayed.
MAX_STEPS = 8
# An action that fits no category still becomes a step (B5), taking a few seconds.
FALLBACK_DURATION_S = 5


@dataclass(frozen=True)
class CheckedIntent:
    intent: Intent
    issues: list[Issue]
    overflow: list[str]  # the text of steps past MAX_STEPS, which the scene hands back (R6)


def check_intent(intent: Intent, state: WorldState, action: str) -> CheckedIntent:
    """The intent with references the state can't resolve turned back into words.

    The actor is the player character unless the intent names a living character in the story.
    The interpret step never refuses (B5), so an intent with no step and no standing action
    becomes one step that carries the player's words as they are.
    """
    issues: list[Issue] = []
    intent = intent.model_copy(deep=True)
    if intent.actor_id is not None:
        actor = state.characters.get(intent.actor_id)
        if actor is None or actor.status is CharacterStatus.DEAD:
            reason = "dead" if actor is not None else "not in the story"
            issues.append(Issue("bad_actor", f"the actor is {reason}", intent.actor_id))
            intent.actor_id = None
        elif intent.actor_id == state.player_id:
            intent.actor_id = None

    known = state.characters.keys() | state.places.keys() | state.factions.keys()
    for step in intent.steps:
        unknown = [ref for ref in step.target_ids if ref not in known]
        if unknown:
            issues.append(Issue("unknown_target", "kept as words", ", ".join(unknown)))
            step.target_ids = [ref for ref in step.target_ids if ref in known]
            step.targets = list(dict.fromkeys([*step.targets, *unknown]))
        facts = step.facts
        unknown = [ref for ref in facts.opposition_ids if ref not in known]
        if unknown:
            issues.append(Issue("unknown_opposition", "kept as words", ", ".join(unknown)))
            facts.opposition_ids = [ref for ref in facts.opposition_ids if ref in known]
            facts.opposition = "; ".join(filter(None, [facts.opposition, *unknown]))

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


def check_resolution(
    resolution: Resolution, overflow: list[str] | None = None
) -> tuple[Resolution, list[Issue]]:
    """Resolve's outcome, held to A2, A3 and R6 before the steps play out.

    A2: no roll can overturn a certain or ruled-out step, so the class wins over a result that
    disagrees with it. A3: a contested or long-shot step is decided by its roll, so the roll's
    result wins. R6: a chained plan stops at its first step that doesn't cleanly succeed, and the
    steps after it, with any `overflow` past `MAX_STEPS`, are listed as unplayed, so the narrator
    hands the scene back.
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
        if later and (declared or not step.clean_success):
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
        if step.result is settled and step.roll is None:
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
    return StopReason.FAILED


def check_update(delta: StateDelta, state: WorldState) -> tuple[StateDelta, list[Issue]]:
    """The narrator's scene end, before `engine.apply.apply_delta` applies the rest with C1.

    A scene ends on a moment the next one starts from (R3), so a blank one keeps the last. The
    dead can't be present (C1), and the rolling summary is never blanked.
    """
    issues: list[Issue] = []
    delta = delta.model_copy(deep=True)
    end = delta.scene_end
    if end is not None:
        end.ended_on = end.ended_on.strip()
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


def check_plan(
    state: WorldState, plan: DirectorPlan, ctx: TurnContext
) -> tuple[DirectorPlan, list[Issue]]:
    """The director's pick, held to the state and the player's settings.

    A picture needs pictures switched on (M2) and a subject that exists, and a dead character is
    drawn only for their death. An event may only start themes the player switched on and the
    rating allows (F7, F2), and may only point at threads, clocks and events that exist.
    Callbacks pull in only dormant or open threads (N1). Suggestions follow the player's setting
    (S2).
    """
    issues: list[Issue] = []
    plan = plan.model_copy(deep=True)

    picture = plan.picture
    if picture is not None:
        reason = _picture_problem(state, picture.subject_id, picture.trigger, ctx)
        if reason is not None:
            issues.append(Issue("picture_dropped", reason, picture.subject_id))
            plan.picture = None

    event = plan.event
    if event is not None:
        refused = [theme for theme in event.themes if not _theme_allowed(theme, ctx)]
        if refused:
            names = ", ".join(sorted(theme.value for theme in refused))
            issues.append(Issue("event_dropped", f"themes switched off: {names}", event.title))
            plan.event = None
        else:
            if event.thread_id is not None and event.thread_id not in state.threads:
                issues.append(Issue("unknown_thread", "event's thread cleared", event.thread_id))
                event.thread_id = None
            known_sources = state.clocks.keys() | state.threads.keys() | state.pending_events.keys()
            if event.source_id is not None and event.source_id not in known_sources:
                issues.append(Issue("unknown_source", "event's source cleared", event.source_id))
                event.source_id = None

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
        if character.status is CharacterStatus.DEAD and trigger is not PictureTrigger.DEATH:
            return "the subject is dead"
        return None
    if subject_id in state.places or subject_id in state.deeds:
        return None
    return "the subject isn't in the story"


def _theme_allowed(theme: Theme, ctx: TurnContext) -> bool:
    prefs = ctx.content_prefs
    if theme is Theme.ROMANCE:
        return prefs.romance
    if theme is Theme.DARK:
        return prefs.dark_themes
    if theme is Theme.GORE:
        return ctx.rating is Rating.MATURE and prefs.gore is not GoreLevel.LOW
    return True
