"""What a turn's log line counts about the logic of play (T5), in numbers only.

A long story read by hand (2026-11-10) showed what makes play feel illogical: a throw deciding
whether an ordinary thing is there, a move the character had used all story refused as not
theirs, rumors under what they heard that no scene had told, and goals that only pile up. Each
turn counts the same things, so a change that brings one of them back shows as a number that
rises in the logs, and nobody has to read a story to see it (T6, T16).
"""

from engine.contracts.direction import DirectorPlan
from engine.contracts.intent import OutcomeClass
from engine.contracts.resolution import BeatVerdict, Resolution
from engine.state.records import GoalStatus
from engine.state.world import WorldState


def turn_tally(
    before: WorldState, after: WorldState, resolution: Resolution, plan: DirectorPlan
) -> dict[str, int]:
    """The turn's counts, from the state it started on, the state it saves, what the engine
    settled and what the director planned:

    - `refused`: the steps ruled out with no throw (A2), and `moves_refused`, those of them
      refused because a power or technique they named is on no record of the actor's (G14). A
      move the story let the character do is theirs (A4), so it must not come back refused.
    - `searches`: the things a throw decided the place holds or not (R2), and
      `searches_empty`, those that came up empty. What a place of that kind would hold is
      there with no throw, so these stay rare.
    - `rumors_heard`: the rumors the character who played the turn has now heard (W2), and
      `rumors_unvoiced`, those of them that aren't the talk the director gave the scene to
      tell. Only what a scene told is heard (C6), so this one stays at zero.
    - `goals_open`: the goals still open after the turn (N2).
    """
    steps = resolution.steps
    searches = [beat for step in steps for beat in step.beats if beat.roll is not None]
    heard = _newly_heard(before, after)
    told = plan.talk.rumor_id if plan.talk is not None else None
    return {
        "refused": sum(1 for step in steps if step.outcome_class is OutcomeClass.RULED_OUT),
        "moves_refused": sum(1 for step in steps if step.not_own),
        "searches": len(searches),
        "searches_empty": sum(1 for beat in searches if beat.verdict is BeatVerdict.EMPTY),
        "rumors_heard": len(heard),
        "rumors_unvoiced": sum(1 for rumor_id in heard if rumor_id != told),
        "goals_open": sum(1 for g in after.goals.values() if g.status is GoalStatus.ACTIVE),
    }


def _newly_heard(before: WorldState, after: WorldState) -> list[str]:
    """The rumors the character who played the turn hadn't heard when it started and has now."""
    player = before.player_id
    already = {i for i, rumor in before.rumors.items() if player in rumor.heard_at}
    return [i for i, rumor in after.rumors.items() if player in rumor.heard_at and i not in already]
