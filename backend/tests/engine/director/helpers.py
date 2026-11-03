"""Shared helpers for the director's tests: contexts, intents and a turn runner that calls the
pipeline seams in the graph's order (B5)."""

from dataclasses import dataclass

from engine import pipeline
from engine.base import HOUR
from engine.context import ContentPrefs, Rating, StorySettings, TurnContext
from engine.contracts import ActionKind, DirectorPlan, Intent, IntentStep, Resolution
from engine.pipeline import PlayOut
from engine.rng import SeededRng
from engine.state import WorldState


def ctx(turn: int = 2, *, story: str = "s1", rating=Rating.TEEN, prefs=None, **settings):
    return TurnContext(
        story_id=story,
        turn=turn,
        settings=StorySettings(**settings),
        rating=rating,
        content_prefs=prefs or ContentPrefs(),
    )


def rng(story: str = "s1", turn: int = 2) -> SeededRng:
    return SeededRng.for_turn(story, "main", turn)


def act(text: str, verb: str, kind: ActionKind, duration_s: int, **intent) -> Intent:
    step = IntentStep(text=text, verb=verb, kind=kind, proposed_duration_s=duration_s)
    return Intent(steps=[step], **intent)


def farming(**intent) -> Intent:
    return act("Work the fields", "farm", ActionKind.WORK, 6 * HOUR, **intent)


def supper(**intent) -> Intent:
    return act("Have supper with Ilse", "eat supper", ActionKind.CONVERSATION, HOUR, **intent)


def fence(**intent) -> Intent:
    return act("Mend the fence", "mend fence", ActionKind.TASK, 3 * HOUR, **intent)


def full_day(**intent) -> Intent:
    """A day's farming and a night's sleep: 24 in-world hours."""
    steps = [
        IntentStep(
            text="Work the fields all day",
            verb="farm",
            kind=ActionKind.WORK,
            proposed_duration_s=12 * HOUR,
        ),
        IntentStep(text="Sleep", verb="sleep", kind=ActionKind.REST, proposed_duration_s=12 * HOUR),
    ]
    return Intent(steps=steps, **intent)


@dataclass
class Turn:
    state: WorldState
    plan: DirectorPlan
    play: PlayOut


def play_turn(
    state: WorldState,
    turn: int,
    intent: Intent,
    *,
    story: str = "s1",
    stakes: bool = False,
    resolution: Resolution | None = None,
    rating=Rating.TEEN,
    prefs=None,
    **settings,
) -> Turn:
    """One turn through the seams: catch up, resolve, play out, direct, record."""
    context = ctx(turn, story=story, rating=rating, prefs=prefs, **settings)
    turn_rng = rng(story, turn)
    state = pipeline.catch_up(state, state.world_s, context, turn_rng.child("catch_up")).state
    resolved = resolution or pipeline.resolve(state, intent, context, turn_rng)
    if stakes:
        resolved = resolved.model_copy(update={"stakes": True})
    play = pipeline.play_out(state, resolved, context, turn_rng)
    plan = pipeline.direct(play.state, play.resolution, context, turn_rng, intent=intent)
    after = pipeline.record_direction(play.state, plan, context)
    after.turn = turn
    return Turn(state=after, plan=plan, play=play)
