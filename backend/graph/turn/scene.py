"""The scene a turn saves, in API.md's shape, built in code from what the turn decided.

The narrator writes the text, the suggestions and the picture prompt. Everything else on the
scene comes from the engine: the steps with their class, reason and roll (A2, A8), the beats
that found something new or came up empty (R2), the chain (A9), where a plan stopped (R6), the
event (W16), the picture code planned (M1) and the time.
"""

from engine.contracts import (
    BeatVerdict,
    DirectorPlan,
    PictureDecision,
    PictureKind,
    Resolution,
    StepResolution,
)
from engine.looks import place_looks
from engine.state.records import RollRecord
from engine.state.world import WorldState
from graph.turn.outputs import NarratorOutput
from graph.turn.types import (
    BeatDetail,
    Choice,
    LinkDetail,
    NarrationMode,
    RollDetail,
    SceneDetails,
    SceneDraft,
    SceneEvent,
    ScenePicture,
    StepDetail,
    TurnInput,
    TurnKind,
)

MAX_CHOICE_CHARS = 120
_STANDING_WORDS = {"wait", "observe"}


def scene_draft(
    turn: TurnInput,
    *,
    before: WorldState,
    after: WorldState,
    resolution: Resolution,
    plan: DirectorPlan,
    narration: NarratorOutput,
    mode: NarrationMode,
) -> SceneDraft:
    """`before` is the state the scene started from; `after` the state once it played out."""
    elapsed = after.world_s - before.world_s
    lived = after.player.personal_s(after.world_s) - before.player.personal_s(before.world_s)
    return SceneDraft(
        turn=turn.ctx.turn,
        kind=turn.kind,
        player_action=_player_action(turn),
        narration=narration.narration.strip(),
        choices=choices(narration, plan.suggestions.count) if mode != "template" else [],
        details=details(resolution),
        event=SceneEvent(size=plan.event.size, title=plan.event.title) if plan.event else None,
        picture=picture(after, plan.picture, narration.image_prompt, mode),
        timeline_id=before.timeline_id,
        world_start_s=before.world_s,
        world_end_s=after.world_s,
        personal_elapsed_s=lived if lived != elapsed else None,
        narration_mode=mode,
    )


def _player_action(turn: TurnInput) -> str | None:
    if turn.kind is TurnKind.STANDING and turn.standing is not None:
        return turn.standing.value
    return turn.action.strip() if turn.action else None


def choices(narration: NarratorOutput, count: int) -> list[Choice]:
    """S2: at most the number the director asked for, never wait or observe (always offered),
    each label short and unique."""
    picked: list[Choice] = []
    seen: set[str] = set()
    if count <= 0:
        return picked
    for suggestion in narration.suggestions:
        label = " ".join(suggestion.label.split())[:MAX_CHOICE_CHARS]
        key = label.casefold().rstrip(".!")
        if not label or key in seen or key in _STANDING_WORDS:
            continue
        seen.add(key)
        picked.append(Choice(id=f"c{len(picked) + 1}", label=label, kind=suggestion.kind))
        if len(picked) >= count:
            break
    return picked


def details(resolution: Resolution) -> SceneDetails:
    """API.md's `SceneDetails`, so the player can see why (A8)."""
    links = [link for step in resolution.steps for link in step.chain]
    return SceneDetails(
        steps=[_step_detail(step) for step in resolution.steps],
        chain=[
            LinkDetail(link=link.text, outcome_class=link.outcome_class, reason=link.reason)
            for link in links
        ]
        or None,
        stopped_at_step=resolution.stopped_at_step,
    )


def _step_detail(step: StepResolution) -> StepDetail:
    beats = [
        BeatDetail(
            beat=beat.text,
            thing=beat.thing,
            verdict=beat.verdict,
            reason=beat.reason,
            roll=_roll_detail(beat.roll),
        )
        for beat in step.beats
        if beat.verdict is not BeatVerdict.HOLDS
    ]
    return StepDetail(
        text=step.text,
        outcome_class=step.outcome_class,
        reason=step.reason,
        roll=_roll_detail(step.roll),
        beats=beats or None,
    )


def _roll_detail(roll: RollRecord | None) -> RollDetail | None:
    if roll is None:
        return None
    odds_label = roll.odds_label or f"{round(roll.odds * 100)}%"
    return RollDetail(odds_label=odds_label, result=roll.result, seed=roll.seed)


def picture(
    state: WorldState, decision: PictureDecision | None, prompt: str | None, mode: NarrationMode
) -> ScenePicture | None:
    """M1: the picture code planned, with the narrator's prompt, or one built from the subject's
    record when the narrator wrote none. A scene picture of a scene whose telling was blocked is
    dropped, since its picture would be blocked too (F4); portraits and places stay."""
    if decision is None:
        return None
    if mode == "template" and decision.kind is PictureKind.SCENE:
        return None
    text = " ".join((prompt or "").split())
    if not text or mode == "template":
        text = fallback_prompt(state, decision)
    return ScenePicture(kind=decision.kind, prompt=text, subject_id=decision.subject_id)


def fallback_prompt(state: WorldState, decision: PictureDecision) -> str:
    subject_id = decision.subject_id
    character = state.characters.get(subject_id) if subject_id else None
    if character is not None:
        looks = character.appearance or character.description
        return f"Portrait of {character.name}. {looks}".strip()
    place = state.places.get(subject_id) if subject_id else None
    if place is not None:
        return f"{place.name}. {place_looks(place)}".strip()
    deed = state.deeds.get(subject_id) if subject_id else None
    if deed is not None:
        return deed.text
    return state.scene.ended_on or state.bible.genre or "A scene from the story."
