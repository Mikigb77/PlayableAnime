"""The scene a turn saves, in API.md's shape, built in code from what the turn decided.

The narrator writes the text, the suggestions and the picture prompt. Everything else on the
scene comes from the engine: the steps with their class, reason and roll (A2, A8), the beats
that found something new or came up empty (R2), the chain (A9), where a plan stopped (R6), the
event (W16), the picture code planned (M1) and the time.
"""

import re

from engine.contracts import (
    BeatVerdict,
    ChoiceKind,
    DirectorPlan,
    PictureDecision,
    PictureKind,
    Resolution,
    StepResolution,
    SuggestionPlan,
)
from engine.looks import place_looks
from engine.resolve import throw as dice
from engine.state.records import RollRecord, Throw
from engine.state.world import WorldState
from engine.world.telling import account
from graph.turn.outputs import NarratorOutput
from graph.turn.types import (
    BeatDetail,
    Choice,
    DieDetail,
    LinkDetail,
    NarrationMode,
    NumberPartDetail,
    RollDetail,
    SceneDetails,
    SceneDraft,
    SceneEvent,
    ScenePicture,
    StepDetail,
    StruckDetail,
    ThrowDetail,
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
    shown: SceneDetails | None = None,
    event_title: str | None = None,
) -> SceneDraft:
    """`before` is the state the scene started from; `after` the state once it played out.
    `shown` is the turn's details as the player was shown them, and `event_title` its event's
    title, where they were said again in the story's language (S10, `graph.turn.saying`)."""
    elapsed = after.world_s - before.world_s
    lived = after.player.personal_s(after.world_s) - before.player.personal_s(before.world_s)
    event = None
    if plan.event is not None:
        event = SceneEvent(size=plan.event.size, title=event_title or plan.event.title)
    return SceneDraft(
        turn=turn.ctx.turn,
        kind=turn.kind,
        player_action=_player_action(turn),
        narration=narration.text,
        choices=choices(narration, plan.suggestions) if mode != "template" else [],
        details=shown if shown is not None else details(resolution),
        event=event,
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


def choices(narration: NarratorOutput, plan: SuggestionPlan) -> list[Choice]:
    """S2: at most the number the director asked for, never wait or observe (always offered),
    each label short and unique. A way to let time pass is the director's to offer (W10), so a
    choice the narrator marked `time` beyond what the plan asked for is a side matter."""
    picked: list[Choice] = []
    seen: set[str] = set()
    if plan.count <= 0:
        return picked
    time_left = plan.kinds.count(ChoiceKind.TIME)
    for suggestion in narration.suggestions:
        label = " ".join(suggestion.label.split())[:MAX_CHOICE_CHARS]
        key = label.casefold().rstrip(".!")
        if not label or key in seen or key in _STANDING_WORDS:
            continue
        seen.add(key)
        kind = suggestion.kind
        if kind is ChoiceKind.TIME:
            kind = ChoiceKind.TIME if time_left > 0 else ChoiceKind.SIDE
            time_left -= 1
        picked.append(Choice(id=f"c{len(picked) + 1}", label=label, kind=kind))
        if len(picked) >= plan.count:
            break
    return picked


def details(resolution: Resolution, *, throws_told: bool = True) -> SceneDetails:
    """API.md's `SceneDetails`, so the player can see why (A8).

    The engine writes each throw into its reason in words, and the app leaves that sentence
    out, since it shows the dice themselves. `throws_told=False` leaves it out here, for
    reasons that are said again in the story's language (S10), where the app could no longer
    find the sentence."""
    links = [link for step in resolution.steps for link in step.chain]
    return SceneDetails(
        steps=[_step_detail(step, throws_told) for step in resolution.steps],
        chain=[
            LinkDetail(link=link.text, outcome_class=link.outcome_class, reason=link.reason)
            for link in links
        ]
        or None,
        stopped_at_step=resolution.stopped_at_step,
    )


def without_throw(reason: str, roll: RollRecord | None) -> str:
    """A reason without the sentence that tells its throw (`engine.resolve.throw.told`): what
    is left is what the throw meant. A reason worded another way is left whole."""
    if roll is None or roll.throw is None:
        return reason
    found = re.search(re.escape(dice.told(roll)), reason, re.IGNORECASE)
    if found is None:
        return reason
    rest = reason[found.end() :].removeprefix(".")
    return " ".join(f"{reason[: found.start()]}{rest}".split())


def _step_detail(step: StepResolution, throws_told: bool = True) -> StepDetail:
    def why(reason: str, roll: RollRecord | None) -> str:
        return reason if throws_told else without_throw(reason, roll)

    beats = [
        BeatDetail(
            beat=beat.text,
            thing=beat.thing,
            verdict=beat.verdict,
            reason=why(beat.reason, beat.roll),
            roll=_roll_detail(beat.roll),
        )
        for beat in step.beats
        if beat.verdict is not BeatVerdict.HOLDS
    ]
    struck = [
        StruckDetail(
            by=peril.by,
            outcome_class=peril.outcome_class,
            harm=peril.harm,
            reason=why(peril.reason, peril.roll),
            roll=_roll_detail(peril.roll),
        )
        for peril in step.perils
    ]
    return StepDetail(
        text=step.text,
        outcome_class=step.outcome_class,
        reason=why(step.reason, step.roll),
        roll=_roll_detail(step.roll),
        beats=beats or None,
        struck=struck or None,
    )


def _roll_detail(roll: RollRecord | None) -> RollDetail | None:
    if roll is None:
        return None
    odds_label = roll.odds_label or f"{round(roll.odds * 100)}%"
    return RollDetail(
        odds_label=odds_label,
        result=roll.result,
        seed=roll.seed,
        throw=_throw_detail(roll.throw) if roll.throw is not None else None,
    )


def _throw_detail(throw: Throw) -> ThrowDetail:
    """A3. The dice as they fell, for the app to show: it never rolls its own."""
    return ThrowDetail(
        dice=[DieDetail(kind=d.kind, face=d.face, sprung=d.sprung) for d in throw.dice],
        hand=throw.hand,
        hand_why=throw.hand_why,
        greens=list(throw.greens),
        number=throw.number,
        made_of=[NumberPartDetail(text=p.text, points=p.points) for p in throw.made_of],
        total=throw.total,
        most=throw.most,
        mark=throw.mark,
        against=throw.against,
        deadly=throw.deadly,
        miss_costs=throw.miss_costs,
        insight=throw.insight,
        insight_at=throw.insight_at,
    )


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
        return account(state, deed)  # in the world's words, not the player's step (G16)
    return state.scene.ended_on or state.bible.genre or "A scene from the story."
